"""
Video processing Celery tasks.
"""

import os
import sys
import logging
import traceback
import psutil
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

# ==================== ERROR CLASSIFICATION FOR PRODUCTION ====================
from typing import Type, Tuple
from requests.exceptions import Timeout, ConnectionError as RequestsConnectionError
from redis.exceptions import ConnectionError as RedisConnectionError
from core.exceptions import (
    ValidationError,
    TierLimitExceeded,
    InsufficientCreditsError,
    ConfigurationError,
)


class ErrorClassifier:
    """Classify errors as PERMANENT or TRANSIENT for retry decisions."""

    # Transient errors - SHOULD retry
    TRANSIENT_ERRORS = (
        Timeout,  # API timeout
        RequestsConnectionError,  # Network issues
        RedisConnectionError,  # Redis down
        ConnectionError,  # General connection error
        TimeoutError,  # Operation timeout
    )

    # Permanent errors - SHOULD NOT retry
    PERMANENT_ERRORS = (
        ValidationError,  # Invalid input
        TierLimitExceeded,  # Tier limit reached
        InsufficientCreditsError,  # No credits
        ConfigurationError,  # System misconfiguration
        FileNotFoundError,  # Missing file
        PermissionError,  # Access denied
        ValueError,  # Invalid value
        TypeError,  # Wrong type
        KeyError,  # Missing key
        AttributeError,  # Missing attribute
        NotImplementedError,  # Not implemented
    )

    @classmethod
    def is_transient(cls, error: Exception) -> bool:
        """Check if error is transient (should retry)."""
        # Check exact types
        if isinstance(error, cls.TRANSIENT_ERRORS):
            return True

        # Check for permanent errors first (override)
        if isinstance(error, cls.PERMANENT_ERRORS):
            return False

        # Check error message patterns for common issues
        error_str = str(error).lower()
        permanent_patterns = [
            "not found",
            "missing",
            "does not exist",
            "invalid",
            "not allowed",
            "forbidden",
            "unauthorized",
            "authentication failed",
            "configuration error",
            "syntax error",
            "validation failed",
            "already exists",
            "permission denied",
            "access denied",
        ]

        for pattern in permanent_patterns:
            if pattern in error_str:
                return False

        # Default to transient (safer to retry than fail permanently)
        return True

    @classmethod
    def get_retry_delay(cls, retry_count: int, base_delay: int = 60) -> int:
        """
        Calculate exponential backoff delay with jitter.

        Args:
            retry_count: Current retry attempt (0-indexed)
            base_delay: Base delay in seconds

        Returns:
            Delay in seconds
        """
        import random

        # Exponential backoff: 60s, 120s, 240s, 300s (max)
        delay = min(300, base_delay * (2**retry_count))

        # Add jitter (±10%) to prevent thundering herd
        jitter = random.uniform(-delay * 0.1, delay * 0.1)
        final_delay = max(10, delay + jitter)

        return int(final_delay)


# ==================== END ERROR CLASSIFICATION ====================

# ==================== WebSocket Integration ====================
# Lazy-loaded WebSocket handlers to avoid circular imports
_ws_handlers = None


def _get_ws_handlers():
    """Lazy load WebSocket handlers to avoid circular imports."""
    global _ws_handlers

    if _ws_handlers is None:
        try:
            from api.websocket import (
                send_video_update,
                send_video_completed,
                send_video_failed,
                send_progress_update,
            )

            _ws_handlers = {
                "update": send_video_update,
                "completed": send_video_completed,
                "failed": send_video_failed,
                "progress": send_progress_update,
            }
            logger.info("✅ WebSocket handlers loaded successfully")
        except ImportError as e:
            logger.warning(f"❌ WebSocket handlers not available: {e}")
            _ws_handlers = {}

    return _ws_handlers


def _send_ws_update(video_id, user_id, status, progress, step=None, message=None):
    """Send WebSocket update using the manager."""
    try:
        from api.websocket import send_video_update

        # WebSocketManager handles both direct emit AND Redis publish
        send_video_update(
            video_id=video_id,
            user_id=user_id,
            status=status,
            progress=progress,
            step=step,
            message=message,
            publish_to_redis=True,  # Always publish for cross-process
        )
        logger.info(f"📤 Sent update: {video_id} - {step} ({progress}%)")
    except Exception as e:
        logger.error(f"Failed to send WebSocket update: {e}")


def _send_ws_completed(video_id, user_id, result_url, processing_time, total_cost):
    """Send WebSocket completion safely."""
    try:
        logger.info(f"🔔 _send_ws_completed called for video {video_id}")
        handlers = _get_ws_handlers()
        if "completed" in handlers:
            handlers["completed"](
                video_id, user_id, result_url, processing_time, total_cost
            )
            logger.info(f"✅ _send_ws_completed executed for video {video_id}")
        else:
            logger.warning(f"⚠️ No 'completed' handler found for video {video_id}")
    except Exception as e:
        logger.error(f"WebSocket completion failed: {e}", exc_info=True)


def _send_ws_failed(video_id, user_id, error_message, retry_count, can_retry):
    """Send WebSocket failure safely."""
    try:
        handlers = _get_ws_handlers()
        if "failed" in handlers:
            handlers["failed"](video_id, user_id, error_message, retry_count, can_retry)
    except Exception as e:
        logger.debug(f"WebSocket failure failed (non-critical): {e}")


def _send_ws_retrying(video_id, user_id, retry_count, max_retries):
    """Send WebSocket retry notification."""
    from api.websocket import socketio

    try:
        handlers = _get_ws_handlers()
        if hasattr(handlers, "send_video_update"):
            handlers["send_video_update"](
                video_id,
                user_id,
                "retrying",
                0,
                "retrying",
                f"Retrying... ({retry_count}/{max_retries})",
            )
        # Also emit custom retry event
        if socketio:
            socketio.emit(
                "video_retrying",
                {
                    "video_id": video_id,
                    "retry_count": retry_count,
                    "max_retries": max_retries,
                },
                room=f"user:{user_id}",
            )
    except Exception as e:
        logger.debug(f"WebSocket retry notification failed: {e}")


