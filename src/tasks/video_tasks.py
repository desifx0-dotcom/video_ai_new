"""
Video processing Celery tasks.
"""

import os
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List

from .celery_app import celery_app
from services.video_service import VideoService
from services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationChannel,
)
from core.exceptions import ProcessingError
from app.monitoring.metrics import record_video_processing

logger = logging.getLogger(__name__)

video_service = VideoService()


@celery_app.task(bind=True, max_retries=3)
def process_video_async(
    self, video_id: str, user_id: str, options: Dict[str, Any] = None
):
    """
    Process video asynchronously.

    Args:
        video_id: Video ID
        user_id: User ID
        options: Processing options (quality, style, aspect_ratio, etc.)
    """
    from services.notification_service import (
        NotificationService,
        NotificationType,
        NotificationChannel,
    )
    from services.user_service import UserService
    from providers.ffmpeg_provider import FFmpegProvider
    import tempfile
    import subprocess
    import shutil

    notification_service = NotificationService()
    user_service = UserService()
    ffmpeg = FFmpegProvider()
    options = options or {}

    send_email_notification = options.get("send_email_notification", False)

    try:
        logger.info(
            f"Starting video processing for video_id: {video_id}, user_id: {user_id}"
        )
        logger.info(f"Processing options: {options}")

        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"current": "starting", "total": 100, "status": "Processing video..."},
        )

        # Send processing started notification (in-app only)
        try:
            notification_service.send_notification(
                user_id=user_id,
                notification_type=NotificationType.VIDEO_PROCESSING_STARTED,
                data={
                    "video_id": video_id,
                    "video_title": options.get("title", "Your video"),
                    "message": "Your video processing has started.",
                },
                channels=[NotificationChannel.IN_APP, NotificationChannel.WEBSOCKET],
            )
        except Exception as e:
            logger.error(f"Failed to send processing started notification: {e}")

        # Get video data
        video = video_service.get_video_by_id(video_id)
        if not video:
            raise ProcessingError(f"Video not found: {video_id}")

        # Update progress: Analyzing
        self.update_state(
            state="PROGRESS",
            meta={"current": "analyzing", "total": 100, "status": "Analyzing video..."},
        )

        # Process based on video type (speech vs silent)
        video_type = options.get("video_type", "speech")

        # Step 1: Handle silent video processing
        if options.get("process_silent_video") or video_type == "silent":
            logger.info(f"Processing silent video: {video_id}")
            _process_silent_video(video, options)
        else:
            # Step 2: Transcribe audio (if speech video)
            if video_type == "speech" and options.get("auto_transcribe", True):
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": "transcribing",
                        "total": 100,
                        "status": "Transcribing audio...",
                    },
                )
                _transcribe_video(video, options)

        # Step 3: Generate title, description, tags
        self.update_state(
            state="PROGRESS",
            meta={
                "current": "generating_metadata",
                "total": 100,
                "status": "Generating title and description...",
            },
        )
        _generate_metadata(video, options)

        # Step 4: Generate thumbnails
        self.update_state(
            state="PROGRESS",
            meta={
                "current": "generating_thumbnails",
                "total": 100,
                "status": "Generating thumbnails...",
            },
        )
        _generate_thumbnails(video, options)

        # Step 5: Apply video styles
        if options.get("styles") and len(options["styles"]) > 0:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": "applying_styles",
                    "total": 100,
                    "status": "Applying video styles...",
                },
            )
            _apply_video_styles(video, options["styles"])

        # Step 6: Apply aspect ratio
        if options.get("aspect_ratio") and options["aspect_ratio"] != "original":
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": "aspect_ratio",
                    "total": 100,
                    "status": "Adjusting aspect ratio...",
                },
            )
            _apply_aspect_ratio(video, options["aspect_ratio"])

        # Step 7: Apply FPS and audio quality
        if options.get("fps") and options["fps"] != "original":
            _apply_fps(video, options["fps"])

        if options.get("audio_quality") and options["audio_quality"] != "original":
            _apply_audio_quality(video, options["audio_quality"])

        # Step 8: Generate chapters
        if options.get("generate_chapters"):
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": "generating_chapters",
                    "total": 100,
                    "status": "Generating chapters...",
                },
            )
            _generate_chapters(video)

        # Step 9: Translate if requested
        if options.get("translation_language"):
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": "translating",
                    "total": 100,
                    "status": "Translating content...",
                },
            )
            _translate_content(video, options["translation_language"])

        # Step 10: Finalize output
        self.update_state(
            state="PROGRESS",
            meta={
                "current": "finalizing",
                "total": 100,
                "status": "Finalizing output...",
            },
        )
        output_path = _finalize_video(video, options)

        # Mark as completed
        video.status = "completed"
        video.processing_completed = datetime.utcnow()
        video.processing_time = (
            (video.processing_completed - video.processing_started).total_seconds()
            if video.processing_started
            else None
        )
        video.output_video_url = output_path
        video_service.update_video(video)

        # Record metrics
        record_video_processing(
            tier=video.processed_tier or "free",
            video_type=video.video_type.value if video.video_type else "unknown",
            duration=video.duration or 0,
            status="completed",
        )

        # Get user tier to determine email behavior
        user = user_service.get_user_by_id(user_id)
        user_tier = user.tier.value if user else "free"

        # Determine channels based on tier and opt-in
        channels = [NotificationChannel.WEBSOCKET, NotificationChannel.IN_APP]

        if user_tier in ["pro", "enterprise"] and send_email_notification:
            channels.append(NotificationChannel.EMAIL)
            logger.info(f"Adding email notification for user {user_id} (opted in)")

        # Send completion notification
        notification_service.send_notification(
            user_id=user_id,
            notification_type=NotificationType.VIDEO_PROCESSED,
            data={
                "video_id": video_id,
                "video_title": video.title or "Your video",
                "video_url": video.output_video_url,
                "thumbnail_url": video.selected_thumbnail,
                "duration": video.duration,
                "message": f"Your video '{video.title or video.original_filename}' is ready!",
            },
            channels=channels,
            video_specific_opt_in=send_email_notification,
        )

        logger.info(f"Video processing completed for video_id: {video_id}")

        return {
            "success": True,
            "video_id": video_id,
            "output_url": video.output_video_url,
            "processing_time": video.processing_time,
        }

    except ProcessingError as e:
        logger.error(
            f"Video processing failed for video_id: {video_id}, error: {str(e)}"
        )

        # Send failure notification
        try:
            notification_service.send_notification(
                user_id=user_id,
                notification_type=NotificationType.VIDEO_FAILED,
                data={
                    "video_id": video_id,
                    "error": str(e),
                    "step": e.step if hasattr(e, "step") else "unknown",
                    "message": f"Video processing failed: {str(e)}",
                },
                channels=[
                    NotificationChannel.IN_APP,
                    NotificationChannel.WEBSOCKET,
                    NotificationChannel.EMAIL,
                ],
                video_specific_opt_in=True,
            )
        except Exception as notify_error:
            logger.error(f"Failed to send failure notification: {notify_error}")

        # Record metrics for failure
        record_video_processing(
            tier=options.get("tier", "free"),
            video_type="unknown",
            duration=0,
            status="failed",
        )

        # Retry if possible
        if self.request.retries < self.max_retries:
            logger.info(
                f"Retrying video processing for video_id: {video_id} (attempt {self.request.retries + 1})"
            )
            raise self.retry(countdown=60 * (self.request.retries + 1))

        return {
            "success": False,
            "video_id": video_id,
            "error": str(e),
            "retries_exhausted": True,
        }

    except Exception as e:
        logger.error(
            f"Unexpected error processing video {video_id}: {str(e)}\n{traceback.format_exc()}"
        )

        try:
            notification_service.send_notification(
                user_id=user_id,
                notification_type=NotificationType.SYSTEM_ALERT,
                data={
                    "video_id": video_id,
                    "error": "Unexpected system error",
                    "message": "An unexpected error occurred during processing.",
                },
                channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
                video_specific_opt_in=True,
            )
        except Exception:
            pass

        if self.request.retries < self.max_retries:
            logger.info(
                f"Retrying video processing for video_id: {video_id} (attempt {self.request.retries + 1})"
            )
            raise self.retry(countdown=60 * (self.request.retries + 1))

        return {
            "success": False,
            "video_id": video_id,
            "error": "Unexpected error",
            "retries_exhausted": True,
        }


