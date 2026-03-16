"""
Subscription entity.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class SubscriptionStatus(str, Enum):
    """Subscription status."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class BillingCycle(str, Enum):
    """Billing cycle."""
    MONTHLY = "monthly"
    YEARLY = "yearly"
    QUARTERLY = "quarterly"

@dataclass
class Subscription:
    """Subscription entity."""
    
    # === FIELDS WITHOUT DEFAULTS (MUST COME FIRST) ===
    id: str
    user_id: str
    tier: str
    stripe_subscription_id: str
    stripe_customer_id: str
    stripe_price_id: str
    current_period_start: datetime
    current_period_end: datetime
    amount: float  # in USD
    
    # === FIELDS WITH DEFAULTS (MUST COME AFTER) ===
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    cancel_at_period_end: bool = False
    currency: str = "usd"
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    
    # Features (copied from tier config at time of subscription)
    features: dict = field(default_factory=dict)
    
    # Payment history
    last_payment_date: Optional[datetime] = None
    next_payment_date: Optional[datetime] = None
    
    # Trial information
    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    is_in_trial: bool = False
    
    # Metadata
    metadata: dict = field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    cancelled_at: Optional[datetime] = None
    
    def is_active(self) -> bool:
        """Check if subscription is active."""
        return self.status == SubscriptionStatus.ACTIVE and not self.cancel_at_period_end
    
    def is_cancelled(self) -> bool:
        """Check if subscription is cancelled."""
        return self.status == SubscriptionStatus.CANCELLED or self.cancel_at_period_end
    
    def is_in_grace_period(self) -> bool:
        """Check if subscription is in grace period."""
        if self.status == SubscriptionStatus.PAST_DUE:
            # Give 3 days grace period
            from datetime import timedelta
            grace_period_end = self.current_period_end + timedelta(days=3)
            return datetime.utcnow() <= grace_period_end
        return False
    
    def days_until_renewal(self) -> int:
        """Get days until subscription renewal."""
        if not self.current_period_end:
            return 0
        
        delta = self.current_period_end - datetime.utcnow()
        return max(0, delta.days)
    
    def should_renew(self) -> bool:
        """Check if subscription should be renewed."""
        return self.is_active() and not self.cancel_at_period_end
    
    def cancel(self):
        """Cancel the subscription."""
        if not self.cancelled_at:
            self.cancelled_at = datetime.utcnow()
        self.cancel_at_period_end = True
        self.updated_at = datetime.utcnow()
    
    def update_status(self, new_status: SubscriptionStatus):
        """Update subscription status."""
        self.status = new_status
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert subscription to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tier": self.tier,
            "status": self.status.value,
            "amount": self.amount,
            "currency": self.currency,
            "billing_cycle": self.billing_cycle.value,
            "current_period_start": self.current_period_start.isoformat(),
            "current_period_end": self.current_period_end.isoformat(),
            "cancel_at_period_end": self.cancel_at_period_end,
            "days_until_renewal": self.days_until_renewal(),
            "is_active": self.is_active(),
            "is_in_trial": self.is_in_trial,
            "features": self.features,
            "created_at": self.created_at.isoformat(),
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None
        }