def _send_ws_progress(video_id, progress, step, estimated_time_remaining=None):
    """Send WebSocket progress update safely."""
    try:
        handlers = _get_ws_handlers()
        if "progress" in handlers:
            handlers["progress"](video_id, progress, step, estimated_time_remaining)
    except Exception as e:
        logger.debug(f"WebSocket progress update failed (non-critical): {e}")


# Convenience wrapper for backward compatibility
def emit_websocket_update(video_id, user_id, status, progress):
    """Safe WebSocket emission (backward compatibility)."""
    _send_ws_update(video_id, user_id, status, progress, status)


# ==================== End WebSocket Integration ====================


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


@celery_app.task(bind=True, max_retries=3)
def process_video_async(
    self, video_id: str, user_id: str, options: Dict[str, Any] = None
):
    """
    Process video asynchronously - PRODUCTION OPTIMIZED with proper retry logic.

    Processing order:
    1. Metadata & AI generation (silent/speech detection, transcription, metadata, thumbnails)
    2. ALL video filters applied in SINGLE PASS (speed, fps, styles, quality, aspect ratio)

    Retry Strategy:
    - Permanent errors (validation, config, missing files): FAIL IMMEDIATELY
    - Transient errors (network, timeout, rate limit): RETRY with exponential backoff
    - Max 3 retries, then move to dead letter queue
    """
    options = options or {}
    from services.user_service import UserService
    from core.exceptions import ConfigurationError

    # ========== VALIDATION FIRST - FAIL FAST ==========
    video = video_service.get_video_by_id(video_id)
    if not video:
        # PERMANENT ERROR - Don't retry
        logger.error(f"Video {video_id} not found - PERMANENT FAILURE")
        _send_ws_failed(
            video_id, user_id, "Video not found", self.request.retries, False
        )
        return {
            "success": False,
            "video_id": video_id,
            "error": "Video not found",
            "permanent_failure": True,
        }

    # Validate input file exists (PERMANENT ERROR)
    if not video.original_path or not os.path.exists(video.original_path):
        logger.error(
            f"Original video file missing: {video.original_path} - PERMANENT FAILURE"
        )
        _send_ws_failed(
            video_id,
            user_id,
            "Original video file missing",
            self.request.retries,
            False,
        )
        return {
            "success": False,
            "video_id": video_id,
            "error": "Original video file missing",
            "permanent_failure": True,
        }

    # Validate FFmpeg is available (PERMANENT ERROR for production)
    try:
        import subprocess

        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise ConfigurationError("FFmpeg not available")
    except Exception as e:
        logger.error(f"FFmpeg validation failed: {e} - PERMANENT FAILURE")
        _send_ws_failed(
            video_id, user_id, "FFmpeg not available", self.request.retries, False
        )
        return {
            "success": False,
            "video_id": video_id,
            "error": "FFmpeg not available",
            "permanent_failure": True,
        }

    # Send initial WebSocket update - QUEUED
    _send_ws_update(
        video_id, user_id, "queued", 0, "queued", "Video queued for processing"
    )
    _send_ws_progress(video_id, 0, "queued", None)

    # Check if video is already being processed (transient timeout)
    if video and video.status == "processing":
        processing_started = video.processing_started
        if processing_started:
            elapsed = (datetime.utcnow() - processing_started).total_seconds()
            if elapsed > 600:  # 10 minutes timeout
                logger.warning(
                    f"Video {video_id} has been processing for {elapsed}s, marking as failed"
                )
                video.status = "failed"
                video.error_message = "Processing timeout"
                video_service.update_video(video)
                _send_ws_failed(
                    video_id, user_id, "Processing timeout", self.request.retries, True
                )
                return {
                    "success": False,
                    "video_id": video_id,
                    "error": "Processing timeout",
                }

    # Log received options
    logger.info("=" * 80)
    logger.info(f"📥 VIDEO PROCESSING STARTED for {video_id}")
    logger.info(f"📥 User ID: {user_id}")
    logger.info(f"📥 Received options:")
    for key in [
        "quality",
        "fps",
        "audio_quality",
        "aspect_ratio",
        "speed",
        "speed_presets",
        "thumbnail_style",
        "styles",
    ]:
        logger.info(f"   {key}: {options.get(key)}")
    logger.info("=" * 80)

    notification_service = NotificationService()
    user_service = UserService()
    send_email_notification = options.get("send_email_notification", False)

    try:
        logger.info(
            f"Starting video processing for video_id: {video_id}, user_id: {user_id}"
        )

        # Send WebSocket update - STARTING
        _send_ws_update(
            video_id, user_id, "queued", 5, "queued", "Video queued for processing"
        )
        _send_ws_progress(video_id, 5, "queued", None)

        # INITIAL STATUS - QUEUED
        video_service.update_processing_status(video_id, "queued", 5, "queued")

        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"current": "starting", "total": 100, "status": "Initializing..."},
        )

        # STATUS - ANALYZING
        video_service.update_processing_status(video_id, "processing", 10, "analyzing")
        _send_ws_update(
            video_id, user_id, "processing", 10, "analyzing", "Analyzing video..."
        )
        _send_ws_progress(video_id, 10, "analyzing", None)
        self.update_state(
            state="PROGRESS",
            meta={"current": "analyzing", "total": 100, "status": "Analyzing video..."},
        )

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
        _send_ws_update(
            video_id,
            user_id,
            "processing",
            15,
            "configuring",
            "Configuring video settings...",
        )
        _send_ws_progress(video_id, 15, "configuring", None)

        settings_changed = False

        # 1.1 SPEED
        speed_value = options.get("speed")
        if speed_value is None:
            speed_value = options.get("speed_presets")
            if speed_value and isinstance(speed_value, str):
                speed_value = float(speed_value.replace("x", ""))
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

        # 1.7 Aspect Ratio
        if options.get("aspect_ratio") and options["aspect_ratio"] != "original":
            video.aspect_ratio = options["aspect_ratio"]
            logger.info(
                f"✅ Setting aspect ratio (will apply last): {options['aspect_ratio']}"
            )
            settings_changed = True
        else:
            video.aspect_ratio = "original"

        # Save all settings
        if settings_changed:
            video_service.update_video(video)
            logger.info(f"💾 Saved video settings to database")

        # ========== STEP 2: SILENT VIDEO OR TRANSCRIPTION ==========
        _send_ws_update(
            video_id,
            user_id,
            "processing",
            20,
            "analyzing",
            "Analyzing video content...",
        )
        _send_ws_progress(video_id, 20, "analyzing", None)
        self.update_state(
            state="PROGRESS",
            meta={"current": "analyzing", "total": 100, "status": "Analyzing video..."},
        )

        video_type = options.get("video_type", "speech")

        if options.get("process_silent_video") or video_type == "silent":
            logger.info(f"Processing silent video: {video_id}")
            video_service.update_processing_status(
                video_id, "processing", 25, "silent_analysis"
            )
            _send_ws_update(
                video_id,
                user_id,
                "processing",
                25,
                "silent_analysis",
                "Analyzing silent video content...",
            )
            _send_ws_progress(video_id, 25, "silent_analysis", None)
            _process_silent_video(video, options)
        else:
            if video_type == "speech" and options.get("auto_transcribe", True):
                video_service.update_processing_status(
                    video_id, "processing", 30, "transcribing"
                )
                _send_ws_update(
                    video_id,
                    user_id,
                    "processing",
                    30,
                    "transcribing",
                    "Transcribing audio...",
                )
                _send_ws_progress(video_id, 30, "transcribing", None)
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": "transcribing",
                        "total": 100,
                        "status": "Transcribing audio...",
                    },
                )
                _transcribe_video(video, options)

        # ========== STEP 3: GENERATE METADATA ==========
        video_service.update_processing_status(video_id, "processing", 40, "metadata")
        _send_ws_update(
            video_id,
            user_id,
            "processing",
            40,
            "generating_metadata",
            "Generating title and description...",
        )
        _send_ws_progress(video_id, 40, "generating_metadata", None)
        self.update_state(
            state="PROGRESS",
            meta={
                "current": "metadata",
                "total": 100,
                "status": "Generating metadata...",
            },
        )
        _generate_metadata(video, options)

        # ========== STEP 4: GENERATE THUMBNAILS ==========
        video_service.update_processing_status(video_id, "processing", 60, "thumbnails")
        _send_ws_update(
            video_id, user_id, "processing", 60, "thumbnails", "Creating thumbnails..."
        )
        _send_ws_progress(video_id, 60, "thumbnails", None)
        self.update_state(
            state="PROGRESS",
            meta={
                "current": "thumbnails",
                "total": 100,
                "status": "Generating thumbnails...",
            },
        )

        # FIRST generate the thumbnails
        _generate_thumbnails(video, options, user_id)

        # THEN send completion for thumbnails
        _send_ws_update(
            video_id, user_id, "processing", 70, "thumbnails", "Thumbnails complete"
        )
        _send_ws_progress(video_id, 70, "thumbnails", None)

        # ========== STEP 5: APPLY ALL VIDEO FILTERS (SINGLE PASS) ==========
        video_service.update_processing_status(
            video_id, "processing", 75, "applying_filters"
        )
        _send_ws_update(
            video_id,
            user_id,
            "processing",
            75,
            "applying_filters",
            "Applying video effects...",
        )
        _send_ws_progress(video_id, 75, "applying_filters", None)
        self.update_state(
            state="PROGRESS",
            meta={
                "current": "applying_filters",
                "total": 100,
                "status": "Applying video effects...",
            },
        )

        try:
            output_path = _apply_all_filters_production(video, options)
            if not output_path:
                error_msg = f"Video filter application failed at stage: {getattr(video, '_last_failed_stage', 'unknown')}"
                logger.error(f"[MASTER] {error_msg}")
                _send_ws_failed(
                    video_id,
                    user_id,
                    error_msg,
                    self.request.retries,
                    self.request.retries < self.max_retries,
                )
                raise ProcessingError(error_msg)
        except Exception as filter_error:
            logger.error(f"[MASTER] Filter application failed: {filter_error}")
            video.status = "failed"
            video.error_message = str(filter_error)
            video_service.update_video(video)
            _send_ws_failed(
                video_id,
                user_id,
                str(filter_error),
                self.request.retries,
                self.request.retries < self.max_retries,
            )
            raise ProcessingError(
                f"Video processing failed during filter application: {filter_error}"
            )

        # Filters complete
        _send_ws_update(
            video_id,
            user_id,
            "processing",
            90,
            "applying_filters",
            "Video effects applied",
        )
        _send_ws_progress(video_id, 90, "applying_filters", None)

        # ========== STEP 6: COMPLETE ==========
        video.status = "completed"
        video.processing_completed = datetime.utcnow()
        if video.processing_started:
            video.processing_time = (
                video.processing_completed - video.processing_started
            ).total_seconds()
        video.output_video_url = output_path
        video.output_path = output_path
        video.output_video_size = (
            os.path.getsize(output_path) if os.path.exists(output_path) else 0
        )

        video_service.update_video(video)

        # Send completion WebSocket
        _send_ws_completed(
            video_id,
            user_id,
            video.output_video_url,
            video.processing_time,
            video.total_cost,
        )
        _send_ws_update(
            video_id,
            user_id,
            "completed",
            100,
            "completed",
            "Video processing complete!",
        )
        _send_ws_progress(video_id, 100, "completed", 0)

        # Deduct credits AFTER successful processing
        try:
            from services.credit_service import CreditService

            credit_service = CreditService()

            user = user_service.get_user_by_id(user_id)
            credits_needed = 1

            if user.credits_remaining >= credits_needed:
                credit_service.use_credits(
                    user_id=user_id,
                    amount=credits_needed,
                    description=f"Video processing completed: {video.original_filename}",
                    video_id=video_id,
                    operation="video_processing",
                )
                logger.info(
                    f"✅ Deducted {credits_needed} credit(s) from user {user_id} for video {video_id}"
                )
                logger.info(
                    f"💰 Credits remaining: {user.credits_remaining - credits_needed}"
                )
            else:
                logger.warning(
                    f"⚠️ User {user_id} has insufficient credits ({user.credits_remaining}) for processing"
                )

        except Exception as e:
            logger.error(f"Failed to deduct credits for video {video_id}: {e}")

        # Log final settings
        logger.info("=" * 80)
        logger.info(f"✅ VIDEO PROCESSING COMPLETED for {video_id}")
        logger.info(f"📊 Final video settings:")
        logger.info(f"   quality: {video.output_quality}")
        logger.info(f"   fps: {video.fps}")
        logger.info(f"   audio_quality: {video.audio_quality}")
        logger.info(f"   aspect_ratio: {getattr(video, 'aspect_ratio', 'original')}")
        logger.info(f"   speed: {getattr(video, 'speed', 1.0)}x")
        logger.info(f"   styles: {video.applied_styles}")
        logger.info(f"   output_path: {output_path}")
        logger.info(f"   output_size: {video.output_video_size:,} bytes")
        logger.info("=" * 80)

        # Send completion WebSocket
        _send_ws_completed(
            video_id,
            user_id,
            video.output_video_url,
            video.processing_time,
            video.total_cost,
        )
        _send_ws_update(
            video_id,
            user_id,
            "completed",
            100,
            "completed",
            "Video processing complete!",
        )
        _send_ws_progress(video_id, 100, "completed", 0)

        return {
            "success": True,
            "video_id": video_id,
            "output_url": video.output_video_url,
            "processing_time": video.processing_time,
        }

    except Exception as e:
        # ========== PRODUCTION ERROR HANDLING ==========
        error_type = type(e).__name__

        # Classify error
        is_transient = ErrorClassifier.is_transient(e)

        if not is_transient:
            # PERMANENT ERROR - Don't retry, fail immediately
            logger.error(
                f"PERMANENT error in video processing for {video_id}: {error_type} - {str(e)}"
            )
            logger.error(f"Full traceback: {traceback.format_exc()}")

            # Update video status to failed with clear reason
            video.status = "failed"
            video.error_message = f"Permanent error: {str(e)[:200]}"
            video_service.update_video(video)

            # Send failure notification (no retry)
            _send_ws_failed(
                video_id,
                user_id,
                f"Processing failed: {str(e)[:200]}",
                self.request.retries,
                False,
            )

            return {
                "success": False,
                "video_id": video_id,
                "error": str(e),
                "error_type": error_type,
                "permanent_failure": True,
            }

        # TRANSIENT ERROR - Retry with exponential backoff
        logger.warning(
            f"TRANSIENT error in video processing for {video_id}: {error_type} - {str(e)}"
        )
        logger.warning(f"Attempt {self.request.retries + 1}/{self.max_retries}")

        if self.request.retries < self.max_retries:
            # Calculate delay with exponential backoff
            delay = ErrorClassifier.get_retry_delay(self.request.retries)

            _send_ws_update(
                video_id,
                user_id,
                "retrying",
                0,
                "retrying",
                f"Temporary issue: {error_type}. Retrying in {delay}s (attempt {self.request.retries + 1}/{self.max_retries})",
            )

            logger.info(
                f"Retrying video {video_id} in {delay}s (attempt {self.request.retries + 1})"
            )
            raise self.retry(exc=e, countdown=delay)
        else:
            # Max retries exceeded
            logger.error(
                f"MAX RETRIES exceeded for video {video_id}: {error_type} - {str(e)}"
            )

            # Update video status
            video.status = "failed"
            video.error_message = f"Max retries exceeded: {str(e)[:200]}"
            video_service.update_video(video)

            _send_ws_failed(
                video_id,
                user_id,
                f"Processing failed after {self.max_retries} retries: {str(e)[:200]}",
                self.request.retries,
                False,
            )

            return {
                "success": False,
                "video_id": video_id,
                "error": str(e),
                "error_type": error_type,
                "max_retries_exceeded": True,
            }


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
    """Transcribe video audio with WebSocket progress updates."""
    from providers.openai_provider import OpenAIProvider

    try:
        # Send WebSocket update - transcription started
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            25,
            "transcribing",
            "Extracting audio from video...",
        )
        _send_ws_progress(video.id, 25, "transcribing", None)

        provider = OpenAIProvider()

        # Extract audio from video
        from providers.ffmpeg_provider import FFmpegProvider

        ffmpeg = FFmpegProvider()

        import tempfile

        audio_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name

        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            28,
            "transcribing",
            "Extracting audio track...",
        )
        ffmpeg.extract_audio(video.original_path, audio_path)

        # Transcribe
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            32,
            "transcribing",
            "Transcribing audio with AI...",
        )
        _send_ws_progress(video.id, 32, "transcribing", None)

        transcript = provider.transcribe_audio(audio_path)
        video.transcription = transcript
        video.transcription_language = "en"

        # Clean up
        os.unlink(audio_path)

        logger.info(f"Transcription completed for {video.id}")
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            35,
            "transcribing",
            "Transcription complete",
        )
        _send_ws_progress(video.id, 35, "transcribing", None)

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        _send_ws_failed(
            video.id, video.user_id, f"Transcription failed: {str(e)}", 0, True
        )
        raise ProcessingError(f"Transcription failed: {str(e)}", step="transcription")


