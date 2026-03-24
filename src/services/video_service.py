"""
Main video processing orchestrator service.
"""

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

from core.domain.entities.video import Video, VideoStatus, VideoType
from core.domain.entities.user import User, Tier
from services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationChannel,
)
from core.domain.value_objects.processing_status import ProcessingState
from core.exceptions import (
    ValidationError,
    TierLimitExceeded,
    InsufficientCreditsError,
    ProcessingError,
    FileUploadError,
    VideoTooLargeError,
    InvalidVideoFormatError,
    SilentVideoDetected,
)
from core.constants import (
    FILE_SIZE_LIMITS,
    DURATION_LIMITS,
    MONTHLY_LIMITS,
    VIDEO_EXTENSIONS,
    VIDEO_MIME_TYPES,
    MAX_UPLOAD_SIZE,
)

from services.user_service import UserService
from services.tier_service import TierService
from services.credit_service import CreditService
from services.quality_service import QualityService
from services.silent_video_service import SilentVideoService
from src.services.transcription_service import TranscriptionService
from services.title_service import TitleService
from services.thumbnail_service import ThumbnailService
from services.style_service import StyleService
from services.translation_service import TranslationService
from services.storage_service import StorageService
from providers.ffmpeg_provider import FFmpegProvider
from providers.firebase_provider import FirebaseProvider


logger = logging.getLogger(__name__)


