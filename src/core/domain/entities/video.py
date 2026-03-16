"""
Video entity representing a processing job.
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
    """Video entity."""

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
    ai_thumbnails: List[str] = field(default_factory=list)  # URLs or paths
    extracted_thumbnails: List[str] = field(default_factory=list)
    selected_thumbnail: Optional[str] = None

    # 🔥 NEW: Thumbnail style preference
    thumbnail_style: str = "default"

    # Video Processing
    output_quality: str = "720p"
    output_format: str = "mp4"
    applied_styles: List[str] = field(default_factory=list)
    output_video_url: Optional[str] = None
    output_video_size: Optional[int] = None

    # 🔥 NEW: Advanced processing options
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
        """Convert video to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "duration": self.duration,
            "status": self.status.value,
            "video_type": self.video_type.value,
            "progress": self.get_progress(),
            # Results
            "title": self.title,
            "description": self.description,
            "transcription": self.transcription,
            "transcription_language": self.transcription_language,
            "tags": self.tags,
            # Thumbnails
            "ai_thumbnails": self.ai_thumbnails,
            "extracted_thumbnails": self.extracted_thumbnails,
            "selected_thumbnail": self.selected_thumbnail,
            # 🔥 NEW: Thumbnail style
            "thumbnail_style": self.thumbnail_style,
            # Output
            "output_video_url": self.output_video_url,
            "output_video_size": self.output_video_size,
            "output_quality": self.output_quality,
            "applied_styles": self.applied_styles,
            # 🔥 NEW: Advanced options
            "fps": self.fps,
            "audio_quality": self.audio_quality,
            "auto_transcribe": self.auto_transcribe,
            "generate_chapters": self.generate_chapters,
            "remove_silence": self.remove_silence,
            # Translation
            "translated_transcription": self.translated_transcription,
            "translation_language": self.translation_language,
            "translated_title": self.translated_title,
            # Metadata
            "processed_tier": self.processed_tier,
            "processing_time": self.processing_time,
            "total_cost": self.total_cost,
            # Timestamps
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processing_started": (
                self.processing_started.isoformat() if self.processing_started else None
            ),
            "processing_completed": (
                self.processing_completed.isoformat()
                if self.processing_completed
                else None
            ),
            "scheduled_for_deletion": (
                self.scheduled_for_deletion.isoformat()
                if self.scheduled_for_deletion
                else None
            ),
            # Error handling
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }
