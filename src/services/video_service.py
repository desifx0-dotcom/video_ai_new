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
        """Upload and validate a video file with complete tier enforcement."""
        from services.notification_service import NotificationService, NotificationType

        options = options or {}

        # Get user
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")

        # Create a temporary file for processing
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_path = temp_file.name
        temp_file.close()

        try:
            # Save uploaded file to temp location
            if hasattr(file_obj, "save"):
                file_obj.save(temp_path)
            elif hasattr(file_obj, "read"):
                with open(temp_path, "wb") as f:
                    while True:
                        chunk = file_obj.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                raise ProcessingError(f"Unsupported file object type: {type(file_obj)}")

            # Get video duration
            try:
                duration = self.ffmpeg.get_video_duration(temp_path)
            except Exception as e:
                raise ProcessingError(
                    f"Failed to get video duration: {str(e)}", "duration"
                )

            # Detect silent video
            is_silent = self.silent_video_service.is_silent_video(temp_path)

            # Check tier limits
            if is_silent and not self.tier_service.is_silent_video_allowed(user.tier):
                raise TierLimitExceeded(
                    "silent_video",
                    0,
                    0,
                    message=f"Silent videos are not available in {user.tier.value} tier. "
                    f"Upgrade to Starter or higher to process silent videos.",
                    upgrade_url="/pricing",
                )

            # Check duration limit
            max_duration = self.tier_service.get_max_video_length(user.tier, is_silent)
            if duration > max_duration:
                raise ValidationError(
                    f"Video duration ({duration//60} minutes) exceeds maximum for {user.tier.value} tier ({max_duration//60} minutes)"
                )

            # Check monthly limit
            if user.videos_processed_this_month >= user.monthly_video_limit:
                raise TierLimitExceeded(
                    "monthly_videos",
                    user.videos_processed_this_month,
                    user.monthly_video_limit,
                    message=f"You've used {user.videos_processed_this_month} of {user.monthly_video_limit} videos this month.",
                    upgrade_url="/pricing",
                )

            # Check credits
            if user.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
                credits_needed = max(1, int(duration) // 60)
                if user.credits_remaining < credits_needed:
                    raise InsufficientCreditsError(
                        user.credits_remaining,
                        credits_needed,
                        message=f"Insufficient credits: {user.credits_remaining}/{credits_needed} credits needed. "
                        f"Each minute of video costs 1 credit.",
                        upgrade_url="/pricing",
                    )

            # Validate file
            self._validate_upload(user, filename, file_size, content_type)

            # Generate unique ID
            video_id = str(uuid.uuid4())

            # Create permanent upload directory
            upload_dir = Path(tempfile.gettempdir()) / "video_ai" / "uploads" / video_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / "original.mp4"

            # Copy from temp file to final location
            shutil.copy2(temp_path, str(upload_path))

            # Clean up temp file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")

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
                # User-selected options
                output_quality=options.get("quality", "720p"),
                fps=options.get("fps", "original"),
                audio_quality=options.get("audio_quality", "original"),
                aspect_ratio=options.get("aspect_ratio", "original"),
                thumbnail_style=options.get("thumbnail_style", "default"),
                applied_styles=options.get("styles", []),
                auto_transcribe=options.get("auto_transcribe", True),
                generate_chapters=options.get("generate_chapters", False),
                remove_silence=options.get("remove_silence", False),
                translation_language=options.get("translation_language", ""),
                original_fps=options.get("original_fps", 0),
                original_audio_bitrate=options.get("original_audio_bitrate", 0),
                original_width=options.get("original_width", 0),
                original_height=options.get("original_height", 0),
            )

            # ========== Store original video properties ==========
            # Get raw values from options (passed from upload endpoint (for frontend "video details" section))
            raw_fps = options.get("original_fps", 0)
            raw_audio_bitrate = options.get("original_audio_quality", 0)
            raw_aspect_ratio = options.get("original_aspect_ratio", "")

            # Format FPS for display
            if raw_fps and raw_fps > 0:
                video.original_fps = f"{int(raw_fps)} fps"
            else:
                video.original_fps = "unknown"

            # Format Audio Quality for display
            if raw_audio_bitrate and raw_audio_bitrate > 0:
                audio_kbps = int(raw_audio_bitrate / 1000)
                video.original_audio_quality = f"{audio_kbps} kbps"
            else:
                video.original_audio_quality = "unknown"

            # Format Aspect Ratio for display
            if (
                raw_aspect_ratio
                and raw_aspect_ratio != "unknown"
                and ":" in str(raw_aspect_ratio)
            ):
                video.original_aspect_ratio = raw_aspect_ratio
            else:
                video.original_aspect_ratio = "unknown"

            logger.info(
                f"📊 Video details - FPS: {video.original_fps}, Audio: {video.original_audio_quality}, Aspect: {video.original_aspect_ratio}"
            )

            # Store metadata for processing
            video.metadata = {
                "fps": video.fps,
                "audio_quality": video.audio_quality,
                "aspect_ratio": video.aspect_ratio,
                "thumbnail_style": video.thumbnail_style,
                "applied_styles": video.applied_styles,
                "original_fps": raw_fps,
                "original_audio_bitrate": raw_audio_bitrate,
                "original_aspect_ratio": raw_aspect_ratio,
            }

            # Log what's being saved
            logger.info(f"💾 Saving video with options:")
            logger.info(f"   quality: {video.output_quality}")
            logger.info(f"   fps: {video.fps}")
            logger.info(f"   audio_quality: {video.audio_quality}")
            logger.info(f"   aspect_ratio: {video.aspect_ratio}")
            logger.info(f"   thumbnail_style: {video.thumbnail_style}")
            logger.info(f"   styles: {video.applied_styles}")
            logger.info(f"   original_fps: {video.original_fps}")
            logger.info(f"   original_audio_quality: {video.original_audio_quality}")
            logger.info(f"   original_aspect_ratio: {video.original_aspect_ratio}")

            # Set output URL for frontend preview
            video.output_video_url = f"/processed/{video_id}/output.mp4"

            # Save to database
            if self.db:
                self.db.save("videos", video_id, video.to_dict())
                logger.info(f"✅ Video {video_id} saved to database")

            # Create processing job
            job_id = str(uuid.uuid4())
            job_data = {
                "id": job_id,
                "video_id": video_id,
                "user_id": user_id,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "send_email_notification": options.get(
                    "send_email_notification", False
                ),
            }
            if self.db:
                self.db.save("processing_jobs", job_id, job_data)

            # Schedule for deletion
            retention_days = self.tier_service.get_retention_days(user.tier)
            video.schedule_deletion(retention_days)

            # Queue Celery task
            try:
                from tasks.video_tasks import process_video_async

                logger.info(f"📤 Sending options to Celery for video {video_id}:")
                logger.info(f"   quality: {options.get('quality')}")
                logger.info(f"   fps: {options.get('fps')}")
                logger.info(f"   audio_quality: {options.get('audio_quality')}")
                logger.info(f"   aspect_ratio: {options.get('aspect_ratio')}")
                logger.info(f"   thumbnail_style: {options.get('thumbnail_style')}")
                logger.info(f"   styles: {options.get('styles')}")

                process_video_async.delay(video_id, user_id, options)
                logger.info(f"✅ Video {video_id} queued for processing")
            except Exception as e:
                logger.error(f"Failed to queue video for processing: {e}")
                video.status = VideoStatus.UPLOADED
                if self.db:
                    self.db.save("videos", video_id, video.to_dict())

            # Send notification
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

        except Exception as e:
            # Clean up on error
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            raise

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

    def validate_advanced_options(user_tier, options):
        """Validate that advanced options are only used by eligible tiers."""
        advanced_options = [
            "fps",
            "audio_quality",
            "generate_chapters",
            "remove_silence",
        ]
        allowed_tiers = ["pro", "plus", "enterprise"]

        if user_tier not in allowed_tiers:
            for opt in advanced_options:
                if options.get(opt) and options[opt] != "original":
                    raise TierLimitExceeded(
                        "advanced_options",
                        message=f"Advanced option '{opt}' requires Pro tier or higher. Upgrade to access this feature.",
                        upgrade_url="/pricing",
                    )
        return True

    def get_video(self, video_id: str, user_id: str) -> Optional[Any]:
        """Get a video by ID with user ownership check."""
        try:
            if not self.db:
                logger.warning(
                    f"Database not available, returning None for video {video_id}"
                )
                return None

            video_data = self.db.get("videos", video_id)
            if not video_data:
                return None

            # Check if user owns this video
            if video_data.get("user_id") != user_id:
                return None

            # Convert to Video object (same as get_video_by_id)
            from core.domain.entities.video import Video

            def parse_datetime(value):
                if not value:
                    return None
                if isinstance(value, str):
                    try:
                        from datetime import datetime

                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except:
                        return None
                return value

            video = Video(
                id=video_data.get("id"),
                user_id=video_data.get("user_id"),
                original_filename=video_data.get("original_filename"),
                file_size=video_data.get("file_size"),
                duration=video_data.get("duration"),
                mime_type=video_data.get("mime_type", "video/mp4"),
                status=video_data.get("status", "uploaded"),
                video_type=video_data.get("video_type", "speech"),
                title=video_data.get("title"),
                description=video_data.get("description"),
                transcription=video_data.get("transcription"),
                transcription_language=video_data.get("transcription_language"),
                tags=video_data.get("tags", []),
                ai_thumbnails=video_data.get("ai_thumbnails", []),
                extracted_thumbnails=video_data.get("extracted_thumbnails", []),
                selected_thumbnail=video_data.get("selected_thumbnail"),
                output_quality=video_data.get("output_quality", "720p"),
                output_video_url=video_data.get("output_video_url"),
                output_video_size=video_data.get("output_video_size"),
                applied_styles=video_data.get("applied_styles", []),
                processed_tier=video_data.get("processed_tier", "free"),
                created_at=parse_datetime(video_data.get("created_at")),
                updated_at=parse_datetime(video_data.get("updated_at")),
                processing_started=parse_datetime(video_data.get("processing_started")),
                processing_completed=parse_datetime(
                    video_data.get("processing_completed")
                ),
                error_message=video_data.get("error_message"),
                retry_count=video_data.get("retry_count", 0),
            )

            return video

        except Exception as e:
            logger.error(f"Error getting video {video_id}: {e}")
            return None

    def get_video_by_id(self, video_id: str) -> Optional[Any]:
        """Get a video by ID (no user check - for internal use)."""
        try:
            if not self.db:
                return None

            video_data = self.db.get("videos", video_id)
            if not video_data:
                return None

            print(
                f"🔍 DEBUG: Retrieved video {video_id}, original_path: {video_data.get('original_path')}"
            )
            print(f"🔍 DEBUG: output_video_url: {video_data.get('output_video_url')}")

            # Convert dictionary to Video entity
            from core.domain.entities.video import Video

            # Parse datetime fields
            def parse_datetime(value):
                if not value:
                    return None
                if isinstance(value, str):
                    try:
                        from datetime import datetime

                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except:
                        return None
                return value

            # Create Video entity from dictionary
            video = Video(
                id=video_data.get("id"),
                user_id=video_data.get("user_id"),
                original_filename=video_data.get("original_filename"),
                original_path=video_data.get("original_path"),
                file_size=video_data.get("file_size"),
                duration=video_data.get("duration"),
                mime_type=video_data.get("mime_type", "video/mp4"),
                status=video_data.get("status", "uploaded"),
                video_type=video_data.get("video_type", "speech"),
                title=video_data.get("title"),
                description=video_data.get("description"),
                transcription=video_data.get("transcription"),
                transcription_language=video_data.get("transcription_language"),
                tags=video_data.get("tags", []),
                ai_thumbnails=video_data.get("ai_thumbnails", []),
                extracted_thumbnails=video_data.get("extracted_thumbnails", []),
                selected_thumbnail=video_data.get("selected_thumbnail"),
                output_quality=video_data.get("output_quality", "720p"),
                output_video_url=video_data.get("output_video_url"),
                output_video_size=video_data.get("output_video_size"),
                applied_styles=video_data.get("applied_styles", []),
                processed_tier=video_data.get("processed_tier", "free"),
                created_at=parse_datetime(video_data.get("created_at")),
                updated_at=parse_datetime(video_data.get("updated_at")),
                processing_started=parse_datetime(video_data.get("processing_started")),
                processing_completed=parse_datetime(
                    video_data.get("processing_completed")
                ),
                error_message=video_data.get("error_message"),
                retry_count=video_data.get("retry_count", 0),
            )

            return video

        except Exception as e:
            logger.error(f"Error getting video {video_id}: {e}")
            return None

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
        # 🔥 Keep existing output_video_url or set a new one
        if not video.output_video_url:
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

    def update_video(self, video) -> bool:
        """Update video in database."""
        try:
            if not self.db:
                logger.warning("Database not available, cannot update video")
                return False

            self.db.save("videos", video.id, video.to_dict())
            return True

        except Exception as e:
            logger.error(f"Error updating video {video.id}: {e}")
            return False

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

    def get_processing_status(
        self, video_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get processing status for a video."""
        try:
            if not self.db:
                logger.warning("Database not available, returning None")
                return None

            video_data = self.db.get("videos", video_id)

            if not video_data:
                return None

            # Check if video belongs to user
            if video_data.get("user_id") != user_id:
                return None

            # Progress mapping
            status_progress = {
                "uploaded": 5,
                "queued": 10,
                "processing": 15,
                "analyzing": 25,
                "transcribing": 40,
                "generating_title": 50,
                "generating_thumbnails": 60,
                "applying_styles": 75,
                "translating": 85,
                "compressing": 95,
                "completed": 100,
                "failed": 0,
            }

            status = video_data.get("status", "uploaded")
            progress = status_progress.get(status, 0)

            return {
                "video_id": video_id,
                "status": status,
                "progress": progress,
                "error_message": video_data.get("error_message"),
                "current_step": video_data.get("current_step", ""),
                "estimated_time": video_data.get("estimated_time_remaining", 0),
            }

        except Exception as e:
            logger.error(f"Error getting processing status: {e}")
            return None

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

    def generate_chapters(
        self, video_path: str, transcript: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate chapters using FFmpeg scene detection + AI naming.

        Cost: FREE (FFmpeg) + optional ~$0.003 for AI naming (Pro+ tiers)

        Returns:
            List of chapters: [{"timestamp": float, "title": str, "description": str}]
        """
        chapters = []

        # Method 1: Extract existing chapters from video metadata (if any)
        existing_chapters = self._extract_existing_chapters(video_path)
        if existing_chapters:
            return existing_chapters

        # Method 2: Detect scene changes with FFmpeg (FREE)
        scene_changes = self._detect_scene_changes(video_path)

        if not scene_changes:
            # Fallback: Use time-based intervals
            duration = self.ffmpeg.get_video_duration(video_path)
            scene_changes = self._create_time_based_chapters(duration)

        # Method 3: Name chapters using AI (if transcript available and tier allows)
        if transcript and len(transcript) > 100:
            named_chapters = self._name_chapters_with_ai(scene_changes, transcript)
            if named_chapters:
                return named_chapters

        # Fallback: Return chapters with generic names
        for i, timestamp in enumerate(scene_changes):
            chapters.append(
                {
                    "timestamp": timestamp,
                    "title": f"Chapter {i + 1}",
                    "description": f"Chapter starting at {self._format_time(timestamp)}",
                }
            )

        return chapters

    def _extract_existing_chapters(self, video_path: str) -> List[Dict[str, Any]]:
        """Extract existing chapters from video metadata using FFprobe (FREE)."""
        try:
            import subprocess
            import json

            cmd = [
                self.ffmpeg.ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_chapters",
                video_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                chapters = data.get("chapters", [])

                if chapters:
                    return [
                        {
                            "timestamp": float(chap.get("start_time", 0)),
                            "title": chap.get("tags", {}).get(
                                "title", f"Chapter {i+1}"
                            ),
                            "description": chap.get("tags", {}).get("description", ""),
                        }
                        for i, chap in enumerate(chapters)
                    ]

            return []
        except Exception as e:
            logger.warning(f"Failed to extract existing chapters: {e}")
            return []

    def _detect_scene_changes(
        self, video_path: str, threshold: float = 0.3
    ) -> List[float]:
        """
        Detect scene changes using FFmpeg scene detection.
        Cost: FREE (FFmpeg)

        Args:
            video_path: Path to video file
            threshold: Scene change sensitivity (0.1-0.9, lower = more sensitive)

        Returns:
            List of timestamps where scenes change
        """
        try:
            import subprocess
            import re

            # FFmpeg command to detect scene changes
            cmd = [
                self.ffmpeg.ffmpeg_path,
                "-i",
                video_path,
                "-vf",
                f"select='gt(scene,{threshold})',showinfo",
                "-f",
                "null",
                "-",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            # Parse timestamps from output
            timestamps = []
            pattern = r"pts_time:(\d+\.?\d*)"

            for line in result.stderr.split("\n"):
                match = re.search(pattern, line)
                if match:
                    timestamp = float(match.group(1))
                    timestamps.append(timestamp)

            # Remove duplicates and sort
            timestamps = sorted(set(timestamps))

            # Limit to max 20 chapters
            if len(timestamps) > 20:
                timestamps = timestamps[:: len(timestamps) // 20]

            return timestamps

        except Exception as e:
            logger.warning(f"Scene detection failed: {e}")
            return []

    def _create_time_based_chapters(
        self, duration: float, interval: int = 60
    ) -> List[float]:
        """Create time-based chapters every N seconds (FREE)."""
        chapters = []
        for t in range(interval, int(duration), interval):
            chapters.append(float(t))

        # Add final chapter near the end
        if duration > 0:
            chapters.append(duration - 10)

        return chapters

    def _name_chapters_with_ai(
        self, timestamps: List[float], transcript: str
    ) -> List[Dict[str, Any]]:
        """
        Name chapters using AI based on transcript content.
        Cost: ~$0.003 per video (Gemini 1.5 Flash)

        Only used for Pro+ tiers.
        """
        try:
            # Build prompt for AI
            prompt = f"""
            You are a video chapter analyzer. Given these chapter timestamps and the transcript, 
            generate a title and brief description for each chapter.
            
            Transcript: {transcript[:3000]}
            
            Chapter timestamps (in seconds): {timestamps}
            
            Return as JSON array:
            [
                {{"timestamp": 0, "title": "Introduction", "description": "Opening of the video"}},
                ...
            ]
            
            Make titles concise (5-10 words) and descriptions brief (10-20 words).
            """

            from providers.google_provider import GoogleProvider

            google = GoogleProvider()

            response = google.generate_text(
                prompt, model="gemini-1.5-flash", temperature=0.5
            )

            # Parse JSON response
            import json
            import re

            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if json_match:
                chapters = json.loads(json_match.group())
                return chapters

            return []

        except Exception as e:
            logger.warning(f"AI chapter naming failed: {e}")
            return []

    def _format_time(self, seconds: float) -> str:
        """Format seconds to MM:SS or HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def add_chapters_to_video(
        self, video_path: str, output_path: str, chapters: List[Dict[str, Any]]
    ) -> bool:
        """
        Add chapter markers to video using FFmpeg (FREE).

        Args:
            video_path: Input video path
            output_path: Output video path
            chapters: List of chapters with timestamp and title

        Returns:
            True if successful
        """
        try:
            import subprocess
            import tempfile

            # Create metadata file for chapters
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                for i, chapter in enumerate(chapters):
                    start = chapter["timestamp"]
                    end = (
                        chapters[i + 1]["timestamp"] if i + 1 < len(chapters) else None
                    )

                    f.write(f"[CHAPTER]\n")
                    f.write(f"TIMEBASE=1/1000\n")
                    f.write(f"START={int(start * 1000)}\n")
                    if end:
                        f.write(f"END={int(end * 1000)}\n")
                    f.write(f"title={chapter['title']}\n")

                metadata_file = f.name

            # Add chapters to video
            cmd = [
                self.ffmpeg.ffmpeg_path,
                "-i",
                video_path,
                "-i",
                metadata_file,
                "-map_metadata",
                "1",
                "-codec",
                "copy",
                "-y",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            # Cleanup
            os.unlink(metadata_file)

            return result.returncode == 0

        except Exception as e:
            logger.error(f"Failed to add chapters to video: {e}")
            return False