class VideoService:
    """Main video processing service."""

    def __init__(self):
        self.user_service = UserService()
        self.tier_service = TierService()
        self.credit_service = CreditService()
        self.quality_service = QualityService()
        self.silent_video_service = SilentVideoService()
        self.transcription_service = TranscriptionService()
        self.title_service = TitleService()
        self.thumbnail_service = ThumbnailService()
        self.style_service = StyleService()
        self.translation_service = TranslationService()
        self.storage_service = StorageService()
        self.ffmpeg = FFmpegProvider()

        # Initialize database properly
        try:
            from providers.firebase_provider import FirebaseProvider

            self.db = FirebaseProvider()
            logger.info("✅ VideoService: Firebase initialized successfully")
        except Exception as e:
            logger.error(f"❌ VideoService: Failed to initialize Firebase: {e}")
            # In development, set db to None but don't crash
            if os.getenv("FLASK_ENV") == "development":
                logger.warning("⚠️ VideoService: Using mock mode (no database)")
                self.db = None
            else:
                raise

    def upload_video(
        self,
        user_id: str,
        file_obj,
        filename: str,
        file_size: int,
        content_type: str,
        options: Optional[Dict] = None,
    ) -> Tuple[Video, str]:
        """
        Upload and validate a video file.

        Args:
            user_id: User ID uploading the video
            file_obj: File object
            filename: Original filename
            file_size: File size in bytes
            content_type: MIME type
            options: Processing options

        Returns:
            Tuple of (Video object, upload path)
        """
        from services.notification_service import NotificationService, NotificationType

        options = options or {}

        # Get user
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")

        # Validate file
        self._validate_upload(user, filename, file_size, content_type)

        # Generate unique ID for the video
        video_id = str(uuid.uuid4())

        # Create upload directory
        upload_dir = Path(tempfile.gettempdir()) / "video_ai" / "uploads" / video_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded file
        upload_path = upload_dir / "original.mp4"
        file_obj.save(upload_path)

        # Get video duration
        try:
            duration = self.ffmpeg.get_video_duration(upload_path)
        except Exception as e:
            raise ProcessingError(f"Failed to get video duration: {str(e)}", "duration")

        # Validate duration against tier limits
        max_duration = DURATION_LIMITS.get(user.tier.value, 180)  # Default 3 minutes
        if duration > max_duration:
            raise ValidationError(
                f"Video duration ({duration:.1f}s) exceeds maximum for {user.tier.value} tier ({max_duration}s)"
            )
        # video aspect ratios
        if options.get("aspect_ratio") and options["aspect_ratio"] != "original":
            video.aspect_ratio = options["aspect_ratio"]
            logger.info(f"Will apply aspect ratio: {options['aspect_ratio']}")

        # Check monthly limit
        if user.videos_processed_this_month >= user.monthly_video_limit:
            raise TierLimitExceeded(
                "monthly_videos",
                user.videos_processed_this_month,
                user.monthly_video_limit,
            )

        # Check credits for non-unlimited tiers
        if user.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            credits_needed = max(1, int(duration) // 60)
            if user.credits_remaining < credits_needed:
                raise InsufficientCreditsError(user.credits_remaining, credits_needed)

        # Detect if video is silent (has significant cost savings)
        is_silent = False
        if self.silent_video_service.is_silent_video(upload_path):
            is_silent = True
            logger.info(
                f"Silent video detected for {video_id}, enabling cost-saving mode"
            )

        # Create video entity
        video = Video(
            id=video_id,
            user_id=user_id,
            original_filename=filename,
            file_size=file_size,
            duration=duration,
            mime_type=content_type,
            video_type=VideoType.SILENT if is_silent else VideoType.SPEECH,
            original_path=str(upload_path),
            processed_tier=user.tier.value,
            status="uploaded",
        )
        print("🔍 FRESH VIDEO OBJECT:")
        print(f"  created_at type: {type(video.created_at)}")
        print(f"  created_at value: {video.created_at}")

        video.created_at = video.created_at or datetime.utcnow()
        video.updated_at = video.updated_at or datetime.utcnow()

        # If they're strings, convert them
        if isinstance(video.created_at, str):
            try:
                video.created_at = datetime.fromisoformat(
                    video.created_at.replace("Z", "+00:00")
                )
            except:
                video.created_at = datetime.utcnow()

        # Apply processing options
        if options.get("quality") and options["quality"] != "original":
            video.output_quality = options["quality"]
        else:
            video.output_quality = self.quality_service.get_default_quality(user.tier)

        if options.get("styles"):
            video.applied_styles = options["styles"]

        if options.get("translation_language"):
            video.translation_language = options["translation_language"]

        if options.get("thumbnail_style"):
            video.thumbnail_style = options["thumbnail_style"]

        if options.get("fps"):
            video.fps = options["fps"]

        if options.get("audio_quality"):
            video.audio_quality = options["audio_quality"]

        if options.get("auto_transcribe") is not None:
            video.auto_transcribe = options["auto_transcribe"]

        if options.get("generate_chapters") is not None:
            video.generate_chapters = options["generate_chapters"]

        if options.get("remove_silence") is not None:
            video.remove_silence = options["remove_silence"]

        # Check if user opted in for email notification (for Pro/Enterprise)
        send_email_notification = options.get("send_email_notification", False)

        # Save to database
        if self.db:
            self.db.save("videos", video_id, video.to_dict())
        else:
            logger.warning(f"⚠️ Database not available, video {video_id} not saved")

        # Create processing job
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "video_id": video_id,
            "user_id": user_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "send_email_notification": send_email_notification,
        }
        if self.db:
            self.db.save("processing_jobs", job_id, job_data)

        # Schedule for deletion based on tier
        retention_days = self.tier_service.get_retention_days(user.tier)
        video.schedule_deletion(retention_days)

        # Move Celery task to background WITHOUT blocking the response
        try:
            # Try to import celery task here to avoid circular imports
            from tasks.video_tasks import process_video_async

            # Start async processing in the background
            process_video_async.delay(video_id, user_id, options)
            logger.info(f"✅ Video {video_id} queued for processing")

        except Exception as e:
            logger.error(f"Failed to queue video for processing: {e}")
            print(f"⚠️ Background processing unavailable: {e}")
            # Update video status to indicate it needs manual processing
            video.status = VideoStatus.UPLOADED
            if self.db:
                self.db.save("videos", video_id, video.to_dict())

        # print(f"✅ Video {video_id} uploaded successfully to database")
        # print(f"⚠️ Background processing disabled - Redis not configured")

        # Send notification about upload started (in-app only)
        try:
            notification_service = NotificationService()
            notification_service.send_notification(
                user_id=user_id,
                notification_type=NotificationType.VIDEO_PROCESSING_STARTED,
                data={
                    "video_id": video_id,
                    "video_title": filename,
                    "message": f'Your video "{filename}" has been uploaded and queued for processing.',
                },
                channels=[
                    NotificationChannel.IN_APP,
                    NotificationChannel.WEBSOCKET,
                ],
            )
        except Exception as e:
            logger.error(f"Failed to send upload notification: {e}")

        return video, str(upload_path)

    def _validate_upload(self, user, filename, file_size, content_type):
        """Validate file upload against user tier and file constraints."""

        # Import constants if not already imported
        from core.constants import (
            MAX_UPLOAD_SIZE,
            ALLOWED_VIDEO_EXTENSIONS,
            ALLOWED_VIDEO_MIME_TYPES,
        )

        # Check file size
        max_size = getattr(user, "max_upload_size", MAX_UPLOAD_SIZE)
        if file_size > max_size:
            raise FileUploadError(
                f"File size exceeds maximum allowed size of {max_size // (1024*1024)}MB"
            )

        # Check file extension
        import os

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise InvalidVideoFormatError(
                f"File extension {ext} not allowed. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}"
            )

        # Check mime type if provided
        if content_type and content_type not in ALLOWED_VIDEO_MIME_TYPES:
            # This is a warning, not an error - some browsers send incorrect mime types
            logger.warning(f"Unexpected content type: {content_type}")

        # Check user's remaining quota
        if user.videos_processed_this_month >= user.monthly_video_limit:
            raise TierLimitExceeded(
                "monthly_videos",
                user.videos_processed_this_month,
                user.monthly_video_limit,
            )

        logger.info(f"File validation passed for {filename}")

    def get_video_by_id(self, video_id: str, user_id: str = None) -> Optional[Video]:
        """Get video by ID."""
        if not self.db:
            return None

        video_data = self.db.get("videos", video_id)
        if not video_data:
            return None

        # If user_id is provided, verify ownership
        if user_id and video_data.get("user_id") != user_id:
            return None

        return self._dict_to_video(video_data)

    def _dict_to_video(self, data: Dict[str, Any]) -> Video:
        """Convert dictionary to Video entity."""
        from core.domain.entities.video import Video, VideoStatus, VideoType

        return Video(
            id=data["id"],
            user_id=data["user_id"],
            original_filename=data["original_filename"],
            file_size=data["file_size"],
            duration=data["duration"],
            mime_type=data.get("mime_type", "video/mp4"),
            status=VideoStatus(data.get("status", "uploaded")),
            video_type=VideoType(data.get("video_type", "speech")),
            original_path=data.get("original_path"),
            output_path=data.get("output_path"),
            output_video_url=data.get("output_video_url"),
            output_quality=data.get("output_quality", "720p"),
            applied_styles=data.get("applied_styles", []),
            title=data.get("title"),
            description=data.get("description"),
            transcription=data.get("transcription"),
            tags=data.get("tags", []),
            ai_thumbnails=data.get("ai_thumbnails", []),
            extracted_thumbnails=data.get("extracted_thumbnails", []),
            selected_thumbnail=data.get("selected_thumbnail"),
            processed_tier=data.get("processed_tier", "free"),
            processing_time=data.get("processing_time"),
            total_cost=data.get("total_cost", 0.0),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data["created_at"], str)
                else data["created_at"]
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if isinstance(data["updated_at"], str)
                else data["updated_at"]
            ),
            processing_started=(
                datetime.fromisoformat(data["processing_started"])
                if data.get("processing_started")
                else None
            ),
            processing_completed=(
                datetime.fromisoformat(data["processing_completed"])
                if data.get("processing_completed")
                else None
            ),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            # New fields
            thumbnail_style=data.get("thumbnail_style", "default"),
            fps=data.get("fps", "original"),
            audio_quality=data.get("audio_quality", "original"),
            auto_transcribe=data.get("auto_transcribe", True),
            generate_chapters=data.get("generate_chapters", False),
            remove_silence=data.get("remove_silence", False),
        )

    def process_video(
        self, video_id: str, user_id: str, options: Dict[str, Any] = None
    ) -> Video:
        """Process video with given options."""
        options = options or {}

        # Get video
        video = self.get_video_by_id(video_id)
        if not video:
            raise ProcessingError(f"Video not found: {video_id}")

        # Update status to processing
        video.status = "processing"
        video.processing_started = datetime.utcnow()
        self.update_video(video)

        # TODO: Add actual processing logic here
        # For now, simulate processing
        import time

        time.sleep(2)

        # Update status to completed
        video.status = "completed"
        video.processing_completed = datetime.utcnow()
        video.output_video_url = f"/processed/{video_id}/output.mp4"
        video.output_video_size = video.file_size
        self.update_video(video)

        return video

    def get_unprocessed_count(self, user_id: str) -> int:
        """
        Get count of unprocessed videos for a user.
        Unprocessed = pending + processing
        """
        try:
            if not self.db:
                logger.debug(
                    f"Database not available, returning 0 for unprocessed count"
                )
                return 0

            # Query for videos with status 'pending' or 'processing'
            filters = {"user_id": user_id, "status": {"$in": ["pending", "processing"]}}
            videos = self.db.query("videos", filters=filters)
            return len(videos) if videos else 0
        except Exception as e:
            logger.error(f"Error getting unprocessed count for user {user_id}: {e}")
            return 0

    def get_processing_count(self, user_id: str) -> int:
        """Get count of currently processing videos for a user."""
        try:
            if not self.db:
                logger.debug(
                    f"Database not available, returning 0 for processing count"
                )
                return 0

            filters = {"user_id": user_id, "status": "processing"}
            videos = self.db.query("videos", filters=filters)
            return len(videos) if videos else 0
        except Exception as e:
            logger.error(f"Error getting processing count for user {user_id}: {e}")
            return 0

    def get_user_videos_count(self, user_id: str) -> int:
        """Get total count of videos for a user."""
        try:
            if not self.db:
                logger.debug(
                    f"Database not available, returning 0 for total videos count"
                )
                return 0

            filters = {"user_id": user_id}
            return self.db.count("videos", filters=filters)
        except Exception as e:
            logger.error(f"Error getting videos count for user {user_id}: {e}")
            return 0

    def get_completed_count(self, user_id: str) -> int:
        """Get count of completed videos for a user."""
        try:
            if not self.db:
                logger.debug(f"Database not available, returning 0 for completed count")
                return 0

            filters = {"user_id": user_id, "status": "completed"}
            videos = self.db.query("videos", filters=filters)
            return len(videos) if videos else 0
        except Exception as e:
            logger.error(f"Error getting completed count for user {user_id}: {e}")
            return 0

    def get_failed_count(self, user_id: str) -> int:
        """Get count of failed videos for a user."""
        try:
            if not self.db:
                logger.debug(f"Database not available, returning 0 for failed count")
                return 0

            filters = {"user_id": user_id, "status": "failed"}
            videos = self.db.query("videos", filters=filters)
            return len(videos) if videos else 0
        except Exception as e:
            logger.error(f"Error getting failed count for user {user_id}: {e}")
            return 0

    def get_recent_videos(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent videos for a user."""
        try:
            if not self.db:
                logger.debug(
                    f"Database not available, returning empty list for recent videos"
                )
                return []

            # Query videos for this user, ordered by created_at descending
            videos = self.db.query(
                "videos",
                filters={"user_id": user_id},
                order_by="created_at",
                descending=True,
                limit=limit,
            )

            # Convert to list and return
            return list(videos) if videos else []

        except Exception as e:
            logger.error(f"Failed to get recent videos for user {user_id}: {e}")
            return []

    def get_user_videos(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all videos for a user."""
        try:
            if not self.db:
                logger.debug(f"Database not available, returning empty list")
                return []

            # Query all videos for this user
            videos = self.db.query(
                "videos",
                filters={"user_id": user_id},
                order_by="created_at",
                descending=True,
            )

            return list(videos) if videos else []

        except Exception as e:
            logger.error(f"Error getting user videos for {user_id}: {e}")
            return []

    def get_user_videos_paginated(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 10,
        search: str = "",
        status: str = "",
        sort: str = "newest",
    ) -> Dict[str, Any]:
        """Get paginated videos with filters."""
        try:
            if not self.db:
                return {
                    "videos": [],
                    "total": 0,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": 0,
                }

            # Build filters
            filters = {"user_id": user_id}
            if status:
                filters["status"] = status

            # Get total count
            total = self.db.count("videos", filters=filters)

            # Determine sort order
            order_by = "created_at"
            descending = True

            if sort == "oldest":
                descending = False
            elif sort == "name_asc":
                order_by = "title"
                descending = False
            elif sort == "name_desc":
                order_by = "title"
                descending = True
            elif sort == "size":
                order_by = "file_size"
                descending = True
            elif sort == "duration":
                order_by = "duration"
                descending = True

            # Calculate offset
            offset = (page - 1) * per_page

            # Get videos
            videos = self.db.query(
                "videos",
                filters=filters,
                order_by=order_by,
                descending=descending,
                limit=per_page,
                offset=offset,
            )

            total_pages = (total + per_page - 1) // per_page

            return {
                "videos": videos or [],
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
            }

        except Exception as e:
            logger.error(f"Error getting paginated videos: {e}")
            return {
                "videos": [],
                "total": 0,
                "page": page,
                "per_page": per_page,
                "total_pages": 0,
            }
