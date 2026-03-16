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
    credits_remaining: int = 0
    videos_processed_this_month: int = 0
    monthly_video_limit: int = 3  # Free tier default
    total_videos_processed: int = 0
    total_processing_time: float = 0.0  # in seconds

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

    def is_active(self) -> bool:
        """Check if user is active."""
        return self.status == UserStatus.ACTIVE

    def has_sufficient_credits(self, video_length: int) -> bool:
        """
        Check if user has sufficient credits for a video.
        Returns True for unlimited tiers.
        """
        if self.tier in [Tier.PLUS, Tier.ENTERPRISE]:
            return True

        # Calculate credits needed (1 credit per minute)
        credits_needed = max(1, video_length // 60)
        return self.credits_remaining >= credits_needed

    def can_process_video(self, video_length: int) -> tuple[bool, str]:
        """
        Check if user can process a video.
        Returns (can_process, reason)
        """
        # Check if account is active
        if not self.is_active():
            return False, "Account is not active"

        # Check monthly limit
        if self.videos_processed_this_month >= self.monthly_video_limit:
            return False, "Monthly video limit reached"

        # Check video length against tier limits
        max_length = self.get_max_video_length()
        if video_length > max_length:
            return False, f"Video exceeds maximum length for {self.tier.value} tier"

        # Check credits for non-unlimited tiers
        if self.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            if not self.has_sufficient_credits(video_length):
                return False, "Insufficient credits"

        return True, ""

    def get_max_video_length(self) -> int:
        """Get maximum video length in seconds based on tier."""
        tier_limits = {
            Tier.FREE: 3 * 60,  # 3 minutes
            Tier.STARTER: 30 * 60,  # 30 minutes
            Tier.PRO: 60 * 60,  # 60 minutes
            Tier.PLUS: 120 * 60,  # 120 minutes
            Tier.ENTERPRISE: 300 * 60,  # 300 minutes (5 hours)
        }
        return tier_limits.get(self.tier, 3 * 60)

    def get_quality_settings(self) -> Dict[str, Any]:
        """Get video quality settings based on tier."""
        from core.config.settings import settings

        tier_config = settings.get(f"tiers.{self.tier.value}", {})
        return tier_config.get("quality", {})

    def record_video_processing(self, video_length: int, cost: float = 0.0):
        """Record a video processing event."""
        self.videos_processed_this_month += 1
        self.total_videos_processed += 1
        self.total_processing_time += video_length

        # Deduct credits for non-unlimited tiers
        if self.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            credits_needed = max(1, video_length // 60)
            self.credits_remaining = max(0, self.credits_remaining - credits_needed)

        self.updated_at = datetime.utcnow()

    def upgrade_tier(self, new_tier: Tier):
        """Upgrade user to a new tier."""
        self.tier = new_tier

        # Update monthly limit based on new tier
        tier_limits = {
            Tier.FREE: 3,
            Tier.STARTER: 50,
            Tier.PRO: 100,
            Tier.PLUS: 500,
            Tier.ENTERPRISE: 10000,  # Essentially unlimited
        }
        self.monthly_video_limit = tier_limits.get(new_tier, 3)

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
            "videos_processed_this_month": self.videos_processed_this_month,
            "monthly_video_limit": self.monthly_video_limit,
            "total_videos_processed": self.total_videos_processed,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "email_verified": self.email_verified_at is not None,
        }