def _generate_metadata(video, options):
    """Generate title, description, and tags with WebSocket progress updates."""
    from services.title_service import TitleService

    try:
        logger.info(f"Generating metadata for video {video.id}")
        logger.info(
            f"Video transcription length: {len(video.transcription) if video.transcription else 0}"
        )

        # Send WebSocket update - metadata generation started
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            40,
            "generating_metadata",
            "Analyzing content for titles...",
        )
        _send_ws_progress(video.id, 40, "generating_metadata", None)

        title_service = TitleService()
        result = title_service.generate_metadata(
            transcript=video.transcription or "", video_id=video.id, options=options
        )

        video.title = result.get("title", "")
        video.description = result.get("description", "")
        video.tags = result.get("tags", [])

        # Send WebSocket update - title generation complete
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            45,
            "generating_metadata",
            "Title and description generated",
        )
        _send_ws_progress(video.id, 45, "generating_metadata", None)

        logger.info(f"Metadata generation completed for {video.id}")

    except Exception as e:
        logger.error(f"Metadata generation failed: {e}")
        logger.error(traceback.format_exc())

        # Send WebSocket warning but continue with defaults
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            42,
            "generating_metadata",
            "Using default metadata (AI service unavailable)",
        )

        # Don't raise - set defaults and continue
        video.title = "Untitled Video"
        video.description = "Video processed by Video AI Studio"
        video.tags = ["video", "ai", "processed"]


