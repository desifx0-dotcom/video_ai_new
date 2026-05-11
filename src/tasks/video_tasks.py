"""
Video processing Celery tasks.
"""

import os
import sys
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List
# from api.websocket import send_progress_update, send_video_update, send_video_completed
import uuid
from .celery_app import celery_app
from services.video_service import VideoService
from services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationChannel,
)
from core.exceptions import ProcessingError
logger = logging.getLogger(__name__)

video_service = VideoService()


def _check_silent_video_tier(video, user_id):
    """Check if user can process silent video based on tier."""
    from services.user_service import UserService
    from services.tier_service import TierService
    from core.exceptions import TierLimitExceeded

    user_service = UserService()
    tier_service = TierService()

    user = user_service.get_user_by_id(user_id)
    if not user:
        return False, "User not found"

    is_silent = getattr(video, "is_silent", False)

    if is_silent and not tier_service.is_silent_video_allowed(user.tier):
        raise TierLimitExceeded(
            "silent_video",
            0,
            0,
            message=f"Silent videos are not available in {user.tier.value} tier. "
            f"Upgrade to Starter or higher to process silent videos.",
            upgrade_url="/pricing",
        )

    return True, ""


# Helper function to get WebSocket module lazily
def _get_websocket():
    """Lazy import WebSocket functions to avoid circular imports."""
    from api.websocket import (
        send_video_update,
        send_video_completed,
        send_video_failed,
        send_progress_update,
    )

    return (
        send_video_update,
        send_video_completed,
        send_video_failed,
        send_progress_update,
    )


def _send_ws_update(video_id, user_id, status, progress, step=None, message=None):
    """Send WebSocket update safely."""
    try:
        send_video_update, _, _, _ = _get_websocket()
        send_video_update(video_id, user_id, status, progress, step, message)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket update: {e}")


def _send_ws_completed(video_id, user_id, url, proc_time, cost):
    """Send WebSocket completion safely."""
    try:
        _, send_completed, _, _ = _get_websocket()
        send_completed(video_id, user_id, url, proc_time, cost)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket completion: {e}")


def _send_ws_failed(video_id, user_id, error, retry_count, can_retry):
    """Send WebSocket failure safely."""
    try:
        _, _, send_failed, _ = _get_websocket()
        send_failed(video_id, user_id, error, retry_count, can_retry)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket failure: {e}")


