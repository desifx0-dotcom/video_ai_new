"""
Video processed domain event.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

from ...domain.entities.video import Video
from ...domain.entities.user import User

@dataclass
class VideoProcessed:
    """Domain event emitted when video processing is completed."""
    
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "video_processed"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Event data
    video_id: str
    user_id: str
    processing_time: float  # in seconds
    total_cost: float
    video_type: str
    tier: str
    
    # Processing results
    output_video_url: str
    output_video_size: int
    thumbnail_url: str
    
    # AI results
    has_transcription: bool = False
    has_translation: bool = False
    styles_applied: list = field(default_factory=list)
    
    # User context
    user_email: str = ""
    user_tier: str = ""
    
    # System context
    worker_id: str = ""
    queue_name: str = ""
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_video_and_user(cls, video: Video, user: User) -> 'VideoProcessed':
        """Create event from video and user entities."""
        return cls(
            video_id=video.id,
            user_id=video.user_id,
            processing_time=video.processing_time or 0.0,
            total_cost=video.total_cost,
            video_type=video.video_type.value,
            tier=video.processed_tier,
            output_video_url=video.output_video_url or "",
            output_video_size=video.output_video_size or 0,
            thumbnail_url=video.selected_thumbnail or "",
            has_transcription=bool(video.transcription),
            has_translation=bool(video.translated_transcription),
            styles_applied=video.applied_styles,
            user_email=user.email,
            user_tier=user.tier.value,
            metadata={
                "original_filename": video.original_filename,
                "duration": video.duration,
                "output_quality": video.output_quality,
                "retry_count": video.retry_count
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "video_id": self.video_id,
            "user_id": self.user_id,
            "processing_time": self.processing_time,
            "total_cost": self.total_cost,
            "video_type": self.video_type,
            "tier": self.tier,
            "output_video_url": self.output_video_url,
            "output_video_size": self.output_video_size,
            "thumbnail_url": self.thumbnail_url,
            "has_transcription": self.has_transcription,
            "has_translation": self.has_translation,
            "styles_applied": self.styles_applied,
            "user_email": self.user_email,
            "user_tier": self.user_tier,
            "worker_id": self.worker_id,
            "queue_name": self.queue_name,
            "metadata": self.metadata
        }
    
    def get_cost_breakdown(self) -> Dict[str, float]:
        """Get cost breakdown for analytics."""
        # This would typically come from the video's ai_costs
        # For now, return a simplified version
        return {
            "total": self.total_cost,
            "transcription": self.total_cost * 0.3 if self.has_transcription else 0,
            "thumbnail_generation": self.total_cost * 0.2,
            "style_application": self.total_cost * 0.3 if self.styles_applied else 0,
            "translation": self.total_cost * 0.1 if self.has_translation else 0,
            "video_processing": self.total_cost * 0.1
        }
    
    def is_profitable(self) -> bool:
        """Check if processing was profitable based on tier."""
        # Free tier videos are always "profitable" since user doesn't pay
        if self.tier == "free":
            return True
        
        # For paid tiers, check if cost is less than tier value
        tier_minimum_value = {
            "starter": 0.48,  # $24 / 50 videos = $0.48 per video
            "pro": 0.79,      # $79 / 100 videos = $0.79 per video
            "plus": 0.50,     # $250 / 500 videos = $0.50 per video
            "enterprise": 0.10  # Approximate
        }
        
        expected_value = tier_minimum_value.get(self.tier, 1.00)
        return self.total_cost < expected_value