# Helper functions (regular functions, not async)


def _process_silent_video(video, options):
    """Process silent video using Gemini Vision."""
    try:
        from services.silent_video_service import SilentVideoService

        silent_service = SilentVideoService()
        result = silent_service.analyze_silent_video(
            video_path=video.original_path, video_id=video.id, options=options
        )

        video.transcription = result.get("description", "")
        video.transcription_language = "en"
        video.title = result.get("title", "")
        video.description = result.get("description", "")
        video.tags = result.get("tags", [])

        logger.info(f"Silent video analysis completed for {video.id}")

    except Exception as e:
        logger.error(f"Silent video processing failed: {e}")
        raise ProcessingError(
            f"Silent video analysis failed: {str(e)}", step="silent_analysis"
        )


def _transcribe_video(video, options):
    """Transcribe video audio using Whisper."""
    try:
        from services.transcription_service import TranscriptionService

        transcription_service = TranscriptionService()
        result = transcription_service.transcribe_video(
            video_path=video.original_path, video_id=video.id
        )

        video.transcription = result["text"]
        video.transcription_language = result.get("language", "en")

        logger.info(f"Transcription completed for {video.id}")

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise ProcessingError(f"Transcription failed: {str(e)}", step="transcription")


def _generate_metadata(video, options):
    """Generate title, description, and tags using AI."""
    try:
        from services.title_service import TitleService

        title_service = TitleService()
        result = title_service.generate_metadata(
            transcript=video.transcription, video_id=video.id, options=options
        )

        video.title = result.get("title", "")
        video.description = result.get("description", "")
        video.tags = result.get("tags", [])

        logger.info(f"Metadata generation completed for {video.id}")

    except Exception as e:
        logger.error(f"Metadata generation failed: {e}")
        raise ProcessingError(f"Metadata generation failed: {str(e)}", step="metadata")