def _generate_thumbnails(video, options, user_id):
    """Generate thumbnails with WebSocket progress updates."""
    from services.thumbnail_service import ThumbnailService

    # Check if original_path exists
    if not video.original_path:
        logger.error(f"Video {video.id} has no original_path")
        # Try to get from database again
        video_data = video_service.db.get("videos", video.id)
        if video_data and video_data.get("original_path"):
            video.original_path = video_data["original_path"]
        else:
            _send_ws_failed(
                video.id, video.user_id, "No original video path found", 0, True
            )
            raise ProcessingError(f"No original path found for video {video.id}")

    try:
        # Send WebSocket update - thumbnail generation started
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            50,
            "generating_thumbnails",
            "Starting thumbnail generation...",
        )
        _send_ws_progress(video.id, 50, "generating_thumbnails", None)

        thumbnail_service = ThumbnailService()

        # Pass the thumbnail_style from options
        thumbnail_style = options.get("thumbnail_style", "default")
        logger.info(f"Generating thumbnails with style: {thumbnail_style}")

        # Update progress - extracting frames
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            55,
            "generating_thumbnails",
            "Extracting video frames...",
        )
        _send_ws_progress(video.id, 55, "generating_thumbnails", None)

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

        # Update progress - generating AI thumbnails
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            65,
            "generating_thumbnails",
            "Creating AI thumbnails...",
        )
        _send_ws_progress(video.id, 65, "generating_thumbnails", None)

        video.ai_thumbnails = result.get("ai_thumbnails", [])
        video.extracted_thumbnails = result.get("extracted_thumbnails", [])
        video.selected_thumbnail = result.get(
            "selected_thumbnail",
            video.ai_thumbnails[0]["path"] if video.ai_thumbnails else None,
        )

        video.thumbnail_style = thumbnail_style

        # Send completion update
        thumbnail_count = len(video.ai_thumbnails) + len(video.extracted_thumbnails)
        _send_ws_update(
            video.id,
            video.user_id,
            "processing",
            70,
            "generating_thumbnails",
            f"Generated {thumbnail_count} thumbnails",
        )
        _send_ws_progress(video.id, 70, "generating_thumbnails", None)

        logger.info(f"Thumbnail generation completed for {video.id}")

    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        _send_ws_failed(
            video.id, video.user_id, f"Thumbnail generation failed: {str(e)}", 0, True
        )
        raise ProcessingError(
            f"Thumbnail generation failed: {str(e)}", step="thumbnails"
        )


