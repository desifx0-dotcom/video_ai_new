"""
Payment received domain event.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

@dataclass
class PaymentReceived:
    """Domain event emitted when payment is received."""
    
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "payment_received"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Payment data
    payment_id: str
    user_id: str
    amount: float
    currency: str = "usd"
    description: str = ""
    
    # Billing information
    stripe_payment_intent_id: str = ""
    stripe_invoice_id: str = ""
    stripe_customer_id: str = ""
    
    # Payment type
    payment_type: str = ""  # subscription, one_time, upgrade, credit_purchase
    tier: str = ""  # If subscription payment
    
    # User context
    user_email: str = ""
    user_tier: str = ""
    
    # Business metrics
    is_recurring: bool = False
    is_trial: bool = False
    is_upgrade: bool = False
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_revenue_category(self) -> str:
        """Get revenue category for analytics."""
        if self.is_trial:
            return "trial"
        elif self.is_upgrade:
            return "upgrade"
        elif self.is_recurring:
            return "recurring"
        elif self.payment_type == "credit_purchase":
            return "credits"
        else:
            return "one_time"
    
    def get_mrr_impact(self) -> float:
        """Get Monthly Recurring Revenue impact."""
        if not self.is_recurring or self.is_trial:
            return 0
        
        if self.payment_type == "subscription":
            return self.amount
        elif self.payment_type == "upgrade":
            # For upgrades, calculate the increase in MRR
            # This would typically come from comparing old and new tier prices
            return self.amount
        else:
            return 0
    
    def get_arr_impact(self) -> float:
        """Get Annual Recurring Revenue impact."""
        mrr = self.get_mrr_impact()
        return mrr * 12
    
    def is_enterprise_payment(self) -> bool:
        """Check if this is an enterprise payment."""
        return self.tier == "enterprise" or self.amount >= 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "payment_id": self.payment_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "currency": self.currency,
            "description": self.description,
            "payment_type": self.payment_type,
            "tier": self.tier,
            "user_email": self.user_email,
            "user_tier": self.user_tier,
            "is_recurring": self.is_recurring,
            "is_trial": self.is_trial,
            "is_upgrade": self.is_upgrade,
            "revenue_category": self.get_revenue_category(),
            "mrr_impact": self.get_mrr_impact(),
            "arr_impact": self.get_arr_impact(),
            "is_enterprise": self.is_enterprise_payment(),
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "stripe_invoice_id": self.stripe_invoice_id,
            "stripe_customer_id": self.stripe_customer_id,
            "metadata": self.metadata
        }