def _generate_thumbnails(video, options):
    """Generate thumbnails using AI and frame extraction."""
    try:
        from services.thumbnail_service import ThumbnailService

        thumbnail_service = ThumbnailService()
        result = thumbnail_service.generate_thumbnails(
            video_path=video.original_path,
            title=video.title,
            video_type=video.video_type.value if video.video_type else "speech",
            tier=video.processed_tier or "free",
            transcription=video.transcription,
            style=options.get("thumbnail_style", "default"),
        )

        video.ai_thumbnails = result.get("ai_thumbnails", [])
        video.extracted_thumbnails = result.get("extracted_thumbnails", [])
        video.selected_thumbnail = result.get("selected", "")

        logger.info(f"Thumbnail generation completed for {video.id}")

    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise ProcessingError(
            f"Thumbnail generation failed: {str(e)}", step="thumbnails"
        )


def _apply_video_styles(video, styles):
    """Apply video styles using FFmpeg."""
    try:
        from services.style_service import StyleService

        style_service = StyleService()
        result = style_service.apply_styles(
            video_path=video.original_path,
            style_names=styles,
            tier=video.processed_tier or "free",
        )

        video.applied_styles = result.get("applied_styles", [])
        video.output_path = result.get("path", video.original_path)

        logger.info(f"Style application completed for {video.id}")

    except Exception as e:
        logger.error(f"Style application failed: {e}")
        raise ProcessingError(f"Style application failed: {str(e)}", step="styles")


def _apply_aspect_ratio(video, aspect_ratio):
    """Apply aspect ratio transformation."""
    try:
        from providers.ffmpeg_provider import FFmpegProvider
        import tempfile
        import os

        ffmpeg = FFmpegProvider()

        # Create temp output file
        temp_output = tempfile.NamedTemporaryFile(
            suffix=f"_aspect_{aspect_ratio}.mp4",
            delete=False,
            dir=os.path.dirname(video.original_path),
        ).name

        success = ffmpeg.change_aspect_ratio(
            input_path=video.output_path or video.original_path,
            output_path=temp_output,
            aspect_ratio=aspect_ratio,
        )

        if success:
            video.aspect_ratio = aspect_ratio
            video.output_path = temp_output
            logger.info(f"Aspect ratio applied: {aspect_ratio}")

    except Exception as e:
        logger.error(f"Aspect ratio application failed: {e}")
        # Don't fail the whole process for aspect ratio
        logger.warning(f"Continuing without aspect ratio: {e}")