@celery_app.task(bind=True, max_retries=3)
def process_video_async(
    self, video_id: str, user_id: str, options: Dict[str, Any] = None
):
    """
    Process video asynchronously - PRODUCTION OPTIMIZED ORDER.
    
    Processing order (optimal for quality & performance):
    1. Speed change (affects timing, not resolution)
    2. FPS change (affects timing)
    3. Audio quality (independent)
    4. Video styles (visual effects)
    5. Quality scaling (final resolution)
    6. Aspect ratio (final reshape - LAST)
    """
    options = options or {}
    from services.user_service import UserService

    # Log received options
    logger.info("=" * 80)
    logger.info(f"📥 VIDEO PROCESSING STARTED for {video_id}")
    logger.info(f"📥 Received options:")
    for key in ['quality', 'fps', 'audio_quality', 'aspect_ratio', 'speed', 'speed_presets', 'thumbnail_style', 'styles']:
        logger.info(f"   {key}: {options.get(key)}")
    logger.info("=" * 80)

    notification_service = NotificationService()
    user_service = UserService()
    send_email_notification = options.get("send_email_notification", False)

    try:
        logger.info(f"Starting video processing for video_id: {video_id}, user_id: {user_id}")

        # Send initial WebSocket update
        _send_ws_update(video_id, user_id, "queued", 5, "queued", "Video queued for processing")

        #  INITIAL STATUS - QUEUED
        video_service.update_processing_status(video_id, "queued", 5, "queued")
        
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"current": "starting", "total": 100, "status": "Initializing..."}
        )

        #  STATUS - ANALYZING
        video_service.update_processing_status(video_id, "processing", 10, "analyzing")
        _send_ws_update(video_id, user_id, "processing", 10, "analyzing", "Analyzing video...")

        # Get video data
        video = video_service.get_video_by_id(video_id)
        if not video:
            raise ProcessingError(f"Video not found: {video_id}")

        # Silent video tier enforcement
        _check_silent_video_tier(video, user_id)

        # Detect if video is silent
        if not hasattr(video, "is_silent"):
            from services.silent_video_service import SilentVideoService
            silent_service = SilentVideoService()
            video.is_silent = silent_service.is_silent_video(video.original_path)
            logger.info(f"Video {video_id} silent detection: {video.is_silent}")

        # ========== STEP 1: EXTRACT AND SAVE USER SETTINGS ==========
        settings_changed = False
        
        # 1.1 SPEED (extract from options)
        speed_value = options.get("speed")
        if speed_value is None:
            speed_value = options.get("speed_presets")
            if speed_value and isinstance(speed_value, str):
                speed_value = float(speed_value.replace('x', ''))
        if speed_value is None:
            speed_value = 1.0
        
        if speed_value != 1.0:
            video.speed = speed_value
            logger.info(f"✅ Setting speed: {speed_value}x")
            settings_changed = True
        
        # 1.2 FPS
        if options.get("fps") and options["fps"] != "original":
            video.fps = options["fps"]
            logger.info(f"✅ Setting FPS: {options['fps']}")
            settings_changed = True

        # 1.3 Audio Quality
        if options.get("audio_quality") and options["audio_quality"] != "original":
            video.audio_quality = options["audio_quality"]
            logger.info(f"✅ Setting audio quality: {options['audio_quality']}")
            settings_changed = True

        # 1.4 Output Quality
        if options.get("quality") and options["quality"] != "original":
            video.output_quality = options["quality"]
            logger.info(f"✅ Setting output quality: {options['quality']}")
            settings_changed = True

        # 1.5 Thumbnail Style (metadata only)
        if options.get("thumbnail_style"):
            video.thumbnail_style = options["thumbnail_style"]
            logger.info(f"✅ Setting thumbnail style: {options['thumbnail_style']}")
            settings_changed = True

        # 1.6 Video Styles
        if options.get("styles") and len(options["styles"]) > 0:
            video.applied_styles = options["styles"]
            logger.info(f"✅ Setting video styles: {options['styles']}")
            settings_changed = True

        # 1.7 Aspect Ratio (save for last)
        if options.get("aspect_ratio") and options["aspect_ratio"] != "original":
            video.aspect_ratio = options["aspect_ratio"]
            logger.info(f"✅ Setting aspect ratio (will apply last): {options['aspect_ratio']}")
            settings_changed = True

        # Save all settings to database before processing
        if settings_changed:
            video_service.update_video(video)
            logger.info(f"💾 Saved video settings to database")

        # ========== STEP 2: SILENT VIDEO OR TRANSCRIPTION ==========
        _send_ws_update(video_id, user_id, "processing", 10, "analyzing", "Analyzing video...")
        self.update_state(state="PROGRESS", meta={"current": "analyzing", "total": 100, "status": "Analyzing video..."})

        video_type = options.get("video_type", "speech")

        if options.get("process_silent_video") or video_type == "silent":
            logger.info(f"Processing silent video: {video_id}")
            # STATUS - PROCESSING SILENT
            video_service.update_processing_status(video_id, "processing", 20, "silent_analysis")
            _process_silent_video(video, options)
        else:
            if video_type == "speech" and options.get("auto_transcribe", True):
                # STATUS - TRANSCRIBING
                video_service.update_processing_status(video_id, "processing", 30, "transcribing")
                _send_ws_update(video_id, user_id, "processing", 25, "transcribing", "Transcribing audio...")
                self.update_state(state="PROGRESS", meta={"current": "transcribing", "total": 100, "status": "Transcribing audio..."})
                _transcribe_video(video, options)

        # ========== STEP 3: GENERATE METADATA ==========
         # STATUS - GENERATING METADATA
        video_service.update_processing_status(video_id, "processing", 40, "metadata")
        _send_ws_update(video_id, user_id, "processing", 35, "generating_metadata", "Generating title and description...")
        self.update_state(state="PROGRESS", meta={"current": "metadata", "total": 100, "status": "Generating metadata..."})
        _generate_metadata(video, options)

        # ========== STEP 4: GENERATE THUMBNAILS ==========
                # STATUS - GENERATING THUMBNAILS
        video_service.update_processing_status(video_id, "processing", 50, "thumbnails")
        _send_ws_update(video_id, user_id, "processing", 45, "generating_thumbnails", "Creating thumbnails...")
        self.update_state(state="PROGRESS", meta={"current": "thumbnails", "total": 100, "status": "Generating thumbnails..."})
        _generate_thumbnails(video, options, user_id)

        # ========== STEP 5: APPLY SPEED (timing change) ==========
        if speed_value != 1.0:
            logger.info(f"🎬 Applying speed change: {speed_value}x")
            video_service.update_processing_status(video_id, "processing", 60, "speed")
            _send_ws_update(video_id, user_id, "processing", 55, "speed", f"Applying speed change: {speed_value}x")
            self.update_state(state="PROGRESS", meta={"current": "speed", "total": 100, "status": f"Adjusting speed to {speed_value}x..."})
            success = _apply_speed(video, float(speed_value))
            if success:
                video_service.update_video(video)
                logger.info(f"💾 Saved after speed: {speed_value}x")
            else:
                logger.warning(f"⚠️ Speed change failed, continuing")

        # ========== STEP 6: APPLY FPS (timing change) ==========
        if video.fps and video.fps != "original":
            video_service.update_processing_status(video_id, "processing", 70, "fps")
            _send_ws_update(video_id, user_id, "processing", 65, "fps", f"Adjusting frame rate to {video.fps} fps")
            self.update_state(state="PROGRESS", meta={"current": "fps", "total": 100, "status": f"Adjusting frame rate to {video.fps} fps..."})
            _apply_fps(video, video.fps)
            video_service.update_video(video)
            logger.info(f"💾 Saved after FPS: {video.fps}")

        # ========== STEP 7: APPLY AUDIO QUALITY ==========
        if video.audio_quality and video.audio_quality != "original":
            video_service.update_processing_status(video_id, "processing", 75, "audio")
            _send_ws_update(video_id, user_id, "processing", 75, "audio", f"Adjusting audio quality to {video.audio_quality}")
            self.update_state(state="PROGRESS", meta={"current": "audio", "total": 100, "status": "Adjusting audio quality..."})
            _apply_audio_quality(video, video.audio_quality)
            video_service.update_video(video)
            logger.info(f"💾 Saved after audio: {video.audio_quality}")

        # ========== STEP 8: APPLY VIDEO STYLES ==========
        if video.applied_styles and len(video.applied_styles) > 0:
            video_service.update_processing_status(video_id, "processing", 80, "styles")
            _send_ws_update(video_id, user_id, "processing", 82, "styles", "Applying video styles...")
            self.update_state(state="PROGRESS", meta={"current": "styles", "total": 100, "status": "Applying video styles..."})
            _apply_video_styles(video, video.applied_styles)
            video_service.update_video(video)
            logger.info(f"💾 Saved after styles: {video.applied_styles}")

        # ========== STEP 9: APPLY QUALITY SCALING ==========
        if video.output_quality and video.output_quality != "original":
            video_service.update_processing_status(video_id, "processing", 85, "quality")
            _send_ws_update(video_id, user_id, "processing", 88, "quality", f"Scaling to {video.output_quality}")
            self.update_state(state="PROGRESS", meta={"current": "quality", "total": 100, "status": f"Scaling to {video.output_quality}..."})
            _apply_quality(video, video.output_quality)
            video_service.update_video(video)
            logger.info(f"💾 Saved after quality: {video.output_quality}")

        # ========== STEP 10: APPLY ASPECT RATIO (LAST - final reshape) ==========
        if video.aspect_ratio and video.aspect_ratio != "original":
            video_service.update_processing_status(video_id, "processing", 90, "aspect_ratio")
            _send_ws_update(video_id, user_id, "processing", 94, "aspect_ratio", f"Changing aspect ratio to {video.aspect_ratio}")
            self.update_state(state="PROGRESS", meta={"current": "aspect_ratio", "total": 100, "status": f"Changing aspect ratio to {video.aspect_ratio}..."})
            _apply_aspect_ratio(video, video.aspect_ratio)
            video_service.update_video(video)
            logger.info(f"💾 Saved after aspect ratio: {video.aspect_ratio}")

        # ========== STEP 11: FINALIZE ==========
        video_service.update_processing_status(video_id, "processing", 95, "finalizing")
        _send_ws_update(video_id, user_id, "processing", 98, "finalizing", "Finalizing output...")
        self.update_state(state="PROGRESS", meta={"current": "finalizing", "total": 100, "status": "Finalizing output..."})
        output_path = _finalize_video(video, options)

        # ========== STEP 12: COMPLETE ==========
        video.status = "completed"
        video.processing_completed = datetime.utcnow()
        if video.processing_started:
            video.processing_time = (video.processing_completed - video.processing_started).total_seconds()
        video.output_video_url = output_path
        video.output_path = output_path
        
        video_service.update_video(video)
        
        # Log final settings
        logger.info("=" * 80)
        logger.info(f"✅ VIDEO PROCESSING COMPLETED for {video_id}")
        logger.info(f"📊 Final video settings:")
        logger.info(f"   quality: {video.output_quality}")
        logger.info(f"   fps: {video.fps}")
        logger.info(f"   audio_quality: {video.audio_quality}")
        logger.info(f"   aspect_ratio: {video.aspect_ratio}")
        logger.info(f"   speed: {getattr(video, 'speed', 1.0)}x")
        logger.info(f"   output_path: {output_path}")
        logger.info("=" * 80)

        # Send completion notification
        _send_ws_completed(video_id, user_id, video.output_video_url, video.processing_time, video.total_cost)

        # Verify output path
        if not video.output_video_url or not os.path.exists(video.output_video_url):
            final_output = video.output_path if hasattr(video, "output_path") and video.output_path else None
            if final_output and os.path.exists(final_output):
                video.output_video_url = final_output
                video_service.update_video(video)
                logger.info(f"[FIX] Set output_video_url to: {final_output}")

        return {
            "success": True,
            "video_id": video_id,
            "output_url": video.output_video_url,
            "processing_time": video.processing_time,
        }

    except ProcessingError as e:
        logger.error(f"Video processing failed: {str(e)}")
        _send_ws_failed(video_id, user_id, str(e), self.request.retries, self.request.retries < self.max_retries)

        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))

        return {"success": False, "video_id": video_id, "error": str(e), "retries_exhausted": True}

    except Exception as e:
        logger.error(f"Video processing failed: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        _send_ws_failed(video_id, user_id, str(e), self.request.retries, self.request.retries < self.max_retries)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return {"success": False, "video_id": video_id, "error": str(e), "retries_exhausted": True}

# Helper functions (regular functions, not async)
def _process_silent_video(video, options):
    """
    Process silent video using Gemini Vision with tier-based frame analysis.

    Free tier: Not available - returns reminder message
    Starter: 2 frames analysis
    Pro: 3 frames analysis
    Plus: 4 frames analysis
    Enterprise: 15 frames analysis
    """
    from providers.google_provider import GoogleProvider
    from providers.ffmpeg_provider import FFmpegProvider
    import tempfile
    import os

    try:
        video.is_silent = True
        # Get user tier
        user_tier = video.processed_tier or "free"
        logger.info(f"Processing silent video for tier: {user_tier}")

        # Define frame counts per tier
        frame_counts = {
            "free": 0,  # No frames for free tier
            "starter": 2,
            "pro": 3,
            "plus": 4,
            "enterprise": 15,
        }

        frame_count = frame_counts.get(user_tier, 0)

        # Handle FREE TIER - Silent video not allowed
        if user_tier == "free":
            logger.info(f"Free tier user attempted silent video: {video.id}")

            # Set reminder message for free tier
            video.title = "Silent Video Processing Not Available in Free Tier"
            video.description = """
            Silent video analysis is not available in the Free tier. 
            
            To analyze silent videos (videos without speech), please upgrade to:
            - Starter Tier: 2 frame analysis
            - Pro Tier: 3 frame analysis  
            - Plus Tier: 4 frame analysis
            - Enterprise: 15 frame analysis
            
            Silent videos use AI vision technology to analyze frames and generate:
            - Titles from visual content
            - Descriptions from scene analysis
            - Tags from objects detected
            - AI-generated thumbnails
            """
            video.tags = ["silent-video", "upgrade-required", "free-tier-limit"]
            video.transcription = "Silent video processing requires a paid tier. Upgrade to analyze this video."

            # Add upgrade CTA in transcription
            video.transcription_language = "en"

            logger.info(f"Free tier silent video processed with reminder message")
            return

        # For paid tiers, proceed with frame extraction
        logger.info(
            f"Processing silent video with {frame_count} frames for tier: {user_tier}"
        )

        provider = GoogleProvider()
        ffmpeg = FFmpegProvider()

        # Get video duration
        duration = video.duration or 60
        logger.info(f"Video duration: {duration}s, extracting {frame_count} frames")

        # Calculate frame timestamps (evenly spread throughout video)
        if frame_count == 1:
            timestamps = [duration / 2]  # Middle of video
        else:
            # Spread frames evenly
            interval = duration / (frame_count + 1)
            timestamps = [interval * (i + 1) for i in range(frame_count)]

        logger.info(f"Extracting frames at timestamps: {timestamps}")

        # Extract frames
        frames = []
        frame_paths = []

        for i, ts in enumerate(timestamps):
            try:
                frame_path = ffmpeg.extract_frame(
                    video.original_path,
                    ts,
                    tempfile.gettempdir(),
                    f"silent_frame_{video.id}_{i}",
                )
                if frame_path and os.path.exists(frame_path):
                    frames.append(frame_path)
                    frame_paths.append(frame_path)
                    logger.info(f"Extracted frame {i+1}/{frame_count} at {ts}s")
            except Exception as e:
                logger.error(f"Failed to extract frame at {ts}s: {e}")
                continue

        if not frames:
            logger.warning(f"No frames extracted for video {video.id}")
            # Fallback to basic metadata
            video.title = "Silent Video"
            video.description = "A silent video uploaded to Video AI Studio"
            video.tags = ["silent", "video", "no-speech"]
            return

        logger.info(f"Successfully extracted {len(frames)} frames")

        # Analyze each frame with Gemini Vision
        frame_analyses = []
        for i, frame_path in enumerate(frames):
            try:
                analysis = provider.analyze_image(frame_path)
                frame_analyses.append(
                    {
                        "frame": i + 1,
                        "timestamp": timestamps[i],
                        "description": analysis.get("description", ""),
                        "objects": analysis.get("objects", []),
                        "colors": analysis.get("colors", []),
                        "labels": analysis.get("labels", []),
                    }
                )
                logger.info(f"Analyzed frame {i+1}/{len(frames)}")
            except Exception as e:
                logger.error(f"Failed to analyze frame {i}: {e}")
                frame_analyses.append(
                    {
                        "frame": i + 1,
                        "timestamp": timestamps[i],
                        "description": "",
                        "objects": [],
                        "colors": [],
                        "labels": [],
                    }
                )

        # Combine all analyses
        combined_descriptions = [
            a["description"] for a in frame_analyses if a["description"]
        ]
        combined_objects = []
        combined_colors = []
        combined_labels = []

        for analysis in frame_analyses:
            combined_objects.extend(analysis.get("objects", []))
            combined_colors.extend(analysis.get("colors", []))
            combined_labels.extend(analysis.get("labels", []))

        # Remove duplicates while preserving order
        combined_objects = list(dict.fromkeys(combined_objects))
        combined_colors = list(dict.fromkeys(combined_colors))
        combined_labels = list(dict.fromkeys(combined_labels))

        # Build prompt for metadata generation
        prompt = f"""
        Based on this silent video analysis, generate:
        
        1. A catchy, clickable YouTube title (max 60 chars)
        2. An engaging description (150-200 words) describing the visual content
        3. 10 relevant SEO tags
        
        Video Analysis:
        - Duration: {duration:.1f} seconds
        - Frames analyzed: {len(frames)}
        - Scene descriptions: {' '.join(combined_descriptions[:500])}
        - Objects detected: {', '.join(combined_objects[:20])}
        - Colors present: {', '.join(combined_colors[:10])}
        - Visual themes: {', '.join(combined_labels[:15])}
        
        Return in JSON format:
        {{
            "title": "...",
            "description": "...",
            "tags": ["tag1", "tag2", ...]
        }}
        """

        # Generate metadata
        try:
            response = provider.generate_text(prompt, model="gemini-1.5-flash")

            # Parse JSON response
            import json
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # Fallback
                result = {
                    "title": f"Silent Video - {combined_labels[:3] if combined_labels else 'Visual Content'}",
                    "description": (
                        " ".join(combined_descriptions[:3])
                        if combined_descriptions
                        else "A silent video with visual content"
                    ),
                    "tags": combined_objects[:10] + ["silent", "video"],
                }
        except Exception as e:
            logger.error(f"Metadata generation failed: {e}")
            result = {
                "title": "Silent Video - Visual Content",
                "description": "A silent video. "
                + (
                    " ".join(combined_descriptions[:2]) if combined_descriptions else ""
                ),
                "tags": ["silent", "video", "visual"] + combined_objects[:5],
            }

        # Store results in video object
        video.title = result.get("title", "Silent Video")
        video.description = result.get(
            "description", "A silent video with visual content"
        )
        video.tags = result.get("tags", ["silent", "video"])

        # Store analysis for reference
        video.silent_analysis = {
            "frames_analyzed": len(frames),
            "tier": user_tier,
            "frame_data": frame_analyses,
            "objects_detected": combined_objects,
            "colors_detected": combined_colors,
            "visual_themes": combined_labels,
        }

        # Set transcription to empty string (no audio)
        video.transcription = ""
        video.transcription_language = "silent"

        logger.info(
            f"Silent video analysis completed for {video.id} with {len(frames)} frames"
        )

        # Clean up temporary frame files
        for frame_path in frame_paths:
            try:
                os.unlink(frame_path)
            except:
                pass

    except Exception as e:
        logger.error(f"Silent video processing failed: {e}")

        # Set error message in video
        video.title = "Silent Video Processing Failed"
        video.description = (
            f"An error occurred while processing this silent video: {str(e)}"
        )
        video.tags = ["error", "silent-video"]

        raise ProcessingError(
            f"Silent video analysis failed: {str(e)}", step="silent_analysis"
        )


def _transcribe_video(video, options):
    """Transcribe video audio."""
    from providers.openai_provider import OpenAIProvider

    try:
        provider = OpenAIProvider()

        # Extract audio from video
        from providers.ffmpeg_provider import FFmpegProvider

        ffmpeg = FFmpegProvider()

        import tempfile

        audio_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        ffmpeg.extract_audio(video.original_path, audio_path)

        # Transcribe
        transcript = provider.transcribe_audio(audio_path)
        video.transcription = transcript
        video.transcription_language = "en"

        # Clean up
        os.unlink(audio_path)

        logger.info(f"Transcription completed for {video.id}")

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise ProcessingError(f"Transcription failed: {str(e)}", step="transcription")


def _generate_metadata(video, options):
    """Generate title, description, and tags."""
    from services.title_service import TitleService

    try:
        logger.info(f"Generating metadata for video {video.id}")
        logger.info(
            f"Video transcription length: {len(video.transcription) if video.transcription else 0}"
        )
        title_service = TitleService()
        result = title_service.generate_metadata(
            transcript=video.transcription or "", video_id=video.id, options=options
        )

        video.title = result.get("title", "")
        video.description = result.get("description", "")
        video.tags = result.get("tags", [])

        logger.info(f"Metadata generation completed for {video.id}")

    except Exception as e:
        logger.error(f"Metadata generation failed: {e}")
        logger.error(traceback.format_exc())
        # Don't raise - set defaults and continue
        video.title = "Untitled Video"
        video.description = "Video processed by Video AI Studio"
        video.tags = ["video", "ai", "processed"]


def _generate_thumbnails(video, options, user_id):
    """Generate thumbnails."""
    from services.thumbnail_service import ThumbnailService

    # check if original_path exists
    if not video.original_path:
        logger.error(f"Video {video.id} has no original_path")
        # Try to get from database again
        video_data = video_service.db.get("videos", video.id)
        if video_data and video_data.get("original_path"):
            video.original_path = video_data["original_path"]
        else:
            raise ProcessingError(f"No original path found for video {video.id}")

    try:
        thumbnail_service = ThumbnailService()

        # Pass the thumbnail_style from options
        thumbnail_style = options.get("thumbnail_style", "default")
        logger.info(f"Generating thumbnails with style: {thumbnail_style}")

        result = thumbnail_service.generate_thumbnails(
            video_path=video.original_path,
            title=video.title or "Video",
            video_type="speech" if video.transcription else "silent",
            tier=video.processed_tier or "free",
            transcription=video.transcription,
            user_id=user_id,
            video_id=video.id,
            thumbnail_style=thumbnail_style,
        )

        video.ai_thumbnails = result.get("ai_thumbnails", [])
        video.extracted_thumbnails = result.get("extracted_thumbnails", [])
        video.selected_thumbnail = result.get(
            "selected_thumbnail",
            video.ai_thumbnails[0]["path"] if video.ai_thumbnails else None,
        )

        video.thumbnail_style = thumbnail_style

        logger.info(f"Thumbnail generation completed for {video.id}")

    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise ProcessingError(
            f"Thumbnail generation failed: {str(e)}", step="thumbnails"
        )

def emit_websocket_update(video_id, user_id, status, progress):
    """Safe WebSocket emission."""
    try:
        from api.websocket import socketio

        if socketio is not None:
            socketio.emit(
                "video_status_update",
                {
                    "video_id": video_id,
                    "status": status,
                    "progress": progress,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=user_id,
            )
    except Exception as e:
        logger.warning(f"WebSocket emit failed for video {video_id}: {e}")

def _apply_video_styles(video, styles):
    """
    PRODUCTION SMART VERSION:
    1. Scales DOWN to 720p for memory-efficient processing
    2. Applies styles to the scaled version
    3. Scales BACK UP to original resolution (preserves quality!)
    """
    import os
    import subprocess
    import time
    import json
    import uuid

    try:
        input_path = video.output_path if hasattr(video, "output_path") and video.output_path else video.original_path

        if not input_path or not os.path.exists(input_path):
            logger.error(f"[STYLES] Input not found: {input_path}")
            return

        # ========== 1. Get ORIGINAL resolution ==========
        probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height", "-of", "json", input_path]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        original_width = 1920
        original_height = 1080
        
        if result.returncode == 0:
            info = json.loads(result.stdout)
            original_width = info.get('streams', [{}])[0].get('width', 1920)
            original_height = info.get('streams', [{}])[0].get('height', 1080)
            logger.info(f"[STYLES] 📐 ORIGINAL resolution: {original_width}x{original_height}")

        # ========== 2. CREATE scaled version for processing ==========
        temp_dir = os.path.dirname(input_path)
        scaled_path = os.path.join(temp_dir, f"temp_scaled_{uuid.uuid4().hex[:8]}.mp4")
        
        logger.info(f"[STYLES] 📐 TEMPORARILY scaling down to 1280x720 for processing (memory efficient)")
        
        scale_cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", "scale=1280:720",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            "-y", scaled_path
        ]
        
        scale_result = subprocess.run(scale_cmd, capture_output=True, text=True, timeout=120)
        
        if scale_result.returncode != 0 or not os.path.exists(scaled_path):
            logger.warning(f"[STYLES] Scaling failed, continuing with original resolution")
            working_path = input_path
            needs_restore = False
        else:
            working_path = scaled_path
            needs_restore = True
            logger.info(f"[STYLES] ✅ Scaled to 720p for processing")

        # ========== 3. Apply styles to scaled version ==========
        style_filters = {
            "cinematic": "eq=brightness=0.05:contrast=1.15:saturation=1.1",
            "bright": "eq=brightness=0.1:contrast=1.05:saturation=1.15",
            "educational": "eq=brightness=0.02:contrast=1.08:saturation=1.05",
            "gaming": "eq=saturation=1.25:contrast=1.1:brightness=0.03",
            "vlog": "eq=brightness=0.08:contrast=1.02:saturation=1.08",
            "travel": "eq=saturation=1.15:contrast=1.05:brightness=0.05",
            "professional": "eq=contrast=1.05:saturation=0.95",
            "documentary": "eq=brightness=0:contrast=1.02:saturation=0.92",
            "wedding": "eq=brightness=0.07:contrast=1.02:saturation=1.05",
            "corporate": "eq=brightness=0.03:contrast=1.08:saturation=0.98",
            "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.06",
            "cinematic_pro": "eq=brightness=0.04:contrast=1.2:saturation=1.05",
            "artistic": "eq=saturation=1.15:contrast=1.08:brightness=0.02",
            "retro": "eq=brightness=0.02:contrast=0.92:saturation=0.85",
            "futuristic": "eq=saturation=1.2:contrast=1.12:brightness=0.04",
        }

        style_names = {
            "cinematic": "Cinematic", "bright": "Bright & Vibrant",
            "educational": "Educational", "gaming": "Gaming",
            "vlog": "Vlog", "travel": "Travel",
            "professional": "Professional", "documentary": "Documentary",
            "wedding": "Wedding", "corporate": "Corporate",
            "real_estate": "Real Estate", "cinematic_pro": "Cinematic Pro",
            "artistic": "Artistic", "retro": "Retro", "futuristic": "Futuristic",
        }

        applied = []
        current_input = working_path

        for style_name in styles:
            filter_chain = style_filters.get(style_name)
            if not filter_chain:
                continue

            display_name = style_names.get(style_name, style_name)
            base_name = os.path.splitext(current_input)[0]
            output_path = f"{base_name}_styled_{style_name}.mp4"

            logger.info(f"[STYLES] Applying '{display_name}' to scaled video")

            cmd = [
                "ffmpeg", "-i", current_input,
                "-vf", filter_chain,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "copy",
                "-movflags", "+faststart",
                "-y", output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                if current_input != working_path and os.path.exists(current_input):
                    try:
                        os.remove(current_input)
                    except:
                        pass
                current_input = output_path
                applied.append(style_name)
                logger.info(f"[STYLES] ✅ Applied '{display_name}' to scaled version")
            else:
                logger.error(f"[STYLES] ❌ Failed to apply '{display_name}'")
                break

        # ========== 4. RESTORE to original resolution ==========
        if applied and needs_restore and os.path.exists(current_input):
            final_output = current_input.replace("_styled_", f"_styled_final_{original_width}x{original_height}_")
            
            logger.info(f"[STYLES] 🔄 RESTORING to original resolution {original_width}x{original_height}")
            
            restore_cmd = [
                "ffmpeg", "-i", current_input,
                "-vf", f"scale={original_width}:{original_height}:force_original_aspect_ratio=decrease,pad={original_width}:{original_height}:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-c:a", "copy",
                "-movflags", "+faststart",
                "-y", final_output
            ]
            
            restore_result = subprocess.run(restore_cmd, capture_output=True, text=True, timeout=180)
            
            if restore_result.returncode == 0 and os.path.exists(final_output):
                # Update video to use the restored high-quality version
                video.output_path = final_output
                logger.info(f"[STYLES] ✅ RESTORED to {original_width}x{original_height}")
                
                # Clean up styled version (no longer needed)
                if os.path.exists(current_input) and current_input != final_output:
                    try:
                        os.remove(current_input)
                    except:
                        pass
            else:
                # Restore failed, keep the styled version
                video.output_path = current_input
                logger.warning(f"[STYLES] Restore failed, keeping scaled version")
        elif applied:
            video.output_path = current_input

        # Update video
        if applied:
            video.applied_styles = applied
            video_service.update_video(video)
            logger.info(f"[STYLES] ✅ Final resolution: {original_width}x{original_height}")
            logger.info(f"[STYLES] ✅ Styles applied: {applied}")

        # ========== 5. Cleanup ==========
        if needs_restore and os.path.exists(scaled_path):
            try:
                os.remove(scaled_path)
            except:
                pass

    except Exception as e:
        logger.error(f"[STYLES] Failed: {e}")
        import traceback
        traceback.print_exc()

def _apply_aspect_ratio(video, aspect_ratio):
    """
    Actually change the video container resolution to target aspect ratio.
    Uses letterboxing (keeps all content, no cropping).
    """
    import os
    import subprocess
    import json
    import uuid

    try:
        input_path = (
            video.output_path
            if hasattr(video, "output_path") and video.output_path
            else video.original_path
        )

        if not input_path or not os.path.exists(input_path):
            logger.error(f"[ASPECT] Input path does not exist: {input_path}")
            return False

        # Get original resolution
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        orig_width, orig_height = 1920, 1080
        
        if result.returncode == 0:
            info = json.loads(result.stdout)
            orig_width = info.get('streams', [{}])[0].get('width', 1920)
            orig_height = info.get('streams', [{}])[0].get('height', 1080)
            logger.info(f"[ASPECT] Original resolution: {orig_width}x{orig_height}")

        # Target dimensions for each aspect ratio
        aspect_map = {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),   # This will CHANGE your video to 1080x1920
            "1:1": (1080, 1080),
            "4:5": (1080, 1350),
            "2:3": (1080, 1620),
            "3:2": (1920, 1280),
            "21:9": (2560, 1080),
            "5:4": (1280, 1024),
        }

        if aspect_ratio not in aspect_map:
            logger.warning(f"[ASPECT] Unknown aspect ratio: {aspect_ratio}")
            return False

        target_width, target_height = aspect_map[aspect_ratio]
        
        logger.info(f"[ASPECT] 🎯 CHANGING VIDEO RESOLUTION to: {target_width}x{target_height}")
        logger.info(f"[ASPECT] Original: {orig_width}x{orig_height} → Target: {target_width}x{target_height}")

        # Create output path with new resolution
        temp_dir = os.path.dirname(input_path)
        output_filename = f"{uuid.uuid4().hex[:8]}_{aspect_ratio.replace(':', 'x')}.mp4"
        output_path = os.path.join(temp_dir, output_filename)

        # Calculate scaling to fit within target (letterbox, no crop)
        # This scales the video to fit INSIDE the target dimensions
        scale_to_fit_width = target_width / orig_width
        scale_to_fit_height = target_height / orig_height
        scale_factor = min(scale_to_fit_width, scale_to_fit_height)  # Use min to fit within
        
        scaled_width = int(orig_width * scale_factor)
        scaled_height = int(orig_height * scale_factor)
        
        # Ensure dimensions are even (required for h.264)
        scaled_width = scaled_width if scaled_width % 2 == 0 else scaled_width + 1
        scaled_height = scaled_height if scaled_height % 2 == 0 else scaled_height + 1
        
        logger.info(f"[ASPECT] Scaling video to: {scaled_width}x{scaled_height}")
        logger.info(f"[ASPECT] Padding to: {target_width}x{target_height}")

        # CRITICAL: This actually changes the output resolution!
        scale_and_pad = (
            f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
        )

        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", scale_and_pad,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y", output_path
        ]

        logger.info(f"[ASPECT] Running FFmpeg command...")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # Verify the output resolution
            verify_cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", output_path
            ]
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
            
            if verify_result.returncode == 0:
                info = json.loads(verify_result.stdout)
                actual_width = info.get('streams', [{}])[0].get('width', 0)
                actual_height = info.get('streams', [{}])[0].get('height', 0)
                logger.info(f"[ASPECT] ✅ Output resolution: {actual_width}x{actual_height}")
                
                if actual_width == target_width and actual_height == target_height:
                    logger.info(f"[ASPECT] ✅ SUCCESS! Video resolution changed to {target_width}x{target_height}")
                else:
                    logger.warning(f"[ASPECT] Output resolution {actual_width}x{actual_height} != target {target_width}x{target_height}")
            
            # Update video object
            video.output_path = output_path
            video.aspect_ratio = aspect_ratio
            video_service.update_video(video)
            
            logger.info(f"[ASPECT] ✅ Final output: {output_path}")
            logger.info(f"[ASPECT] ✅ New resolution: {target_width}x{target_height}")
            
            return True
        else:
            logger.error(f"[ASPECT] ❌ FFmpeg error: {result.stderr[:500]}")
            return False

    except Exception as e:
        logger.error(f"[ASPECT] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def _apply_fps(video, fps):
    """Apply FPS change with smart scaling for large videos."""
    import os
    import subprocess
    import json
    import uuid

    try:
        input_path = (
            video.output_path
            if hasattr(video, "output_path") and video.output_path
            else video.original_path
        )

        if not input_path or not os.path.exists(input_path):
            logger.error(f"[FPS] Input path does not exist: {input_path}")
            return False

        # Get original resolution
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        width, height = 1920, 1080
        
        if result.returncode == 0:
            info = json.loads(result.stdout)
            width = info.get('streams', [{}])[0].get('width', 1920)
            height = info.get('streams', [{}])[0].get('height', 1080)
            logger.info(f"[FPS] Original resolution: {width}x{height}")

        # Determine working path (scale down if needed)
        working_path = input_path
        temp_dir = os.path.dirname(input_path)
        temp_files = []

        # 🔥 FORCE SCALE for large videos (>1080p)
        if width > 1920 or height > 1080:
            scaled_path = os.path.join(temp_dir, f"temp_fps_scaled_{uuid.uuid4().hex[:8]}.mp4")
            temp_files.append(scaled_path)
            
            logger.info(f"[FPS] 📐 Scaling {width}x{height} → 1280x720 for processing")
            
            scale_cmd = [
                "ffmpeg", "-i", input_path,
                "-vf", "scale=1280:720",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-c:a", "copy",
                "-y", scaled_path
            ]
            
            scale_result = subprocess.run(scale_cmd, capture_output=True, text=True, timeout=120)
            
            if scale_result.returncode == 0 and os.path.exists(scaled_path):
                working_path = scaled_path
                logger.info(f"[FPS] ✅ Scaled to 720p")
            else:
                logger.warning(f"[FPS] Scaling failed, continuing at original resolution")

        # Apply FPS
        base_name = os.path.splitext(working_path)[0]
        output_path = f"{base_name}_fps_{fps}.mp4"
        temp_files.append(output_path)

        logger.info(f"[FPS] Applying FPS {fps}")

        cmd = [
            "ffmpeg", "-i", working_path,
            "-vf", f"fps={fps}",
            "-c:v", "libx264",
            "-preset", "ultrafast",  # 🔥 Use ultrafast for memory efficiency
            "-crf", "23",            # 🔥 Higher CRF = less memory
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-y", output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # If we scaled, we need to scale back to original resolution
            final_path = output_path
            
            if working_path != input_path and (width > 1920 or height > 1080):
                restore_path = output_path.replace(".mp4", f"_restored.mp4")
                temp_files.append(restore_path)
                
                logger.info(f"[FPS] 🔄 Restoring to original resolution {width}x{height}")
                
                restore_cmd = [
                    "ffmpeg", "-i", output_path,
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-c:a", "copy",
                    "-y", restore_path
                ]
                
                restore_result = subprocess.run(restore_cmd, capture_output=True, text=True, timeout=180)
                
                if restore_result.returncode == 0 and os.path.exists(restore_path):
                    final_path = restore_path
                    logger.info(f"[FPS] ✅ Restored to {width}x{height}")
                else:
                    logger.warning(f"[FPS] Restore failed, keeping processed version")
            
            video.output_path = final_path
            video.fps = fps
            video.output_video_url = final_path
            video_service.update_video(video)
            logger.info(f"[FPS] ✅ Restored to {width}x{height} and set output_url to {final_path}")
            logger.info(f"[FPS] ✅ Success! fps={fps}")
            
            # Cleanup temp files
            for temp_file in temp_files:
                if temp_file != video.output_path and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            
            return True
        else:
            logger.error(f"[FPS] ❌ FFmpeg error: {result.stderr[:300]}")
            return False

    except Exception as e:
        logger.error(f"[FPS] Exception: {e}")
        return False

def _apply_speed(video, speed):
    """
    Apply time remapping (speed change) to video.
    speed < 1.0 = slow motion (longer duration)
    speed > 1.0 = fast motion (shorter duration)
    """
    import os
    import subprocess
    import json

    try:
        # Get current video path
        input_path = video.output_path if hasattr(video, "output_path") and video.output_path else video.original_path

        if not input_path or not os.path.exists(input_path):
            logger.error(f"[SPEED] Input path does not exist: {input_path}")
            return False

        if speed == 1.0 or speed is None:
            logger.info(f"[SPEED] Speed unchanged (1.0x), skipping")
            return True

        # Get original duration for logging
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", input_path
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                original_duration = float(info.get('format', {}).get('duration', 0))
                logger.info(f"[SPEED] Original duration: {original_duration:.2f}s")
        except:
            original_duration = 0

        # Prepare output path
        base_name = os.path.splitext(input_path)[0]
        output_path = f"{base_name}_speed_{speed}x.mp4"

        # FFMPEG COMMAND
        # Using setpts for video and atempo for audio separately
        if speed > 1.0:
            # Fast forward
            video_filter = f"setpts={1.0/speed}*PTS"
            audio_filter = f"atempo={speed}"
            
            cmd = [
                "ffmpeg", "-i", input_path,
                "-vf", video_filter,
                "-af", audio_filter,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-y", output_path
            ]
        else:
            # Slow motion (speed < 1.0)
            # For slow motion, atempo can't go below 0.5, so we need a different approach
            slow_factor = 1.0 / speed  # e.g., 0.5 speed = 2.0 slow_factor
            
            video_filter = f"setpts={slow_factor}*PTS"
            
            # For audio slow motion, we need to chain atempo filters
            # Max atempo is 2.0, so we chain multiple if needed
            remaining = slow_factor
            audio_filters = []
            while remaining > 2.0:
                audio_filters.append("atempo=2.0")
                remaining /= 2.0
            if remaining > 0.5:
                audio_filters.append(f"atempo={remaining}")
            else:
                # If below 0.5, use a different approach
                audio_filters.append(f"atempo=0.5")
            
            audio_filter = ",".join(audio_filters)
            
            cmd = [
                "ffmpeg", "-i", input_path,
                "-vf", video_filter,
                "-af", audio_filter,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-y", output_path
            ]

        logger.info(f"[SPEED] Running: {' '.join(cmd[:10])}...")  # Log first part
        logger.info(f"[SPEED] Speed: {speed}x → Output: {output_path}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # Update video object
            video.output_path = output_path
            video.output_video_url = output_path
            video.speed = speed
            
            # Update duration estimate
            if original_duration > 0:
                video.duration = original_duration / speed if speed != 0 else original_duration
                logger.info(f"[SPEED] New duration: {video.duration:.2f}s")
            
            logger.info(f"[SPEED] ✅ Successfully applied {speed}x speed change")
            return True
        else:
            logger.error(f"[SPEED] ❌ FFmpeg error: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"[SPEED] Timeout expired for speed change")
        return False
    except Exception as e:
        logger.error(f"[SPEED] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    
def _apply_audio_quality(video, quality):
    """Apply audio quality and update output_path - FIXED to actually update video."""
    import os
    import subprocess

    try:
        input_path = video.output_path if hasattr(video, "output_path") and video.output_path else video.original_path

        if not input_path or not os.path.exists(input_path):
            logger.error(f"[AUDIO] Input path does not exist: {input_path}")
            return False

        base_name = os.path.splitext(input_path)[0]
        output_path = f"{base_name}_audio_{quality}.mp4"

        logger.info(f"[AUDIO] Input: {input_path}")
        logger.info(f"[AUDIO] Output: {output_path}")

        bitrate_map = {"128k": "128k", "192k": "192k", "256k": "256k", "320k": "320k"}
        bitrate = bitrate_map.get(quality, "192k")

        cmd = [
            "ffmpeg", "-i", input_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", bitrate,
            "-y", output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # 🔥 CRITICAL: Update ALL output fields
            video.output_path = output_path
            video.audio_quality = quality
            video.output_video_url = output_path
            video.output_video_size = os.path.getsize(output_path)
            video_service.update_video(video)
            
            logger.info(f"[AUDIO] ✅ Success! New output_path: {video.output_path}")
            logger.info(f"[AUDIO] ✅ Updated output_video_url: {video.output_video_url}")
            return True
        else:
            logger.error(f"[AUDIO] ❌ FFmpeg error: {result.stderr[:300]}")
            return False

    except Exception as e:
        logger.error(f"[AUDIO] Exception: {e}")
        return False

def _apply_quality(video, quality):
    """Apply quality scaling while respecting original resolution"""
    import os
    import subprocess

    try:
        input_path = (
            video.output_path
            if hasattr(video, "output_path") and video.output_path
            else video.original_path
        )

        if not input_path or not os.path.exists(input_path):
            logger.error(f"[QUALITY] Input not found: {input_path}")
            return False

        # Get original resolution
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            input_path,
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0 and result.stdout:
            parts = result.stdout.strip().split(",")
            orig_width, orig_height = int(parts[0]), int(parts[1])
        else:
            orig_width, orig_height = 1920, 1080

        logger.info(f"[QUALITY] Original resolution: {orig_width}x{orig_height}")

        # Quality to max dimensions mapping
        quality_max = {
            "480p": (854, 480),
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "2K": (2560, 1440),
            "4k": (3840, 2160),
            "4K+HDR": "3840:2160",
            "8K": "7680:4320",
        }

        max_w, max_h = quality_max.get(quality, (orig_width, orig_height))

        #  NEVER upscale beyond original
        target_width = min(max_w, orig_width)
        target_height = min(max_h, orig_height)

        # If target is same as original, skip
        if target_width >= orig_width and target_height >= orig_height:
            logger.info(
                f"[QUALITY] Target quality {quality} exceeds original, keeping original resolution"
            )
            video.output_quality = quality
            video_service.update_video(video)
            return True

        logger.info(f"[QUALITY] Scaling to {target_width}x{target_height}")

        base_name = os.path.splitext(input_path)[0]
        output_path = f"{base_name}_{quality}.mp4"

        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-vf",
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease",
            "-c:v",
            "libx264",
            "-preset",
            "fast",  # Use "fast" instead of "medium" to reduce memory
            "-crf",
            "23",  # Higher CRF = less memory, still good quality
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-y",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 0
        ):
            video.output_path = output_path
            video.output_quality = quality
            video_service.update_video(video)
            logger.info(f"[QUALITY] ✅ Success!")
            return True
        else:
            logger.error(f"[QUALITY] FFmpeg error: {result.stderr[:500]}")
            return False

    except Exception as e:
        logger.error(f"[QUALITY] Exception: {e}")
        return False


def _generate_chapters(video):
    """Generate chapters."""
    from services.title_service import TitleService

    try:
        title_service = TitleService()
        chapters = title_service.generate_chapters(video.transcription or "", video.id)

        video.chapters = chapters
        logger.info(f"Generated {len(chapters)} chapters for {video.id}")

    except Exception as e:
        logger.error(f"Chapter generation failed: {e}")
        # Chapters are optional, don't fail the process


def _translate_content(video, target_language):
    """Translate content."""
    from providers.google_provider import GoogleProvider

    try:
        provider = GoogleProvider()

        if video.title:
            video.translated_title = provider.translate_text(
                video.title, target_language
            )

        if video.description:
            video.translated_description = provider.translate_text(
                video.description, target_language
            )

        if video.transcription:
            video.translated_transcription = provider.translate_text(
                video.transcription[:5000], target_language
            )

        video.translation_language = target_language

        logger.info(f"Translation completed for {video.id} to {target_language}")

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        # Don't fail the whole process for translation


def _finalize_video(video, options):
    """Finalize video output - SAVE to all needed fields."""
    import os
    import subprocess

    current_path = (
        video.output_path
        if hasattr(video, "output_path") and video.output_path
        else video.original_path
    )

    if not current_path or not os.path.exists(current_path):
        logger.error(f"[FINAL] Current path does not exist: {current_path}")
        return None

    logger.info(f"[FINAL] Starting with: {current_path}")
    logger.info(f"[FINAL] User settings: aspect={video.aspect_ratio}, fps={video.fps}, audio={video.audio_quality}")

    quality = getattr(video, "output_quality", options.get("quality", "720p"))

    # Apply quality if specified
    if quality and quality != "original":
        base_name = os.path.splitext(current_path)[0]
        quality_path = f"{base_name}_{quality}.mp4"

        logger.info(f"[FINAL] Applying quality {quality}")

        quality_resolutions = {
            "480p": "854:480",
            "720p": "1280:720",
            "1080p": "1920:1080",
            "2K": "2560:1440",
            "4k": "3840:2160",
            "4K+HDR": "3840:2160",
            "8K": "7680:4320",
        }

        resolution = quality_resolutions.get(quality, "1280:720")

        cmd = [
            "ffmpeg",
            "-i",
            current_path,
            "-vf", f"scale={resolution}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-y", quality_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0 and os.path.exists(quality_path):
                current_path = quality_path
                video.output_quality = quality
                logger.info(f"[FINAL] ✅ Quality {quality} applied")
            else:
                logger.warning(f"[FINAL] Quality change failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"[FINAL] Quality change error: {e}")

    # Save the final path to ALL relevant fields
    video.output_path = current_path
    video.output_video_url = current_path
    video.output_video_size = os.path.getsize(current_path) if os.path.exists(current_path) else 0
    
    # Update the database immediately
    video_service.update_video(video)
    
    logger.info(f"[FINAL] ✅ Final video: {video.output_path}")
    logger.info(f"[FINAL] ✅ File size: {video.output_video_size} bytes")
    logger.info(f"[FINAL] ✅ Final settings: quality={video.output_quality}, aspect={video.aspect_ratio}, fps={video.fps}, audio={video.audio_quality}")

    return current_path


def _get_quality_resolution(quality):
    """Get resolution string for quality."""
    quality_map = {
        "480p": "854:480",
        "720p": "1280:720",
        "1080p": "1920:1080",
        "2K": "2560:1440",
        "4k": "3840:2160",
        "4K+HDR": "3840:2160",
        "8K": "7680:4320",
    }
    return quality_map.get(quality, "1280:720")


# existing functions (process_video_batch, retry_failed_videos, etc.)
@celery_app.task
def process_video_batch(
    video_ids: List[str], user_id: str, options: Dict[str, Any] = None
):
    """
    Process multiple videos in batch.

    Args:
        video_ids: List of video IDs
        user_id: User ID
        options: Processing options
    """
    options = options or {}
    results = []

    for video_id in video_ids:
        try:
            result = process_video_async.delay(video_id, user_id, options)
            results.append(
                {"video_id": video_id, "task_id": result.id, "status": "queued"}
            )
        except Exception as e:
            logger.error(f"Failed to queue video {video_id} for processing: {str(e)}")
            results.append({"video_id": video_id, "error": str(e), "status": "failed"})

    return {
        "total": len(video_ids),
        "queued": len([r for r in results if r["status"] == "queued"]),
        "failed": len([r for r in results if r["status"] == "failed"]),
        "results": results,
    }


@celery_app.task
def retry_failed_videos():
    """Retry videos that failed processing."""
    from providers.firebase_provider import FirebaseProvider

    db = FirebaseProvider()

    # Find videos that failed and can be retried
    failed_videos = db.query(
        "videos", filters={"status": "failed", "retry_count": {"$lt": 3}}
    )

    retried_count = 0

    for video_data in failed_videos:
        video_id = video_data["id"]
        user_id = video_data["user_id"]

        try:
            # Update retry count
            new_retry_count = video_data.get("retry_count", 0) + 1
            db.save(
                "videos",
                video_id,
                {
                    "retry_count": new_retry_count,
                    "status": "queued",
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

            # Queue for retry
            process_video_async.delay(video_id, user_id)
            retried_count += 1

            logger.info(f"Retrying video {video_id} (attempt {new_retry_count})")

        except Exception as e:
            logger.error(f"Failed to retry video {video_id}: {str(e)}")

    logger.info(f"Retried {retried_count} failed videos")
    return {"retried_count": retried_count}


@celery_app.task
def update_video_status(
    video_id: str, status: str, progress: float = 0.0, message: str = ""
):
    """Update video processing status."""
    from providers.firebase_provider import FirebaseProvider

    db = FirebaseProvider()

    updates = {"status": status, "updated_at": datetime.utcnow().isoformat()}

    if progress > 0:
        updates["progress"] = progress

    if message:
        updates["error_message"] = message

    db.save("videos", video_id, updates)
    video_data = db.get("videos", video_id)
    user_id = video_data.get("user_id")

    # # Emit WebSocket update
    # try:
    #     from api.websocket import socketio

    #     if socketio:
    #         socketio.emit(
    #             "video_status_update",
    #             {
    #                 "video_id": video_id,
    #                 "status": status,
    #                 "progress": progress,
    #                 "timestamp": datetime.utcnow().isoformat(),
    #             },
    #             room=user_id,
    #         )
    # except Exception as e:
    #     logger.warning(f"WebSocket emit failed: {e}")


@celery_app.task
def schedule_video_deletion(video_id: str, delay_hours: int):
    """Schedule video for deletion after delay."""
    import time
    from providers.firebase_provider import FirebaseProvider

    db = FirebaseProvider()

    # Wait for delay
    time.sleep(delay_hours * 3600)

    # Mark video for deletion
    db.save(
        "videos",
        video_id,
        {
            "scheduled_for_deletion": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        },
    )

    # Actually delete the video (in production, this would be a separate cleanup task)
    video_data = db.get("videos", video_id)
    if video_data:
        user_id = video_data.get("user_id")

        # Delete from storage
        from services.storage_service import StorageService

        storage_service = StorageService()

        if video_data.get("output_video_url"):
            storage_service.delete_video(video_data["output_video_url"])

        # Mark as deleted in database
        db.save(
            "videos",
            video_id,
            {
                "is_deleted": True,
                "deleted_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

        logger.info(f"Deleted video {video_id} for user {user_id}")


@celery_app.task
def generate_video_preview(video_id: str, timestamp: float, output_path: str):
    """Generate video preview at specific timestamp."""
    from providers.firebase_provider import FirebaseProvider
    from providers.ffmpeg_provider import FFmpegProvider

    db = FirebaseProvider()
    ffmpeg = FFmpegProvider()

    video_data = db.get("videos", video_id)
    if not video_data:
        return {"success": False, "error": "Video not found"}

    original_path = video_data.get("original_path")
    if not original_path:
        return {"success": False, "error": "Original video path not found"}

    try:
        # Extract frame
        preview_path = ffmpeg.extract_frame(
            video_path=original_path,
            timestamp=timestamp,
            output_dir=os.path.dirname(output_path),
            filename=os.path.basename(output_path).replace(".jpg", ""),
        )

        if preview_path:
            return {
                "success": True,
                "preview_path": preview_path,
                "video_id": video_id,
                "timestamp": timestamp,
            }
        else:
            return {"success": False, "error": "Failed to extract frame"}

    except Exception as e:
        logger.error(f"Failed to generate preview for video {video_id}: {str(e)}")
        return {"success": False, "error": str(e)}


@celery_app.task
def analyze_video_content(video_id: str):
    """Analyze video content for metadata extraction."""
    from providers.firebase_provider import FirebaseProvider
    from providers.ffmpeg_provider import FFmpegProvider

    db = FirebaseProvider()
    ffmpeg = FFmpegProvider()

    video_data = db.get("videos", video_id)
    if not video_data:
        return {"success": False, "error": "Video not found"}

    original_path = video_data.get("original_path")
    if not original_path:
        return {"success": False, "error": "Original video path not found"}

    try:
        # Get video metadata
        metadata = ffmpeg.get_video_metadata(original_path)

        # Detect silent segments
        silent_segments = ffmpeg.detect_silent_segments(original_path)

        # Extract key frames
        duration = metadata.get("duration", 60)
        timestamps = [duration * 0.25, duration * 0.5, duration * 0.75]  # 25%, 50%, 75%

        # Update video with analysis results
        updates = {
            "metadata": metadata,
            "silent_segments": silent_segments,
            "key_frame_timestamps": timestamps,
            "updated_at": datetime.utcnow().isoformat(),
        }

        db.save("videos", video_id, updates)

        return {
            "success": True,
            "video_id": video_id,
            "metadata": metadata,
            "silent_segments_count": len(silent_segments),
            "key_frames": len(timestamps),
        }

    except Exception as e:
        logger.error(f"Failed to analyze video {video_id}: {str(e)}")
        return {"success": False, "error": str(e)}