def _check_system_resources():
    """Check available memory and warn if low."""
    memory = psutil.virtual_memory()
    if memory.available < 500 * 1024 * 1024:  # Less than 500MB
        logger.warning(f"Low memory: {memory.available / (1024*1024):.0f}MB available")
        return False
    return True


def _apply_all_filters_production(video, options):
    """
    MULTI-PASS: Apply filters in stages with WebSocket progress updates.
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

    # Send initial progress - APPLYING FILTERS starts
    _send_ws_update(
        video.id,
        video.user_id,
        "processing",
        75,
        "applying_filters",
        "Starting video filters...",
    )
    _send_ws_progress(video.id, 75, "applying_filters", None)

    video._last_failed_stage = None
    input_path = video.original_path
    if not input_path or not os.path.exists(input_path):
        logger.error(f"[MASTER] Input not found: {input_path}")
        return None

    # ========== CHECK IF CHUNKED PROCESSING IS NEEDED ==========
    from providers.ffmpeg_provider import FFmpegProvider

    ffmpeg = FFmpegProvider()

    # Check file size and resolution
    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    try:
        metadata = ffmpeg.get_video_metadata(input_path)
        width = metadata.get("video", {}).get("width", 0)
        height = metadata.get("video", {}).get("height", 0)
    except:
        width = 0
        height = 0

    video_short_id = video.id[:8]
    final_path = os.path.join(
        os.path.dirname(input_path), f"final_{video_short_id}.mp4"
    )

    aspect_dimensions = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
        "2:3": (1080, 1620),
    }

    # Determine target dimensions for aspect ratio
    aspect_ratio = getattr(video, "aspect_ratio", "original")
    target_width = None
    target_height = None
    if aspect_ratio in aspect_dimensions:
        target_width, target_height = aspect_dimensions[aspect_ratio]

    # Use chunked processing for large videos (> 1GB OR > 2K resolution)
    use_chunked = (
        file_size_mb > 100 or width > 1920 or height > 1080
    )  # if it is more than 100mb or more than 1k

    if use_chunked:
        logger.info(
            f"[MASTER] Large video detected ({file_size_mb:.0f}MB, {width}x{height})"
        )
        logger.info(f"[MASTER] Using CHUNKED multi-pass processing")

        # Get all filter parameters
        speed = getattr(video, "speed", 1.0)
        fps = getattr(video, "fps", "original")
        styles = getattr(video, "applied_styles", [])
        quality = getattr(video, "output_quality", "original")

        # Use chunked processing
        success = ffmpeg.apply_full_filter_chain_chunked(
            input_path=input_path,
            output_path=final_path,
            speed=speed,
            fps=fps,
            styles=styles,
            quality=quality,
            aspect_ratio=aspect_ratio,
            target_width=target_width,
            target_height=target_height,
            chunk_duration=5,
        )

        if success and os.path.exists(final_path):
            _send_ws_update(
                video.id,
                video.user_id,
                "processing",
                90,
                "finalizing",
                "Finalizing output...",
            )
            _send_ws_progress(video.id, 90, "finalizing", None)

            video.output_path = final_path
            video.output_video_url = final_path
            video.output_video_size = os.path.getsize(final_path)
            video_service.update_video(video)

            logger.info(
                f"[MASTER] ✅ Chunked processing completed: {os.path.basename(final_path)}"
            )
            logger.info(f"[MASTER] ✅ File size: {video.output_video_size:,} bytes")
            return final_path
        else:
            logger.warning(
                f"[MASTER] Chunked processing failed, falling back to normal processing"
            )

    # ========== NORMAL PROCESSING ==========
    logger.info(f"[MASTER] Using normal multi-pass processing")

    # Validate FFmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception as e:
        logger.error(f"[MASTER] FFmpeg not available: {e}")
        return None

    # ========== 1. COLLECT ALL FEATURES ==========
    video_short_id = video.id[:8]

    quality = getattr(video, "output_quality", "original")
    aspect_ratio = getattr(video, "aspect_ratio", "original")
    speed = getattr(video, "speed", 1.0)
    fps = getattr(video, "fps", "original")
    styles = getattr(video, "applied_styles", [])
    audio_quality = getattr(video, "audio_quality", "original")

    # ========== 2. APPLY FILTERS IN STAGES ==========
    current_input = input_path
    temp_files = []
    total_stages = 0

    # Calculate total stages for progress calculation
    if speed != 1.0:
        total_stages += 1
    if fps and fps != "original" and str(fps).isdigit():
        total_stages += 1
    if styles:
        total_stages += len(styles)
    if quality in {"480p", "720p", "1080p"}:
        total_stages += 1
    if aspect_ratio in aspect_dimensions:
        total_stages += 1

    completed_stages = 0

    # Function to update progress after each stage
    def update_progress(message):
        nonlocal completed_stages
        completed_stages += 1
        progress_pct = (
            85 + int((completed_stages / total_stages) * 14) if total_stages > 0 else 90
        )
        _send_ws_progress(video.id, progress_pct, "applying_filters", None)
        logger.info(f"[MASTER] Progress: {progress_pct}% - {message}")

    # Stage 1: Apply SPEED
    if speed != 1.0:
        temp_speed = os.path.join(
            os.path.dirname(input_path), f"temp_speed_{video_short_id}.mp4"
        )
        temp_files.append(temp_speed)

        speed_factor = 1.0 / speed
        tempo_factor = speed

        logger.info(f"[MASTER] Stage 1: Applying speed {speed}x")
        update_progress(f"Applying speed {speed}x")

        # Check if video has audio stream
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            "-pix_fmt",
            "yuv420p",
            current_input,
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        has_audio = False
        if probe_result.returncode == 0 and probe_result.stdout.strip():
            try:
                data = json.loads(probe_result.stdout)
                has_audio = len(data.get("streams", [])) > 0
            except:
                pass

        if not has_audio:
            cmd = [
                "ffmpeg",
                "-i",
                current_input,
                "-filter:v",
                f"setpts={speed_factor}*PTS",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-y",
                temp_speed,
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
                "ffmpeg",
                "-i",
                current_input,
                "-filter_complex",
                f"[0:v]setpts={speed_factor}*PTS[v];[0:a]{audio_filter}[a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-y",
                temp_speed,
            ]
        logger.info(f"[FFMPEG] Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"[MASTER] Speed stage FAILED: {result.stderr[:500]}")
            video._last_failed_stage = "speed"
            _send_ws_failed(video.id, video.user_id, "Speed filter failed", 0, False)
            return None

        if os.path.exists(temp_speed) and os.path.getsize(temp_speed) > 0:
            current_input = temp_speed
            logger.info(f"[MASTER] ✅ Speed {speed}x applied")
        else:
            logger.error(f"[MASTER] Speed output file is empty or missing!")
            return None

    # Stage 2: Apply FPS
    if fps and fps != "original" and str(fps).isdigit():
        temp_fps = os.path.join(
            os.path.dirname(input_path), f"temp_fps_{video_short_id}.mp4"
        )
        temp_files.append(temp_fps)

        logger.info(f"[MASTER] Stage 2: Applying FPS {fps}")
        update_progress(f"Applying FPS {fps}")

        cmd = [
            "ffmpeg",
            "-i",
            current_input,
            "-vf",
            f"fps={fps}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            "-pix_fmt",
            "yuv420p",
            "-y",
            temp_fps,
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
        "cinematic": "eq=brightness=0.05:contrast=1.15:saturation=1.1,unsharp=5:5:0.8",
        "bright": "eq=brightness=0.12:contrast=1.08:saturation=1.2",
        "educational": "eq=brightness=0.03:contrast=1.1:saturation=1.05,unsharp=3:3:0.5",
        "vlog": "eq=brightness=0.08:contrast=1.02:saturation=1.08,colorbalance=rs=0.02:gs=0.01:bs=-0.02",
        "gaming": "eq=saturation=1.25:contrast=1.15:brightness=0.03,unsharp=5:5:1.0,colorbalance=rs=0.05:gs=0.03:bs=-0.02",
        "travel": "eq=saturation=1.18:contrast=1.05:brightness=0.05,colorbalance=rs=0.03:gs=0.02:bs=0.04",
        "dark": "eq=brightness=-0.1:contrast=1.18:saturation=0.88,colorbalance=gs=-0.04",
        "professional": "eq=contrast=1.08:saturation=0.98,unsharp=3:3:0.4",
        "documentary": "eq=brightness=0:contrast=1.02:saturation=0.95,colorbalance=rs=-0.02:gs=-0.01:bs=-0.01",
        "wedding": "eq=brightness=0.07:contrast=1.02:saturation=1.05,colorbalance=rs=0.04:gs=0.02:bs=0.03",
        "corporate": "eq=brightness=0.03:contrast=1.08:saturation=0.98,unsharp=2:2:0.3",
        "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.06,unsharp=4:4:0.6",
        "action": "eq=contrast=1.2:brightness=0.03,unsharp=5:5:1.2,eq=saturation=1.1",
        "minimalist": "eq=saturation=0.92:contrast=1.05,unsharp=2:2:0.2",
        "vintage": "eq=brightness=0.02:contrast=0.92:saturation=0.88,colorbalance=rs=-0.03:gs=-0.02:bs=0.05",
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
        "hollywood": "eq=brightness=0.04:contrast=1.18:saturation=1.15,unsharp=5:5:1.1,colorbalance=rs=0.03:gs=0.02:bs=-0.02",
        "dreamy": "eq=brightness=0.06:contrast=1.02:saturation=1.08,unsharp=3:3:0.4,colorbalance=rs=0.04:gs=0.03:bs=0.07",
        "neon": "eq=saturation=1.3:contrast=1.2:brightness=0.05,colorbalance=rs=0.08:gs=0.05:bs=0.12,unsharp=4:4:0.8",
        "pastel": "eq=saturation=0.85:contrast=1.02:brightness=0.07,colorbalance=rs=0.02:gs=0.02:bs=0.02",
        "hdr": "eq=contrast=1.15:saturation=1.12,brightness=0.02,unsharp=5:5:1.0",
    }

    if styles:
        for i, style in enumerate(styles):
            if style in style_filters:
                temp_style = os.path.join(
                    os.path.dirname(input_path),
                    f"temp_style_{style}_{video_short_id}.mp4",
                )
                temp_files.append(temp_style)

                filter_str = style_filters[style]
                logger.info(f"[MASTER] Stage 3.{i+1}: Applying style '{style}'")
                update_progress(f"Applying style: {style}")

                cmd = [
                    "ffmpeg",
                    "-i",
                    current_input,
                    "-vf",
                    filter_str,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-c:a",
                    "copy",
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    temp_style,
                ]

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    logger.error(
                        f"[MASTER] Style '{style}' stage FAILED: {result.stderr[:500]}"
                    )
                    video._last_failed_stage = "video_styles"
                    return None

                current_input = temp_style
                logger.info(f"[MASTER] ✅ Style '{style}' applied")

    # Stage 4: Apply QUALITY scaling
    quality_map = {"480p": 480, "720p": 720, "1080p": 1080}
    if quality in quality_map:
        target_height = quality_map[quality]

        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "json",
            "-pix_fmt",
            "yuv420p",
            current_input,
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)

        current_height = 1080
        if probe_result.returncode == 0:
            info = json.loads(probe_result.stdout)
            current_height = info.get("streams", [{}])[0].get("height", 1080)

        if target_height < current_height:
            temp_quality = os.path.join(
                os.path.dirname(input_path), f"temp_quality_{video_short_id}.mp4"
            )
            temp_files.append(temp_quality)

            logger.info(f"[MASTER] Stage 4: Scaling to {quality}")
            update_progress(f"Scaling to {quality}")

            cmd = [
                "ffmpeg",
                "-i",
                current_input,
                "-vf",
                f"scale=-2:{target_height}",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                "-pix_fmt",
                "yuv420p",
                "-pix_fmt",
                "yuv420p",
                "-y",
                temp_quality,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(
                    f"[MASTER] Quality scaling stage FAILED: {result.stderr[:500]}"
                )
                video._last_failed_stage = "quality"
                return None

            current_input = temp_quality
            logger.info(f"[MASTER] ✅ Quality applied")

    # Stage 5: Apply ASPECT RATIO
    if aspect_ratio in aspect_dimensions:
        target_w, target_h = aspect_dimensions[aspect_ratio]
        temp_aspect = os.path.join(
            os.path.dirname(input_path), f"temp_aspect_{video_short_id}.mp4"
        )
        temp_files.append(temp_aspect)

        logger.info(f"[MASTER] Stage 5: Applying aspect ratio {aspect_ratio}")
        update_progress(f"Applying aspect ratio {aspect_ratio}")

        cmd = [
            "ffmpeg",
            "-i",
            current_input,
            "-vf",
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-y",
            temp_aspect,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"[MASTER] Aspect ratio stage FAILED: {result.stderr[:500]}")
            video._last_failed_stage = "aspect_ratio"
            return None

        current_input = temp_aspect
        logger.info(f"[MASTER] ✅ Aspect ratio applied")

    _send_ws_update(
        video.id, video.user_id, "processing", 90, "finalizing", "Finalizing output..."
    )
    _send_ws_progress(video.id, 90, "finalizing", None)

    # ========== 3. FINAL OUTPUT ==========
    final_filename = f"final_{video_short_id}.mp4"
    final_path = os.path.join(os.path.dirname(input_path), final_filename)

    shutil.copy2(current_input, final_path)

    # Send final progress update
    _send_ws_progress(video.id, 100, "finalizing", 0)

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
        logger.info(
            f"[MASTER] ✅ Copied to final location: {os.path.basename(final_path)}"
        )
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
                logger.info(
                    f"[CLEANUP] Deleted system temp: {os.path.basename(temp_file)}"
                )
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


@celery_app.task(bind=True, max_retries=3)
def apply_different_styles_async(self, video_id: str, user_id: str, styles: List[str], output_quality: str = "720p"):
    """
    Apply different video styles to the video while preserving ALL user settings.
    """
    from services.video_service import VideoService
    from providers.ffmpeg_provider import FFmpegProvider
    from core.status_tracker import status_tracker
    import subprocess
    import json
    import os
    from datetime import datetime
    import traceback
    
    task_id = f"{video_id}_{datetime.utcnow().timestamp()}"
    
    video_service = VideoService()
    ffmpeg = FFmpegProvider()
    
    # ========== GET VIDEO ==========
    video = video_service.get_video_by_id(video_id)
    if not video:
        status_tracker.set_status(task_id, "failed", 0, "error", "Video not found")
        return {"success": False, "error": "Video not found", "styles_applied": 0}

    input_path = video.original_path
    if not input_path or not os.path.exists(input_path):
        status_tracker.set_status(task_id, "failed", 0, "error", "Original video file missing")
        return {"success": False, "error": "Original video file missing", "styles_applied": 0}

    if not styles or len(styles) == 0:
        status_tracker.set_status(task_id, "failed", 0, "error", "No styles provided")
        return {"success": False, "error": "No styles provided", "styles_applied": 0}

    #  Set initial status
    status_tracker.set_status(task_id, "processing", 0, "starting")
    _send_ws_update(video_id, user_id, "processing", 0, "style_apply", "Starting style application...")

    try:
        logger.info(f"🎨 Starting style application for video {video_id}")
        logger.info(f"   Styles to apply: {styles}")

        status_tracker.set_status(task_id, "processing", 10, "preparing")
        _send_ws_update(video_id, user_id, "processing", 10, "style_apply", "Preparing video...")

        # ========== GET PROCESSED VIDEO DIMENSIONS ==========
        target_width = None
        target_height = None
        processed_path = video.output_video_url

        status_tracker.set_status(task_id, "processing", 20, "analyzing")
        _send_ws_update(video_id, user_id, "processing", 20, "style_apply", "Analyzing video dimensions...")
        
        if processed_path and os.path.exists(processed_path):
            try:
                probe_cmd = [
                    "ffprobe", "-v", "quiet", "-print_format", "json",
                    "-show_streams", processed_path
                ]
                probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                if probe_result.returncode == 0:
                    info = json.loads(probe_result.stdout)
                    for stream in info.get("streams", []):
                        if stream.get("codec_type") == "video":
                            target_width = stream.get("width", 1920)
                            target_height = stream.get("height", 1080)
                            break
            except Exception as e:
                logger.warning(f"Failed to probe processed video: {e}")
        
        if not target_width or not target_height:
            quality_map = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}
            target_width, target_height = quality_map.get(video.output_quality, (1280, 720))
        
        logger.info(f"Target dimensions: {target_width}x{target_height}")
        
        preserve_settings = {
            "fps": getattr(video, 'fps', 'original'),
            "audio_quality": getattr(video, 'audio_quality', 'original'),
            "aspect_ratio": getattr(video, 'aspect_ratio', 'original'),
            "speed": getattr(video, 'speed', 1.0),
            "quality": getattr(video, 'output_quality', '720p'),
        }
        
        output_dir = os.path.dirname(input_path)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results = []
        total_styles = len(styles)
        failed_styles = []
        
        for idx, style in enumerate(styles):
            current_progress = 30 + int((idx / total_styles) * 60)
            
            status_tracker.set_status(task_id, "processing", current_progress, f"applying_{style}")
            _send_ws_update(video_id, user_id, "processing", current_progress, "style_apply", 
                           f"Applying '{style}' style ({idx + 1}/{total_styles})...")
            
            output_filename = f"{video_id}_{style}_{timestamp}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            logger.info(f"🎨 Applying style '{style}' to video {video_id}")
            
            try:
                success = ffmpeg.apply_video_style(
                    input_path=input_path,
                    output_path=output_path,
                    style=style,
                    target_width=target_width,
                    target_height=target_height,
                    preserve_settings=preserve_settings
                )
                
                if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    results.append({
                        "style": style,
                        "output_path": output_path,
                        "output_url": output_path,
                        "file_size": os.path.getsize(output_path)
                    })
                    logger.info(f"✅ Applied style '{style}' to video {video_id}")
                    _send_ws_update(video_id, user_id, "processing", current_progress + 5, "style_apply", 
                                   f"✅ '{style}' style applied")
                else:
                    failed_styles.append(style)
                    logger.error(f"❌ Failed to apply style '{style}' to video {video_id}")
                    _send_ws_update(video_id, user_id, "processing", current_progress, "style_apply", 
                                   f"⚠️ Failed to apply '{style}' style")
            except Exception as e:
                failed_styles.append(style)
                logger.error(f"❌ Exception applying style '{style}': {e}")
        
        # ========== CHECK RESULTS ==========
        if len(results) == 0:
            #  CRITICAL: No styles were applied successfully
            error_msg = f"Failed to apply any styles. Failed styles: {', '.join(failed_styles)}"
            logger.error(f"❌ {error_msg}")
            
            status_tracker.set_status(task_id, "failed", 0, "error", error_msg)
            _send_ws_failed(video_id, user_id, error_msg, self.request.retries, False)
            
            return {
                "success": False,
                "video_id": video_id,
                "error": error_msg,
                "styles_applied": 0,
                "failed_styles": failed_styles
            }
        
        # ========== UPDATE VIDEO - FINALIZING ==========
        status_tracker.set_status(task_id, "processing", 95, "finalizing")
        _send_ws_update(video_id, user_id, "processing", 95, "style_apply", "Finalizing styled video...")
        
        # Use the first successful result
        first_result = results[0]
        
        # Update video in database with new output
        from providers.firebase_provider import FirebaseProvider
        db = FirebaseProvider()
        
        db.save("videos", video_id, {
            "output_video_url": first_result["output_url"],
            "output_path": first_result["output_path"],
            "output_video_size": first_result["file_size"],
            "applied_styles": styles,
            "updated_at": datetime.utcnow().isoformat(),
            "status": "completed",
            "progress": 100,
            "current_step": "completed",
            "processing_completed": datetime.utcnow().isoformat()
        })
        
        video.output_video_url = first_result["output_url"]
        video.output_path = first_result["output_path"]
        video.output_video_size = first_result["file_size"]
        video.applied_styles = styles
        video.status = "completed"
        video.progress = 100
        video.current_step = "completed"
        
        logger.info(f"✅ Video {video_id} updated with new style: {styles[0]}")
        
        # Status: COMPLETED - only if we actually applied styles
        status_tracker.set_status(task_id, "completed", 100, "complete")
        _send_ws_completed(video_id, user_id, first_result["output_url"], 0, 0)
        _send_ws_update(video_id, user_id, "completed", 100, "style_apply", 
                       f"✅ Style '{styles[0]}' applied successfully!")
        _send_ws_progress(video_id, 100, "style_apply", 0)
        
        return {
            "success": True,
            "video_id": video_id,
            "styles_applied": len(results),
            "results": results,
            "failed_styles": failed_styles if failed_styles else None
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Style application failed: {error_msg}")
        logger.error(traceback.format_exc())
        
        # 🔥 Status: FAILED
        status_tracker.set_status(task_id, "failed", 0, "error", error_msg)
        _send_ws_failed(video_id, user_id, error_msg, self.request.retries, False)
        
        return {
            "success": False,
            "video_id": video_id,
            "error": error_msg,
            "styles_applied": 0
        }

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