def _apply_fps(video, fps):
    """Apply frame rate conversion."""
    try:
        from providers.ffmpeg_provider import FFmpegProvider
        import tempfile
        import os

        ffmpeg = FFmpegProvider()

        temp_output = tempfile.NamedTemporaryFile(
            suffix=f"_fps_{fps}.mp4",
            delete=False,
            dir=os.path.dirname(video.original_path),
        ).name

        success = ffmpeg.change_fps(
            input_path=video.output_path or video.original_path,
            output_path=temp_output,
            fps=fps,
        )

        if success:
            video.fps = fps
            video.output_path = temp_output

    except Exception as e:
        logger.error(f"FPS change failed: {e}")
        logger.warning(f"Continuing with original FPS: {e}")


def _apply_audio_quality(video, quality):
    """Apply audio quality settings."""
    try:
        from providers.ffmpeg_provider import FFmpegProvider
        import tempfile
        import os

        ffmpeg = FFmpegProvider()

        temp_output = tempfile.NamedTemporaryFile(
            suffix=f"_audio_{quality}.mp4",
            delete=False,
            dir=os.path.dirname(video.original_path),
        ).name

        success = ffmpeg.change_audio_quality(
            input_path=video.output_path or video.original_path,
            output_path=temp_output,
            bitrate=quality,
        )

        if success:
            video.audio_quality = quality
            video.output_path = temp_output

    except Exception as e:
        logger.error(f"Audio quality change failed: {e}")
        logger.warning(f"Continuing with original audio: {e}")


def _generate_chapters(video):
    """Generate chapter markers using AI."""
    try:
        from services.title_service import TitleService
        import json

        title_service = TitleService()

        chapters = title_service.generate_chapters(
            transcript=video.transcription, video_id=video.id
        )

        video.chapters = chapters
        logger.info(f"Generated {len(chapters)} chapters for {video.id}")

    except Exception as e:
        logger.error(f"Chapter generation failed: {e}")
        # Chapters are optional, don't fail the process


def _translate_content(video, target_language):
    """Translate video content to target language."""
    try:
        from services.translation_service import TranslationService

        translation_service = TranslationService()

        result = translation_service.translate_video(
            video_id=video.id,
            target_language=target_language,
            title=video.title,
            description=video.description,
            transcription=video.transcription,
        )

        if result:
            video.translated_title = result.get("title")
            video.translated_description = result.get("description")
            video.translated_transcription = result.get("transcription")
            video.translation_language = target_language

            logger.info(f"Translation completed for {video.id} to {target_language}")

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        # Don't fail the whole process for translation


def _finalize_video(video, options):
    """Finalize video output."""
    import os
    import shutil

    output_path = video.output_path or video.original_path

    # Apply quality settings if needed
    quality = options.get("quality", "720p")

    if quality != "original" and output_path:
        from providers.ffmpeg_provider import FFmpegProvider
        import tempfile

        ffmpeg = FFmpegProvider()

        temp_output = tempfile.NamedTemporaryFile(
            suffix=f"_{quality}.mp4", delete=False, dir=os.path.dirname(output_path)
        ).name

        success = ffmpeg.change_quality(
            input_path=output_path, output_path=temp_output, quality=quality
        )

        if success:
            output_path = temp_output
            video.output_quality = quality

    # Final output path
    final_output = f"/processed/{video.id}/output.mp4"
    video.output_video_url = final_output
    video.output_video_size = (
        os.path.getsize(output_path) if os.path.exists(output_path) else 0
    )

    return final_output


# Keep existing functions (process_video_batch, retry_failed_videos, etc.)
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

    # Emit WebSocket update
    from api.websocket import socketio

    socketio.emit(
        "video_status_update",
        {
            "video_id": video_id,
            "status": status,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


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
