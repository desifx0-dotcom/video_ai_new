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


try:
    from api.websocket import socketio
except ImportError:
    socketio = None
    logger.warning("SocketIO not available - WebSocket updates disabled")


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
    Process video asynchronously - PRODUCTION OPTIMIZED.
    
    Processing order:
    1. Metadata & AI generation (silent/speech detection, transcription, metadata, thumbnails)
    2. ALL video filters applied in SINGLE PASS (speed, fps, styles, quality, aspect ratio)
    """
    options = options or {}
    from services.user_service import UserService

    # Check if video is already being processed
    video = video_service.get_video_by_id(video_id)
    if video and video.status == "processing":
        processing_started = video.processing_started
        if processing_started:
            elapsed = (datetime.utcnow() - processing_started).total_seconds()
            if elapsed > 600:  # 900 seconds 10 minutes
                logger.warning(f"Video {video_id} has been processing for {elapsed}s, marking as failed")
                video.status = "failed"
                video.error_message = "Processing timeout"
                video_service.update_video(video)
                return {"success": False, "video_id": video_id, "error": "Processing timeout"}

    # Log received options
    logger.info("=" * 80)
    logger.info(f"📥 VIDEO PROCESSING STARTED for {video_id}")
    logger.info(f"📥 User ID: {user_id}")
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

        # INITIAL STATUS - QUEUED
        video_service.update_processing_status(video_id, "queued", 5, "queued")
        
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"current": "starting", "total": 100, "status": "Initializing..."}
        )

        # STATUS - ANALYZING
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
        else:
            video.speed = 1.0
        
        # 1.2 FPS
        if options.get("fps") and options["fps"] != "original":
            video.fps = options["fps"]
            logger.info(f"✅ Setting FPS: {options['fps']}")
            settings_changed = True
        else:
            video.fps = "original"

        # 1.3 Audio Quality
        if options.get("audio_quality") and options["audio_quality"] != "original":
            video.audio_quality = options["audio_quality"]
            logger.info(f"✅ Setting audio quality: {options['audio_quality']}")
            settings_changed = True
        else:
            video.audio_quality = "original"

        # 1.4 Output Quality
        if options.get("quality") and options["quality"] != "original":
            video.output_quality = options["quality"]
            logger.info(f"✅ Setting output quality: {options['quality']}")
            settings_changed = True
        else:
            video.output_quality = "original"

        # 1.5 Thumbnail Style (metadata only)
        if options.get("thumbnail_style"):
            video.thumbnail_style = options["thumbnail_style"]
            logger.info(f"✅ Setting thumbnail style: {options['thumbnail_style']}")
            settings_changed = True
        else:
            video.thumbnail_style = "default"

        # 1.6 Video Styles
        if options.get("styles") and len(options["styles"]) > 0:
            video.applied_styles = options["styles"]
            logger.info(f"✅ Setting video styles: {options['styles']}")
            settings_changed = True
        else:
            video.applied_styles = []

        # 1.7 Aspect Ratio (save for last)
        if options.get("aspect_ratio") and options["aspect_ratio"] != "original":
            video.aspect_ratio = options["aspect_ratio"]
            logger.info(f"✅ Setting aspect ratio (will apply last): {options['aspect_ratio']}")
            settings_changed = True
        else:
            video.aspect_ratio = "original"

        # Save all settings to database
        if settings_changed:
            video_service.update_video(video)
            logger.info(f"💾 Saved video settings to database")

        # ========== STEP 2: SILENT VIDEO OR TRANSCRIPTION ==========
        _send_ws_update(video_id, user_id, "processing", 10, "analyzing", "Analyzing video...")
        self.update_state(state="PROGRESS", meta={"current": "analyzing", "total": 100, "status": "Analyzing video..."})

        video_type = options.get("video_type", "speech")

        if options.get("process_silent_video") or video_type == "silent":
            logger.info(f"Processing silent video: {video_id}")
            video_service.update_processing_status(video_id, "processing", 20, "silent_analysis")
            _send_ws_update(video_id, user_id, "processing", 20, "silent_analysis", "Analyzing silent video content...")
            _process_silent_video(video, options)
        else:
            if video_type == "speech" and options.get("auto_transcribe", True):
                video_service.update_processing_status(video_id, "processing", 30, "transcribing")
                _send_ws_update(video_id, user_id, "processing", 25, "transcribing", "Transcribing audio...")
                self.update_state(state="PROGRESS", meta={"current": "transcribing", "total": 100, "status": "Transcribing audio..."})
                _transcribe_video(video, options)

        # ========== STEP 3: GENERATE METADATA ==========
        video_service.update_processing_status(video_id, "processing", 40, "metadata")
        _send_ws_update(video_id, user_id, "processing", 35, "generating_metadata", "Generating title and description...")
        self.update_state(state="PROGRESS", meta={"current": "metadata", "total": 100, "status": "Generating metadata..."})
        _generate_metadata(video, options)

        # ========== STEP 4: GENERATE THUMBNAILS ==========
        video_service.update_processing_status(video_id, "processing", 50, "thumbnails")
        _send_ws_update(video_id, user_id, "processing", 45, "generating_thumbnails", "Creating thumbnails...")
        self.update_state(state="PROGRESS", meta={"current": "thumbnails", "total": 100, "status": "Generating thumbnails..."})
        _generate_thumbnails(video, options, user_id)

        # ========== STEP 5: APPLY ALL VIDEO FILTERS (SINGLE PASS) ==========
        video_service.update_processing_status(video_id, "processing", 85, "applying_filters")
        _send_ws_update(video_id, user_id, "processing", 85, "applying_filters", "Applying video effects...")
        self.update_state(state="PROGRESS", meta={"current": "applying_filters", "total": 100, "status": "Applying video effects..."})

        try:
            output_path = _apply_all_filters_production(video, options)
            
            if not output_path:
                # FAIL FAST - specific error message
                error_msg = f"Video filter application failed at stage: {getattr(video, '_last_failed_stage', 'unknown')}"
                logger.error(f"[MASTER] {error_msg}")
                raise ProcessingError(error_msg)
                
        except Exception as filter_error:
            logger.error(f"[MASTER] Filter application failed: {filter_error}")
            # Update video status to failed with clear reason
            video.status = "failed"
            video.error_message = str(filter_error)
            video_service.update_video(video)
            _send_ws_failed(video_id, user_id, str(filter_error), self.request.retries, self.request.retries < self.max_retries)
            raise ProcessingError(f"Video processing failed during filter application: {filter_error}")

        # ========== STEP 6: COMPLETE ==========
        video.status = "completed"
        video.processing_completed = datetime.utcnow()
        if video.processing_started:
            video.processing_time = (video.processing_completed - video.processing_started).total_seconds()
        video.output_video_url = output_path
        video.output_path = output_path
        video.output_video_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        
        video_service.update_video(video)

         #Deduct credits AFTER successful processing
        try:
            from services.credit_service import CreditService
            credit_service = CreditService()
            
            # Get user to check current credits
            user = user_service.get_user_by_id(user_id)
            
            # Calculate credits needed (1 credit per video, or based on duration)
            # Using 1 credit per video for simplicity
            credits_needed = 1
            
            if user.credits_remaining >= credits_needed:
                credit_service.use_credits(
                    user_id=user_id,
                    amount=credits_needed,
                    description=f"Video processing completed: {video.original_filename}",
                    video_id=video_id,
                    operation="video_processing"
                )
                logger.info(f"✅ Deducted {credits_needed} credit(s) from user {user_id} for video {video_id}")
                logger.info(f"💰 Credits remaining: {user.credits_remaining - credits_needed}")
            else:
                logger.warning(f"⚠️ User {user_id} has insufficient credits ({user.credits_remaining}) for processing")
                # Still mark as completed, but log warning for manual review
                
        except Exception as e:
            logger.error(f"Failed to deduct credits for video {video_id}: {e}")
            # Don't fail the processing - credit deduction error shouldn't block completion


        # Log final settings
        logger.info("=" * 80)
        logger.info(f"✅ VIDEO PROCESSING COMPLETED for {video_id}")
        logger.info(f"📊 Final video settings:")
        logger.info(f"   quality: {video.output_quality}")
        logger.info(f"   fps: {video.fps}")
        logger.info(f"   audio_quality: {video.audio_quality}")
        logger.info(f"   aspect_ratio: {video.aspect_ratio}")
        logger.info(f"   speed: {getattr(video, 'speed', 1.0)}x")
        logger.info(f"   styles: {video.applied_styles}")
        logger.info(f"   output_path: {output_path}")
        logger.info(f"   output_size: {video.output_video_size:,} bytes")
        logger.info("=" * 80)

        # Send completion notification
        _send_ws_completed(video_id, user_id, video.output_video_url, video.processing_time, video.total_cost)

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
        logger.error(f"Unexpected error in video processing: {str(e)}")
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

def _apply_all_filters_production(video, options):
    """
    MULTI-PASS: Apply filters in stages with PROPER error handling.
    ANY stage failure causes complete failure - no silent fallbacks.
    """
    import os
    import subprocess
    import json
    import shutil

    logger.info("=" * 80)
    logger.info("[MASTER] 🎬 MULTI-PASS FILTER APPLICATION")
    logger.info(f"[DEBUG] Before applying filters - video attributes:")
    logger.info(f"   quality: {video.output_quality}")
    logger.info(f"   fps: {video.fps}")
    logger.info(f"   speed: {getattr(video, 'speed', 1.0)}")
    logger.info(f"   styles: {video.applied_styles}")
    logger.info(f"   aspect_ratio: {getattr(video, 'aspect_ratio', 'original')}")
        
    video._last_failed_stage = None
    input_path = video.original_path
    if not input_path or not os.path.exists(input_path):
        logger.error(f"[MASTER] Input not found: {input_path}")
        return None

    # Validate FFmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception as e:
        logger.error(f"[MASTER] FFmpeg not available: {e}")
        return None

    # ========== 1. COLLECT ALL FEATURES ==========
    video_short_id = video.id[:8]

    quality = getattr(video, 'output_quality', 'original')
    aspect_ratio = getattr(video, 'aspect_ratio', 'original')
    speed = getattr(video, 'speed', 1.0)
    fps = getattr(video, 'fps', 'original')
    styles = getattr(video, 'applied_styles', [])
    audio_quality = getattr(video, 'audio_quality', 'original')

    # ========== 2. APPLY FILTERS IN STAGES ==========
    current_input = input_path
    temp_files = []

    # Stage 1: Apply SPEED (if needed)
    if speed != 1.0:
        temp_speed = os.path.join(os.path.dirname(input_path), f"temp_speed_{video_short_id}.mp4")
        temp_files.append(temp_speed)
        
        speed_factor = 1.0 / speed
        tempo_factor = speed
        
        logger.info(f"[MASTER] Stage 1: Applying speed {speed}x")
        
        # Check if video has audio stream
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "json",
            current_input
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        has_audio = False
        if probe_result.returncode == 0 and probe_result.stdout.strip():
            try:
                data = json.loads(probe_result.stdout)
                has_audio = len(data.get('streams', [])) > 0
            except:
                pass
        
        if not has_audio:
            cmd = [
                "ffmpeg", "-i", current_input,
                "-filter:v", f"setpts={speed_factor}*PTS",
                "-an",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-y", temp_speed
            ]
        else:
            if tempo_factor < 0.5:
                num_filters = int(1 / tempo_factor)
                audio_filter = ",".join(["atempo=0.5"] * num_filters)
                logger.info(f"Using chained audio filter: {audio_filter}")
            elif tempo_factor > 2.0:
                first_factor = 2.0
                second_factor = tempo_factor / 2.0
                audio_filter = f"atempo={first_factor},atempo={second_factor}"
                logger.info(f"Using chained audio filter: {audio_filter}")
            else:
                audio_filter = f"atempo={tempo_factor}"
            
            cmd = [
                "ffmpeg", "-i", current_input,
                "-filter_complex", f"[0:v]setpts={speed_factor}*PTS[v];[0:a]{audio_filter}[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-y", temp_speed
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"[MASTER] Speed stage FAILED: {result.stderr[:500]}")
            video._last_failed_stage = "speed"
            return None  #  FAIL FAST - don't continue
        
        if os.path.exists(temp_speed) and os.path.getsize(temp_speed) > 0:
            current_input = temp_speed
            logger.info(f"[MASTER] ✅ Speed {speed}x applied")
        else:
            logger.error(f"[MASTER] Speed output file is empty or missing!")
            return None

    # Stage 2: Apply FPS (if needed)
    if fps and fps != 'original' and str(fps).isdigit():
        temp_fps = os.path.join(os.path.dirname(input_path), f"temp_fps_{video_short_id}.mp4")
        temp_files.append(temp_fps)
        
        logger.info(f"[MASTER] Stage 2: Applying FPS {fps}")
        
        cmd = [
            "ffmpeg", "-i", current_input,
            "-vf", f"fps={fps}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            "-y", temp_fps
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"[MASTER] FPS stage FAILED: {result.stderr[:500]}")
            video._last_failed_stage = "fps"
            return None
        
        current_input = temp_fps
        logger.info(f"[MASTER] ✅ FPS applied")

    # Stage 3: Apply VIDEO STYLES
    style_filters = {
        # ========== FREE TIER STYLES ==========
        "cinematic": "eq=brightness=0.05:contrast=1.15:saturation=1.1,unsharp=5:5:0.8",
        "bright": "eq=brightness=0.12:contrast=1.08:saturation=1.2",
        "educational": "eq=brightness=0.03:contrast=1.1:saturation=1.05,unsharp=3:3:0.5",
        "vlog": "eq=brightness=0.08:contrast=1.02:saturation=1.08,colorbalance=rs=0.02:gs=0.01:bs=-0.02",
        
        # Starter tier
        "gaming": "eq=saturation=1.25:contrast=1.15:brightness=0.03,unsharp=5:5:1.0,colorbalance=rs=0.05:gs=0.03:bs=-0.02",
        "travel": "eq=saturation=1.18:contrast=1.05:brightness=0.05,colorbalance=rs=0.03:gs=0.02:bs=0.04",
        
        # Pro tier
        "dark": "eq=brightness=-0.1:contrast=1.18:saturation=0.88,colorbalance=gs=-0.04",
        "professional": "eq=contrast=1.08:saturation=0.98,unsharp=3:3:0.4",
        "documentary": "eq=brightness=0:contrast=1.02:saturation=0.95,colorbalance=rs=-0.02:gs=-0.01:bs=-0.01",
        "wedding": "eq=brightness=0.07:contrast=1.02:saturation=1.05,colorbalance=rs=0.04:gs=0.02:bs=0.03",
        "corporate": "eq=brightness=0.03:contrast=1.08:saturation=0.98,unsharp=2:2:0.3",
        "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.06,unsharp=4:4:0.6",
        "action": "eq=contrast=1.2:brightness=0.03,unsharp=5:5:1.2,eq=saturation=1.1",
        "minimalist": "eq=saturation=0.92:contrast=1.05,unsharp=2:2:0.2",
        "vintage": "eq=brightness=0.02:contrast=0.92:saturation=0.88,colorbalance=rs=-0.03:gs=-0.02:bs=0.05",
        
        # Plus tier
        "cinematic_pro": "eq=brightness=0.06:contrast=1.2:saturation=1.12,unsharp=5:5:1.0,colorbalance=rs=0.02:gs=0.01:bs=-0.01",
        "artistic": "eq=saturation=1.2:contrast=1.08:brightness=0.03,unsharp=4:4:0.8,colorbalance=rs=0.04:gs=0.02:bs=0.06",
        "retro": "eq=brightness=0.02:contrast=0.92:saturation=0.85,colorbalance=rs=-0.04:gs=-0.03:bs=0.08",
        "futuristic": "eq=saturation=1.25:contrast=1.15:brightness=0.04,unsharp=5:5:1.0,colorbalance=rs=0.06:gs=0.04:bs=0.1",
        "cartoon": "eq=saturation=1.2:contrast=1.1,edgedetect=low=0.1:high=0.3,unsharp=3:3:0.5",
        "glamour": "eq=brightness=0.05:contrast=1.02:saturation=1.1,unsharp=4:4:0.7,colorbalance=rs=0.05:gs=0.03:bs=0.03",
        "mystery": "eq=brightness=-0.05:contrast=1.15:saturation=0.92,colorbalance=gs=-0.04,unsharp=3:3:0.5",
        "tech": "eq=saturation=1.18:contrast=1.12:brightness=0.03,unsharp=5:5:0.9,colorbalance=rs=0.06:gs=0.04:bs=0.09",
        "dramatic": "eq=brightness=-0.03:contrast=1.25:saturation=1.1,unsharp=5:5:1.2",
        "warm": "eq=brightness=0.04:contrast=1.02:saturation=1.05,colorbalance=rs=0.06:gs=0.02:bs=-0.03",
        "cool": "eq=brightness=0.02:contrast=1.03:saturation=1.02,colorbalance=rs=-0.02:gs=0:bs=0.05",
        "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
        "black_and_white": "hue=s=0,eq=contrast=1.1",
        "text_heavy": "eq=brightness=0.02:contrast=1.2:saturation=1.05,unsharp=3:3:0.8",
        
        # Enterprise tier
        "hollywood": "eq=brightness=0.04:contrast=1.18:saturation=1.15,unsharp=5:5:1.1,colorbalance=rs=0.03:gs=0.02:bs=-0.02",
        "dreamy": "eq=brightness=0.06:contrast=1.02:saturation=1.08,unsharp=3:3:0.4,colorbalance=rs=0.04:gs=0.03:bs=0.07",
        "neon": "eq=saturation=1.3:contrast=1.2:brightness=0.05,colorbalance=rs=0.08:gs=0.05:bs=0.12,unsharp=4:4:0.8",
        "pastel": "eq=saturation=0.85:contrast=1.02:brightness=0.07,colorbalance=rs=0.02:gs=0.02:bs=0.02",
        "hdr": "eq=contrast=1.15:saturation=1.12,brightness=0.02,unsharp=5:5:1.0",
    }




    if styles:
        for style in styles:
            if style in style_filters:
                temp_style = os.path.join(os.path.dirname(input_path), f"temp_style_{style}_{video_short_id}.mp4")
                temp_files.append(temp_style)
                
                filter_str = style_filters[style]
                logger.info(f"[MASTER] Stage 3: Applying style '{style}'")
                
                cmd = [
                    "ffmpeg", "-i", current_input,
                    "-vf", filter_str,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy",
                    "-y", temp_style
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    logger.error(f"[MASTER] Style '{style}' stage FAILED: {result.stderr[:500]}")
                    video._last_failed_stage = "video_styles"
                    return None
                
                current_input = temp_style
                logger.info(f"[MASTER] ✅ Style '{style}' applied")

    # Stage 4: Apply QUALITY scaling
    quality_map = {"480p": 480, "720p": 720, "1080p": 1080}
    if quality in quality_map:
        target_height = quality_map[quality]
        
        # Get current height
        probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=height", "-of", "json", current_input]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        current_height = 1080
        if probe_result.returncode == 0:
            info = json.loads(probe_result.stdout)
            current_height = info.get('streams', [{}])[0].get('height', 1080)
        
        if target_height < current_height:
            temp_quality = os.path.join(os.path.dirname(input_path), f"temp_quality_{video_short_id}.mp4")
            temp_files.append(temp_quality)
            
            logger.info(f"[MASTER] Stage 4: Scaling to {quality}")
            
            cmd = [
                "ffmpeg", "-i", current_input,
                "-vf", f"scale=-2:{target_height}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "copy",
                "-y", temp_quality
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"[MASTER] Quality scaling stage FAILED: {result.stderr[:500]}")
                video._last_failed_stage = "audio_quality"
                return None
            
            current_input = temp_quality
            logger.info(f"[MASTER] ✅ Quality applied")

    # Stage 5: Apply ASPECT RATIO
    aspect_dimensions = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
        "2:3": (1080, 1620),
    }

    if aspect_ratio in aspect_dimensions:
        target_w, target_h = aspect_dimensions[aspect_ratio]
        temp_aspect = os.path.join(os.path.dirname(input_path), f"temp_aspect_{video_short_id}.mp4")
        temp_files.append(temp_aspect)
        
        logger.info(f"[MASTER] Stage 5: Applying aspect ratio {aspect_ratio}")
        
        cmd = [
            "ffmpeg", "-i", current_input,
            "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-y", temp_aspect
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"[MASTER] Aspect ratio stage FAILED: {result.stderr[:500]}")
            video._last_failed_stage = "aspect_ratio"
            return None
        
        current_input = temp_aspect
        logger.info(f"[MASTER] ✅ Aspect ratio applied")

    # ========== 3. FINAL OUTPUT ==========
    final_filename = f"final_{video_short_id}.mp4"
    final_path = os.path.join(os.path.dirname(input_path), final_filename)
    
    shutil.copy2(current_input, final_path)
    
    # Clean up temp files
    for temp_file in temp_files:
        if os.path.exists(temp_file) and temp_file != final_path:
            try:
                os.remove(temp_file)
                logger.info(f"[CLEANUP] Deleted: {os.path.basename(temp_file)}")
            except:
                pass
    
    # Update video object
    video.output_path = final_path
    video.output_video_url = final_path
    video.output_video_size = os.path.getsize(final_path)
    video_service.update_video(video)
    
    logger.info(f"[MASTER] ✅ FINAL OUTPUT: {final_filename}")
    logger.info(f"[MASTER] ✅ File size: {video.output_video_size:,} bytes")
    
    return final_path

def _copy_to_final_location(video, output_path, input_path):
    """Copy final output and clean up temp files - PRESERVING the filtered output."""
    import os
    import glob
    import shutil

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        logger.error(f"[MASTER] Output file missing or empty: {output_path}")
        return None

    # Ensure output is in the correct location
    final_dir = os.path.dirname(input_path)
    final_path = os.path.join(final_dir, os.path.basename(output_path))

    if output_path != final_path:
        shutil.copy2(output_path, final_path)
        logger.info(f"[MASTER] ✅ Copied to final location: {os.path.basename(final_path)}")
    else:
        final_path = output_path

    # Only delete TEMP files, NOT the final output
    # Temp files are those created in temp directories, not in the video's own directory
    temp_pattern = os.path.join(os.path.dirname(input_path), f"*_temp_*.mp4")

    for temp_file in glob.glob(temp_pattern):
        if temp_file != final_path and temp_file != input_path:
            try:
                os.remove(temp_file)
                logger.info(f"[CLEANUP] Deleted temp: {os.path.basename(temp_file)}")
            except:
                pass

    # clean up any files in system temp directory
    import tempfile
    system_temp = tempfile.gettempdir()
    temp_pattern_system = os.path.join(system_temp, f"*{video.id[:8]}*.mp4")
    for temp_file in glob.glob(temp_pattern_system):
        if temp_file != final_path:
            try:
                os.remove(temp_file)
                logger.info(f"[CLEANUP] Deleted system temp: {os.path.basename(temp_file)}")
            except:
                pass

    # Update video object
    video.output_path = final_path
    video.output_video_url = final_path
    video.output_video_size = os.path.getsize(final_path)
    video_service.update_video(video)

    # Set final status
    video_service.update_processing_status(video.id, "completed", 100, "completed")

    logger.info(f"[MASTER] ✅ FINAL OUTPUT: {os.path.basename(final_path)}")
    logger.info(f"[MASTER] ✅ File size: {video.output_video_size:,} bytes")

    return final_path

def _cleanup_duplicate_files(video, final_path, original_path):
    """Clean up duplicate intermediate files created by previous processing."""
    import os
    import glob
    import shutil
    
    try:
        base_dir = os.path.dirname(original_path)
        video_id_pattern = video.id[:8]
        
        # Find all files related to this video
        pattern = os.path.join(base_dir, f"*{video_id_pattern}*.mp4")
        all_files = glob.glob(pattern)
        
        deleted_count = 0
        for file_path in all_files:
            # Keep only original and final output
            if file_path == original_path or file_path == final_path:
                continue
            try:
                os.remove(file_path)
                deleted_count += 1
                logger.info(f"[CLEANUP] Deleted: {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"[CLEANUP] Failed to delete {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"[CLEANUP] Deleted {deleted_count} intermediate files")
            
    except Exception as e:
        logger.warning(f"[CLEANUP] Error during cleanup: {e}")

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

# ========== QUICK ACTIONS ENDPOINTS ==========

def _get_audio_bitrate(self, audio_quality: str) -> str:
    """Get audio bitrate based on quality setting."""
    bitrate_map = {
        "original": "128k",
        "128k": "128k",
        "192k": "192k",
        "256k": "256k",
        "320k": "320k",
    }
    return bitrate_map.get(audio_quality, "128k")

@celery_app.task(bind=True, max_retries=2)
def apply_different_styles_async(self, video_id: str, user_id: str, styles: List[str], output_quality: str = "720p"):
    """
    Apply different video styles to the video while preserving ALL user settings.
    Uses ORIGINAL video for styling, then restores to processed dimensions.
    """
    from services.video_service import VideoService
    from providers.ffmpeg_provider import FFmpegProvider
    import subprocess
    import json
    import os
    from datetime import datetime
    from pathlib import Path
    
    video_service = VideoService()
    ffmpeg = FFmpegProvider()
    
    try:
        # Get video
        video = video_service.get_video_by_id(video_id)
        if not video:
            raise ProcessingError(f"Video not found: {video_id}")
        
        # ========== USE ORIGINAL VIDEO ==========
        input_path = video.original_path
        if not input_path or not os.path.exists(input_path):
            raise ProcessingError(f"Original video file not found: {input_path}")
        
        # ========== GET PROCESSED VIDEO DIMENSIONS ==========
        target_width = None
        target_height = None
        processed_path = video.output_video_url
        
        if processed_path and os.path.exists(processed_path):
            probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", processed_path]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            if probe_result.returncode == 0:
                info = json.loads(probe_result.stdout)
                for stream in info.get("streams", []):
                    if stream.get("codec_type") == "video":
                        target_width = stream.get("width", 1920)
                        target_height = stream.get("height", 1080)
                        break
        
        # Fallback to quality settings
        if not target_width or not target_height:
            quality_map = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}
            target_width, target_height = quality_map.get(video.output_quality, (1920, 1080))
        
        # ========== GET PRESERVATION SETTINGS ==========
        preserve_settings = {
            "fps": getattr(video, 'fps', 'original'),
            "audio_quality": getattr(video, 'audio_quality', 'original'),
            "aspect_ratio": getattr(video, 'aspect_ratio', 'original'),
        }
        
        # ========== CREATE OUTPUT DIRECTORY ==========
        output_dir = os.path.dirname(input_path)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results = []
        
        for style in styles:
            output_filename = f"{video_id}_{style}_{timestamp}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            # Apply style with target dimensions and preserve settings
            success = ffmpeg.apply_video_style(
                input_path=input_path,
                output_path=output_path,
                style=style,
                target_width=target_width,
                target_height=target_height,
                preserve_settings=preserve_settings
            )
            
            if success and os.path.exists(output_path):
                results.append({
                    "style": style,
                    "output_path": output_path,
                    "output_url": output_path,
                    "file_size": os.path.getsize(output_path)
                })
                logger.info(f"✅ Applied style '{style}' to video {video_id}")
            else:
                logger.error(f"❌ Failed to apply style '{style}' to video {video_id}")
        
        # Update video with new styled version
        if results:
            first_result = results[0]
            video.output_video_url = first_result["output_url"]
            video.output_path = first_result["output_path"]
            video.output_video_size = first_result["file_size"]
            video.applied_styles = styles
            video.updated_at = datetime.utcnow()
            video_service.update_video(video)
        
        return {
            "success": True,
            "video_id": video_id,
            "styles_applied": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Apply styles failed for {video_id}: {str(e)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        
        return {"success": False, "video_id": video_id, "error": str(e)}
    
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
