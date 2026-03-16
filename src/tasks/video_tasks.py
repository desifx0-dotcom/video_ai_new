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
# Initialize notification service when needed, not at module level to avoid circular imports


@celery_app.task(bind=True, max_retries=3)
def process_video_async(
    self, video_id: str, user_id: str, options: Dict[str, Any] = None
):
    """
    Process video asynchronously.

    Args:
        video_id: Video ID
        user_id: User ID
        options: Processing options
    """
    # Import here to avoid circular imports
    from services.notification_service import (
        NotificationService,
        NotificationType,
        NotificationChannel,
    )
    from services.user_service import UserService

    notification_service = NotificationService()
    user_service = UserService()
    options = options or {}

    # Get the send_email_notification flag from options (set in upload page)
    send_email_notification = options.get("send_email_notification", False)

    try:
        logger.info(
            f"Starting video processing for video_id: {video_id}, user_id: {user_id}"
        )

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

        # Process video
        video = video_service.process_video(video_id, user_id, options)

        # Get user tier to determine email behavior
        user = user_service.get_user_by_id(user_id)
        user_tier = user.tier.value if user else "free"

        # Determine channels based on tier and opt-in
        channels = [NotificationChannel.WEBSOCKET, NotificationChannel.IN_APP]

        # Add email for:
        # 1. Free/Starter: NEVER for video processed (only critical emails handled elsewhere)
        # 2. Pro/Enterprise: Only if they explicitly opted in
        if user_tier in ["pro", "enterprise"] and send_email_notification:
            channels.append(NotificationChannel.EMAIL)
            logger.info(
                f"Adding email notification for Pro/Enterprise user {user_id} (opted in)"
            )

        # Send completion notification
        if video and video.output_video_url:
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

        # Record metrics
        record_video_processing(
            tier=video.processed_tier if video else user_tier,
            video_type=video.video_type.value if video else "unknown",
            duration=video.duration if video else 0,
            status="completed",
        )

        logger.info(f"Video processing completed for video_id: {video_id}")

        return {
            "success": True,
            "video_id": video_id,
            "output_url": video.output_video_url if video else None,
            "processing_time": video.processing_time if video else None,
        }

    except ProcessingError as e:
        logger.error(
            f"Video processing failed for video_id: {video_id}, error: {str(e)}"
        )

        # Send failure notification (ALWAYS send email for failures - critical)
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
                video_specific_opt_in=True,  # Force email for failures
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

        # Send unexpected error notification
        try:
            notification_service.send_notification(
                user_id=user_id,
                notification_type=NotificationType.SYSTEM_ALERT,
                data={
                    "video_id": video_id,
                    "error": "Unexpected system error",
                    "message": "An unexpected error occurred during processing.",
                },
                channels=[
                    NotificationChannel.IN_APP,
                    NotificationChannel.EMAIL,
                ],  # Email for critical errors
                video_specific_opt_in=True,
            )
        except Exception:
            pass

        # Retry if possible
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
