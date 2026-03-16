"""
Firebase data models.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

class ProcessingStatus(str, Enum):
    """Video processing status."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    TRANSCRIBING = "transcribing"
    GENERATING_TITLE = "generating_title"
    GENERATING_THUMBNAILS = "generating_thumbnails"
    APPLYING_STYLES = "applying_styles"
    TRANSLATING = "translating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class VideoType(str, Enum):
    """Type of video content."""
    SPEECH = "speech"    # Has audio speech
    SILENT = "silent"    # No speech (music, sound effects only)
    MUSIC = "music"      # Music video
    UNKNOWN = "unknown"

class Tier(str, Enum):
    """User subscription tiers."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    PLUS = "plus"
    ENTERPRISE = "enterprise"

@dataclass_json
@dataclass
class User:
    """User model."""
    id: str
    email: str
    tier: Tier = Tier.FREE
    credits_remaining: int = 0
    videos_processed_this_month: int = 0
    monthly_video_limit: int = 3  # Free tier default
    total_videos_processed: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_end_date: Optional[datetime] = None
    settings: Dict[str, Any] = field(default_factory=lambda: {
        "language": "en",
        "auto_translate": False,
        "default_quality": "720p",
        "email_notifications": True
    })
    is_active: bool = True
    is_admin: bool = False

@dataclass_json
@dataclass
class Video:
    """Video processing job model."""
    id: str
    user_id: str
    original_filename: str
    file_size: int  # in bytes
    duration: float  # in seconds
    video_type: VideoType = VideoType.UNKNOWN
    status: ProcessingStatus = ProcessingStatus.UPLOADED
    upload_date: datetime = field(default_factory=datetime.utcnow)
    processing_started: Optional[datetime] = None
    processing_completed: Optional[datetime] = None
    
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
    
    # Video Processing
    output_quality: str = "720p"
    applied_styles: List[str] = field(default_factory=list)
    output_video_url: Optional[str] = None
    output_video_size: Optional[int] = None
    
    # Translation
    translated_transcription: Optional[str] = None
    translation_language: Optional[str] = None
    translated_title: Optional[str] = None
    translated_description: Optional[str] = None
    
    # Processing Metadata
    processing_time: Optional[float] = None  # in seconds
    ai_costs: Dict[str, float] = field(default_factory=lambda: {
        "transcription": 0.0,
        "title_generation": 0.0,
        "thumbnail_generation": 0.0,
        "translation": 0.0,
        "style_application": 0.0
    })
    total_cost: float = 0.0
    
    # Tier Information (at time of processing)
    processed_tier: Tier = Tier.FREE
    
    # Cleanup
    scheduled_for_deletion: Optional[datetime] = None
    is_deleted: bool = False
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0

@dataclass_json
@dataclass
class ProcessingJob:
    """Background processing job model."""
    id: str
    video_id: str
    user_id: str
    task_id: str  # Celery task ID
    status: ProcessingStatus = ProcessingStatus.UPLOADED
    current_step: Optional[str] = None
    progress: float = 0.0  # 0 to 100
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

@dataclass_json
@dataclass
class Subscription:
    """Subscription model."""
    id: str
    user_id: str
    tier: Tier
    stripe_subscription_id: str
    stripe_price_id: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass_json
@dataclass
class CreditTransaction:
    """Credit transaction model."""
    id: str
    user_id: str
    amount: int  # Positive for addition, negative for usage
    video_id: Optional[str] = None
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass_json
@dataclass
class APILog:
    """API request/response log."""
    id: str
    user_id: Optional[str] = None
    endpoint: str
    method: str
    status_code: int
    request_body: Optional[Dict[str, Any]] = None
    response_body: Optional[Dict[str, Any]] = None
    processing_time_ms: float = 0.0
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass_json
@dataclass
class SystemMetric:
    """System performance metric."""
    id: str
    metric_type: str  # cpu, memory, queue_length, etc.
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: Dict[str, str] = field(default_factory=dict)