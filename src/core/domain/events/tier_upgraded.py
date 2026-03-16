"""
Tier upgraded domain event.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

from ...domain.value_objects.tier import Tier

@dataclass
class TierUpgraded:
    """Domain event emitted when user upgrades their tier."""
    
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "tier_upgraded"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Event data
    user_id: str
    from_tier: Tier
    to_tier: Tier
    upgrade_price: float  # Amount paid for upgrade
    
    # Billing information
    stripe_customer_id: str = ""
    stripe_subscription_id: str = ""
    stripe_invoice_id: str = ""
    
    # User context
    user_email: str = ""
    previous_monthly_limit: int = 0
    new_monthly_limit: int = 0
    
    # Upgrade reason
    upgrade_reason: str = ""  # manual, auto, trial_ended, etc.
    is_annual: bool = False
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_value_proposition(self) -> Dict[str, Any]:
        """Get value proposition of the upgrade."""
        tier_features = {
            Tier.FREE: {"videos": 3, "quality": "720p", "retention": "24h"},
            Tier.STARTER: {"videos": 50, "quality": "1080p", "retention": "7d"},
            Tier.PRO: {"videos": 100, "quality": "4K", "retention": "30d"},
            Tier.PLUS: {"videos": 500, "quality": "4K+HDR", "retention": "90d"},
            Tier.ENTERPRISE: {"videos": "unlimited", "quality": "best", "retention": "custom"}
        }
        
        from_features = tier_features.get(self.from_tier, {})
        to_features = tier_features.get(self.to_tier, {})
        
        return {
            "from": from_features,
            "to": to_features,
            "improvements": {
                "videos_increase": self._calculate_increase(from_features.get("videos", 0), 
                                                          to_features.get("videos", 0)),
                "quality_upgrade": from_features.get("quality") != to_features.get("quality"),
                "retention_increase": self._calculate_retention_increase(
                    from_features.get("retention", "24h"),
                    to_features.get("retention", "24h")
                )
            }
        }
    
    def _calculate_increase(self, from_val, to_val) -> str:
        """Calculate percentage increase."""
        if from_val == 0 or to_val in ["unlimited", "custom"]:
            return "unlimited"
        
        try:
            increase = ((to_val - from_val) / from_val) * 100
            return f"{increase:.0f}%"
        except (TypeError, ValueError):
            return "n/a"
    
    def _calculate_retention_increase(self, from_retention: str, to_retention: str) -> str:
        """Calculate retention increase."""
        def parse_retention(retention: str) -> int:
            if retention.endswith("h"):
                return int(retention[:-1]) / 24
            elif retention.endswith("d"):
                return int(retention[:-1])
            elif retention == "custom":
                return 365
            return 1
        
        from_days = parse_retention(from_retention)
        to_days = parse_retention(to_retention)
        
        if to_days > from_days:
            increase = ((to_days - from_days) / from_days) * 100
            return f"{increase:.0f}%"
        return "same"
    
    def get_revenue_impact(self) -> Dict[str, float]:
        """Calculate revenue impact of the upgrade."""
        monthly_prices = {
            Tier.FREE: 0,
            Tier.STARTER: 24,
            Tier.PRO: 79,
            Tier.PLUS: 250,
            Tier.ENTERPRISE: 999  # average
        }
        
        from_price = monthly_prices.get(self.from_tier, 0)
        to_price = monthly_prices.get(self.to_tier, 0)
        
        monthly_increase = to_price - from_price
        annual_increase = monthly_increase * 12
        
        if self.is_annual:
            # Apply annual discount (typically 20%)
            annual_increase *= 0.8
        
        return {
            "monthly_increase": monthly_increase,
            "annual_increase": annual_increase,
            "upgrade_price": self.upgrade_price,
            "lifetime_value_increase": annual_increase * 3  # Assuming 3-year retention
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        value_prop = self.get_value_proposition()
        revenue_impact = self.get_revenue_impact()
        
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "from_tier": self.from_tier.value,
            "to_tier": self.to_tier.value,
            "upgrade_price": self.upgrade_price,
            "user_email": self.user_email,
            "upgrade_reason": self.upgrade_reason,
            "is_annual": self.is_annual,
            "value_proposition": value_prop,
            "revenue_impact": revenue_impact,
            "stripe_customer_id": self.stripe_customer_id,
            "stripe_subscription_id": self.stripe_subscription_id,
            "metadata": self.metadata
        }