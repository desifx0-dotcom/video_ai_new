"""
Video entity representing a processing job - PRODUCTION READY.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class VideoStatus(str, Enum):
    """Video processing status."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    TRANSCRIBING = "transcribing"
    GENERATING_TITLE = "generating_title"
    GENERATING_THUMBNAILS = "generating_thumbnails"
    APPLYING_STYLES = "applying_styles"
    TRANSLATING = "translating"
    COMPRESSING = "compressing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoType(str, Enum):
    """Type of video content."""

    SPEECH = "speech"  # Has speech audio
    SILENT = "silent"  # No speech (music, sound effects only)
    MUSIC = "music"  # Music video
    UNKNOWN = "unknown"


@dataclass
class Video:
    """Video entity - PRODUCTION READY."""

    id: str
    user_id: str
    original_filename: str
    file_size: int  # in bytes
    duration: float  # in seconds
    mime_type: str

    # Processing information
    status: VideoStatus = VideoStatus.UPLOADED
    video_type: VideoType = VideoType.UNKNOWN
    priority: int = 0  # Higher number = higher priority

    # File paths
    original_path: Optional[str] = None
    processing_path: Optional[str] = None
    output_path: Optional[str] = None

    # AI Processing Results
    transcription: Optional[str] = None
    transcription_language: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Thumbnails
    ai_thumbnails: List[Dict[str, Any]] = field(
        default_factory=list
    )  # URLs or paths with metadata
    extracted_thumbnails: List[str] = field(default_factory=list)
    selected_thumbnail: Optional[str] = None

    # Thumbnail style preference
    thumbnail_style: str = "default"

    # Video Processing Options
    output_quality: str = "720p"
    output_format: str = "mp4"
    applied_styles: List[str] = field(default_factory=list)
    aspect_ratio: str = "original"  # here aspect ratio
    output_video_url: Optional[str] = None
    output_video_size: Optional[int] = None

    # Advanced processing options
    fps: str = "original"
    audio_quality: str = "original"
    auto_transcribe: bool = True
    generate_chapters: bool = False
    remove_silence: bool = False

    # Translation
    translated_transcription: Optional[str] = None
    translation_language: Optional[str] = None
    translated_title: Optional[str] = None
    translated_description: Optional[str] = None

    # Processing Metadata
    processing_started: Optional[datetime] = None
    processing_completed: Optional[datetime] = None
    processing_time: Optional[float] = None  # in seconds
    silent_analysis: Optional[Dict[str, Any]] = None

    # for frontend "video details" section
    original_fps: float = 0.0
    original_audio_bitrate: int = 0
    original_width: int = 0
    original_height: int = 0

    # Display versions
    original_fps_display: str = "unknown"
    original_audio_display: str = "unknown"
    original_aspect_display: str = "unknown"

    # Cost tracking
    ai_costs: Dict[str, float] = field(
        default_factory=lambda: {
            "transcription": 0.0,
            "title_generation": 0.0,
            "thumbnail_generation": 0.0,
            "translation": 0.0,
            "style_application": 0.0,
            "video_processing": 0.0,
        }
    )
    total_cost: float = 0.0

    # Tier Information (at time of processing)
    processed_tier: str = "free"

    # Cleanup
    scheduled_for_deletion: Optional[datetime] = None
    is_deleted: bool = False

    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Regeneration tracking
    thumbnail_regenerations: int = 0
    title_regenerations: int = 0
    description_regenerations: int = 0

    # Used concepts for regeneration
    used_thumbnail_concepts: List[str] = field(default_factory=list)
    used_title_concepts: List[str] = field(default_factory=list)

    # 🔥 ADDED: Flag to track if video is silent
    is_silent: bool = False

    chapters: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure status and video_type are strings."""
        # Convert status to string if it's an enum
        if hasattr(self.status, "value"):
            self.status = self.status.value

        # Convert video_type to string if it's an enum
        if hasattr(self.video_type, "value"):
            self.video_type = self.video_type.value

    def update_status(self, new_status: VideoStatus, message: Optional[str] = None):
        """Update video status and record timestamp."""
        self.status = new_status
        self.updated_at = datetime.utcnow()

        # Set processing timestamps
        if new_status == VideoStatus.PROCESSING and not self.processing_started:
            self.processing_started = datetime.utcnow()
        elif new_status == VideoStatus.COMPLETED and not self.processing_completed:
            self.processing_completed = datetime.utcnow()
            if self.processing_started:
                self.processing_time = (
                    self.processing_completed - self.processing_started
                ).total_seconds()

        if message:
            self.error_message = message

    def add_ai_cost(self, service: str, cost: float):
        """Add AI processing cost."""
        if service in self.ai_costs:
            self.ai_costs[service] += cost
        else:
            self.ai_costs[service] = cost

        self.total_cost = sum(self.ai_costs.values())
        self.updated_at = datetime.utcnow()

    def can_retry(self) -> bool:
        """Check if video can be retried."""
        return (
            self.retry_count < self.max_retries and self.status != VideoStatus.COMPLETED
        )

    def schedule_deletion(self, days: int):
        """Schedule video for deletion."""
        from datetime import timedelta

        self.scheduled_for_deletion = datetime.utcnow() + timedelta(days=days)
        self.updated_at = datetime.utcnow()

    def should_be_deleted(self) -> bool:
        """Check if video should be deleted."""
        if self.scheduled_for_deletion:
            return datetime.utcnow() >= self.scheduled_for_deletion
        return False

    def get_progress(self) -> float:
        """Get processing progress percentage."""
        progress_map = {
            VideoStatus.UPLOADED: 5,
            VideoStatus.QUEUED: 10,
            VideoStatus.PROCESSING: 15,
            VideoStatus.ANALYZING: 25,
            VideoStatus.TRANSCRIBING: 40,
            VideoStatus.GENERATING_TITLE: 50,
            VideoStatus.GENERATING_THUMBNAILS: 60,
            VideoStatus.APPLYING_STYLES: 75,
            VideoStatus.TRANSLATING: 85,
            VideoStatus.COMPRESSING: 95,
            VideoStatus.COMPLETED: 100,
            VideoStatus.FAILED: 0,
            VideoStatus.CANCELLED: 0,
        }
        return progress_map.get(self.status, 0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert video to dictionary - PRODUCTION READY."""

        def format_datetime(dt):
            """Safely format datetime to ISO string."""
            if dt is None:
                return None
            if isinstance(dt, str):
                return dt
            if hasattr(dt, "isoformat"):
                return dt.isoformat()
            return str(dt)

        return {
            # Basic Info
            "id": self.id,
            "user_id": self.user_id,
            "original_filename": self.original_filename,
            "original_path": self.original_path,
            "file_size": self.file_size,
            "duration": self.duration,
            "original_fps": getattr(self, "original_fps", "unknown"),
            "original_audio_quality": getattr(
                self, "original_audio_quality", "unknown"
            ),
            "original_aspect_ratio": getattr(self, "original_aspect_ratio", "unknown"),
            "mime_type": self.mime_type,
            "is_silent": self.is_silent,
            # Status
            "status": (
                self.status if isinstance(self.status, str) else self.status.value
            ),
            "video_type": (
                self.video_type
                if isinstance(self.video_type, str)
                else self.video_type.value
            ),
            "progress": self.get_progress(),
            "silent_analysis": self.silent_analysis,
            # AI Results
            "title": self.title,
            "description": self.description,
            "transcription": self.transcription,
            "transcription_language": self.transcription_language,
            "tags": self.tags,
            # Thumbnails
            "ai_thumbnails": self.ai_thumbnails,
            "extracted_thumbnails": self.extracted_thumbnails,
            "selected_thumbnail": self.selected_thumbnail,
            "thumbnail_style": self.thumbnail_style,
            # Processing Options
            "output_quality": self.output_quality,
            "output_format": self.output_format,
            "applied_styles": self.applied_styles,
            "fps": getattr(self, "fps", "original"),
            "audio_quality": getattr(self, "audio_quality", "original"),
            "aspect_ratio": getattr(self, "aspect_ratio", "original"),
            "auto_transcribe": self.auto_transcribe,
            "generate_chapters": self.generate_chapters,
            "remove_silence": self.remove_silence,
            # Output
            "output_video_url": self.output_video_url,
            "output_video_size": self.output_video_size,
            # Translation
            "translated_transcription": self.translated_transcription,
            "translation_language": self.translation_language,
            "translated_title": self.translated_title,
            "translated_description": self.translated_description,
            # Metadata
            "processed_tier": self.processed_tier,
            "processing_time": self.processing_time,
            "total_cost": self.total_cost,
            "ai_costs": self.ai_costs,
            # Timestamps
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "processing_started": format_datetime(self.processing_started),
            "processing_completed": format_datetime(self.processing_completed),
            "scheduled_for_deletion": format_datetime(self.scheduled_for_deletion),
            # Regeneration tracking
            "thumbnail_regenerations": self.thumbnail_regenerations,
            "title_regenerations": self.title_regenerations,
            "description_regenerations": self.description_regenerations,
            "used_thumbnail_concepts": self.used_thumbnail_concepts,
            "used_title_concepts": self.used_title_concepts,
            # Error handling
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }
