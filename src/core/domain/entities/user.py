"""
User entity representing a system user.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class Tier(str, Enum):
    """User subscription tier."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    PLUS = "plus"
    ENTERPRISE = "enterprise"


class UserStatus(str, Enum):
    """User account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BANNED = "banned"


@dataclass
class User:
    """User entity."""

    id: str
    email: str
    hashed_password: str
    tier: Tier = Tier.FREE
    status: UserStatus = UserStatus.ACTIVE

    # Profile information
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    language: str = "en"
    timezone: str = "UTC"

    # Usage tracking
    credits_remaining: int = 3
    credits_used_this_month: int = 0
    videos_processed_this_month: int = 0
    monthly_video_limit: int = 3
    total_videos_processed: int = 0
    total_processing_time: float = 0.0

    # Regeneration tracking
    text_regenerations_used: int = 0
    thumbnail_regenerations_used: int = 0

    # Subscription information
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    subscription_cancel_at_period_end: bool = False

    # Settings
    settings: Dict[str, Any] = field(
        default_factory=lambda: {
            "email_notifications": True,
            "push_notifications": True,
            "auto_translate": False,
            "default_quality": "720p",
            "default_style": "cinematic",
            "retention_days": 1,
        }
    )

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    email_verified_at: Optional[datetime] = None

    # Permissions
    is_admin: bool = False
    permissions: list = field(default_factory=list)

    def __post_init__(self):
        """Initialize default values after creation."""
        # Set initial credits based on tier if not set
        if self.credits_remaining == 3 and self.tier != Tier.FREE:
            initial_credits = {
                Tier.FREE: 3,
                Tier.STARTER: 30,
                Tier.PRO: 75,
                Tier.PLUS: 250,
                Tier.ENTERPRISE: 10000,
            }.get(self.tier, 3)
            self.credits_remaining = initial_credits

        # Set monthly limit based on tier
        if self.monthly_video_limit == 3 and self.tier != Tier.FREE:
            monthly_limits = {
                Tier.FREE: 3,
                Tier.STARTER: 30,
                Tier.PRO: 75,
                Tier.PLUS: 250,
                Tier.ENTERPRISE: 10000,
            }.get(self.tier, 3)
            self.monthly_video_limit = monthly_limits

    def is_active(self) -> bool:
        """Check if user is active."""
        return self.status == UserStatus.ACTIVE

    def has_sufficient_credits(self, video_length: int) -> bool:
        """Check if user has sufficient credits for a video."""
        if self.tier in [Tier.PLUS, Tier.ENTERPRISE]:
            return True

        credits_needed = max(1, video_length // 60)
        return self.credits_remaining >= credits_needed

    def can_regenerate_text(self) -> tuple[bool, int, int]:
        """Check if user can regenerate text metadata."""
        max_regens = {
            Tier.FREE: 0,
            Tier.STARTER: 1,
            Tier.PRO: 3,
            Tier.PLUS: 5,
            Tier.ENTERPRISE: 10,
        }.get(self.tier, 0)

        can_regenerate = self.text_regenerations_used < max_regens
        remaining = max_regens - self.text_regenerations_used
        return can_regenerate, remaining, max_regens

    def can_regenerate_thumbnail(self) -> tuple[bool, int, int]:
        """Check if user can regenerate thumbnails."""
        max_regens = {
            Tier.FREE: 0,
            Tier.STARTER: 1,
            Tier.PRO: 3,
            Tier.PLUS: 5,
            Tier.ENTERPRISE: 10,
        }.get(self.tier, 0)

        can_regenerate = self.thumbnail_regenerations_used < max_regens
        remaining = max_regens - self.thumbnail_regenerations_used
        return can_regenerate, remaining, max_regens

    def use_text_regeneration(self) -> bool:
        """Record a text regeneration usage."""
        can_regenerate, remaining, _ = self.can_regenerate_text()
        if can_regenerate:
            self.text_regenerations_used += 1
            self.updated_at = datetime.utcnow()
            return True
        return False

    def use_thumbnail_regeneration(self) -> bool:
        """Record a thumbnail regeneration usage."""
        can_regenerate, remaining, _ = self.can_regenerate_thumbnail()
        if can_regenerate:
            self.thumbnail_regenerations_used += 1
            self.updated_at = datetime.utcnow()
            return True
        return False

    def can_process_video(
        self, video_length: int, is_silent: bool = False
    ) -> tuple[bool, str]:
        """Check if user can process a video."""
        if not self.is_active():
            return False, "Account is not active"

        # Check silent video restriction
        if is_silent and self.tier == Tier.FREE:
            return (
                False,
                "Silent videos are not available in Free tier. Upgrade to Starter.",
            )

        # Check monthly limit
        if self.videos_processed_this_month >= self.monthly_video_limit:
            return (
                False,
                f"Monthly video limit reached: {self.videos_processed_this_month}/{self.monthly_video_limit}",
            )

        # Check duration
        max_duration = self.get_max_video_length(is_silent)
        if video_length > max_duration:
            return False, f"Video duration exceeds maximum for {self.tier.value} tier"

        # Check credits
        if self.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            if not self.has_sufficient_credits(video_length):
                return False, "Insufficient credits"

        return True, ""

    def get_max_video_length(self, is_silent: bool = False) -> int:
        """Get maximum video length in seconds based on tier."""
        if is_silent:
            tier_limits = {
                Tier.FREE: 0,
                Tier.STARTER: 10 * 60,  # 10 minutes
                Tier.PRO: 30 * 60,  # 30 minutes
                Tier.PLUS: 60 * 60,  # 60 minutes
                Tier.ENTERPRISE: 300 * 60,  # 300 minutes
            }
        else:
            tier_limits = {
                Tier.FREE: 3 * 60,
                Tier.STARTER: 30 * 60,
                Tier.PRO: 60 * 60,
                Tier.PLUS: 90 * 60,
                Tier.ENTERPRISE: 300 * 60,
            }
        return tier_limits.get(self.tier, 3 * 60)

    def get_max_quality(self) -> str:
        """Get maximum video quality based on tier."""
        tier_qualities = {
            Tier.FREE: "720p",
            Tier.STARTER: "1080p",
            Tier.PRO: "4k",
            Tier.PLUS: "4k+hdr",
            Tier.ENTERPRISE: "4k+hdr",
        }
        return tier_qualities.get(self.tier, "720p")

    def get_vision_frames(self) -> int:
        """Get number of vision frames for silent video analysis."""
        tier_frames = {
            Tier.FREE: 0,
            Tier.STARTER: 2,
            Tier.PRO: 4,
            Tier.PLUS: 5,
            Tier.ENTERPRISE: 15,
        }
        return tier_frames.get(self.tier, 0)

    def get_ai_thumbnails_count(self) -> int:
        """Get number of AI thumbnails allowed."""
        tier_counts = {
            Tier.FREE: 1,
            Tier.STARTER: 3,
            Tier.PRO: 5,
            Tier.PLUS: 10,
            Tier.ENTERPRISE: 10,
        }
        return tier_counts.get(self.tier, 1)

    def get_extracted_frames_count(self) -> int:
        """Get number of extracted frames allowed."""
        tier_counts = {
            Tier.FREE: 5,
            Tier.STARTER: 8,
            Tier.PRO: 15,
            Tier.PLUS: 25,
            Tier.ENTERPRISE: 25,
        }
        return tier_counts.get(self.tier, 5)

    def record_video_processing(self, video_length: int):
        """Record a video processing event."""
        self.videos_processed_this_month += 1
        self.total_videos_processed += 1
        self.total_processing_time += video_length

        # Deduct credits for non-unlimited tiers
        if self.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            credits_needed = max(1, video_length // 60)
            self.credits_remaining = max(0, self.credits_remaining - credits_needed)

        self.updated_at = datetime.utcnow()

    def add_credits(self, amount: int):
        """Add credits to user account."""
        self.credits_remaining += amount
        self.updated_at = datetime.utcnow()

    def use_credits(self, amount: int):
        """Use credits from user account."""
        self.credits_remaining = max(0, self.credits_remaining - amount)
        self.credits_used_this_month += amount
        self.updated_at = datetime.utcnow()

    def upgrade_tier(self, new_tier: Tier):
        """Upgrade user to a new tier."""
        self.tier = new_tier

        # Update monthly limit
        monthly_limits = {
            Tier.FREE: 3,
            Tier.STARTER: 30,
            Tier.PRO: 75,
            Tier.PLUS: 250,
            Tier.ENTERPRISE: 10000,
        }
        self.monthly_video_limit = monthly_limits.get(new_tier, 3)

        # Reset monthly counters
        self.videos_processed_this_month = 0
        self.credits_used_this_month = 0
        self.text_regenerations_used = 0
        self.thumbnail_regenerations_used = 0

        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "email": self.email,
            "hashed_password": self.hashed_password,
            "tier": self.tier.value,
            "status": self.status.value,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "language": self.language,
            "timezone": self.timezone,
            "credits_remaining": self.credits_remaining,
            "credits_used_this_month": self.credits_used_this_month,
            "videos_processed_this_month": self.videos_processed_this_month,
            "monthly_video_limit": self.monthly_video_limit,
            "total_videos_processed": self.total_videos_processed,
            "text_regenerations_used": self.text_regenerations_used,
            "thumbnail_regenerations_used": self.thumbnail_regenerations_used,
            "is_admin": self.is_admin,
            "settings": self.settings,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "email_verified_at": (
                self.email_verified_at.isoformat() if self.email_verified_at else None
            ),
        }
