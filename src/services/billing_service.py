"""
Billing and subscription service - Production Ready
"""

import stripe
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import uuid4
import os

from core.domain.entities.user import User, Tier
from core.domain.entities.subscription import (
    Subscription,
    SubscriptionStatus,
    BillingCycle,
)
from core.exceptions import (
    ValidationError,
    SubscriptionError,
    PaymentError,
    ExternalServiceError,
)
from core.constants import (
    PRICE_TIERS,
    YEARLY_DISCOUNT,
    TRIAL_PERIOD,
    PAYMENT_GRACE_PERIOD,
)
from providers.stripe_provider import StripeProvider
from providers.firebase_provider import FirebaseProvider

logger = logging.getLogger(__name__)


class BillingService:
    """Billing and subscription management service - Production Ready"""

    # Monthly credits per tier
    MONTHLY_CREDITS = {
        "free": 3,
        "starter": 50,
        "pro": 200,
        "plus": 750,
        "enterprise": 9999,
    }

    def __init__(self):
        self.stripe = StripeProvider()
        self.db = FirebaseProvider()  # ✅ Fixed: Initialize database

        # Check if Stripe is configured
        stripe_key = os.getenv("STRIPE_SECRET_KEY")
        self.stripe_enabled = bool(stripe_key and stripe_key.startswith("sk_"))

        if not self.stripe_enabled:
            logger.warning("⚠️ Stripe not configured - using mock mode")

    # ============================================================
    # PRICING PLANS
    # ============================================================

    def get_pricing_plans(self) -> List[Dict[str, Any]]:
        """Get all pricing plans with features."""
        plans = [
            {
                "id": "free",
                "name": "Free",
                "price": 0,
                "currency": "USD",
                "interval": "monthly",
                "credits_per_month": self.MONTHLY_CREDITS["free"],
                "features": [
                    "3 videos/month",
                    "3 minutes max length",
                    "720p output",
                    "1 AI thumbnail",
                    "3 video styles",
                    "Free translation",
                    "24-hour retention",
                ],
            },
            {
                "id": "starter",
                "name": "Starter",
                "price": 24,
                "currency": "USD",
                "interval": "monthly",
                "yearly_price": 230.40,
                "credits_per_month": self.MONTHLY_CREDITS["starter"],
                "features": [
                    "50 videos/month",
                    "30 minutes max length",
                    "1080p output",
                    "3 AI thumbnails",
                    "All 20+ video styles",
                    "Priority processing",
                    "7-day retention",
                    "Silent video analysis",
                ],
            },
            {
                "id": "pro",
                "name": "Pro",
                "price": 79,
                "currency": "USD",
                "interval": "monthly",
                "yearly_price": 758.40,
                "credits_per_month": self.MONTHLY_CREDITS["pro"],
                "features": [
                    "200 videos/month",
                    "60 minutes max length",
                    "4K output",
                    "5 AI thumbnails",
                    "All premium styles",
                    "Gemini Pro + GPT-4",
                    "Express processing",
                    "30-day retention",
                    "60fps interpolation",
                ],
            },
            {
                "id": "plus",
                "name": "Plus",
                "price": 250,
                "currency": "USD",
                "interval": "monthly",
                "yearly_price": 2400,
                "credits_per_month": self.MONTHLY_CREDITS["plus"],
                "features": [
                    "750 videos/month",
                    "120 minutes max length",
                    "4K+HDR output",
                    "10 AI thumbnails",
                    "All premium + custom styles",
                    "GPT-4 Turbo",
                    "VIP processing",
                    "90-day retention",
                    "Priority support",
                ],
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "price": "Custom",
                "currency": "USD",
                "interval": "monthly",
                "credits_per_month": self.MONTHLY_CREDITS["enterprise"],
                "features": [
                    "Unlimited videos",
                    "Highest quality",
                    "White-label option",
                    "On-premise deployment",
                    "Dedicated account manager",
                    "SLA guarantees",
                ],
            },
        ]
        return plans

    def get_user_plans(self, user_id: str) -> Dict[str, Any]:
        """Get user's current plan and available upgrades."""
        user = self._get_user(user_id)
        if not user:
            return {"current": None, "upgrades": []}

        current_tier = user.tier.value
        all_tiers = ["free", "starter", "pro", "plus", "enterprise"]
        tier_index = all_tiers.index(current_tier) if current_tier in all_tiers else 0

        # Available upgrades are tiers above current
        upgrades = (
            all_tiers[tier_index + 1 :] if tier_index < len(all_tiers) - 1 else []
        )

        # Get plan details for each upgrade
        upgrade_plans = []
        all_plans = self.get_pricing_plans()
        for tier in upgrades:
            for plan in all_plans:
                if plan["id"] == tier:
                    upgrade_plans.append(plan)
                    break

        return {"current": current_tier, "upgrades": upgrade_plans}

    # ============================================================
    # USER MANAGEMENT
    # ============================================================

    def _get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        try:
            user_data = self.db.get("users", user_id)
            if user_data:
                return User(**user_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def _update_user(self, user_id: str, data: Dict[str, Any]) -> bool:
        """Update user in database."""
        try:
            data["updated_at"] = datetime.utcnow().isoformat()
            self.db.update("users", user_id, data)
            return True
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            return False

    # ============================================================
    # CREDIT MANAGEMENT
    # ============================================================

    def get_user_credits(self, user_id: str) -> Dict[str, Any]:
        """Get user's current credit balance and limits."""
        user = self._get_user(user_id)
        if not user:
            return {"error": "User not found"}

        monthly_limit = self.MONTHLY_CREDITS.get(user.tier.value, 3)

        return {
            "credits_remaining": user.credits_remaining or 0,
            "monthly_limit": monthly_limit,
            "tier": user.tier.value,
        }

    def add_credits(self, user_id: str, amount: int, reason: str) -> bool:
        """Add credits to a user."""
        user = self._get_user(user_id)
        if not user:
            return False

        new_balance = (user.credits_remaining or 0) + amount

        return self._update_user(user_id, {"credits_remaining": new_balance})

    def deduct_credits(self, user_id: str, amount: int, reason: str) -> bool:
        """Deduct credits from a user."""
        user = self._get_user(user_id)
        if not user:
            return False

        current = user.credits_remaining or 0
        if current < amount:
            return False

        return self._update_user(user_id, {"credits_remaining": current - amount})

    # ============================================================
    # TIER UPGRADE (No Extra Credits)
    # ============================================================

    def process_tier_upgrade(self, user_id: str, new_tier: str) -> Dict[str, Any]:
        """
        Process tier upgrade - RESET credits to new tier's full limit.
        Old credits disappear, user gets fresh credits for the new tier.
        """
        user = self._get_user(user_id)
        if not user:
            raise ValidationError("User not found")

        old_tier = user.tier.value.lower()
        old_credits = user.credits_remaining or 0
        new_tier_lower = new_tier.lower()

        # Validate tier
        if new_tier_lower not in self.MONTHLY_CREDITS:
            raise ValidationError(f"Invalid tier: {new_tier}")

        # Check if already on this tier
        if old_tier == new_tier_lower:
            return {
                "success": True,
                "message": f"Already on {new_tier} tier",
                "old_tier": old_tier,
                "new_tier": new_tier_lower,
                "credits_remaining": user.credits_remaining or 0,
                "new_monthly_limit": self.MONTHLY_CREDITS[new_tier_lower],
            }

        #  RESET CREDITS - Full new tier credits (old credits disappear!)
        new_monthly_limit = self.MONTHLY_CREDITS[new_tier_lower]
        new_credits = new_monthly_limit  # Fresh start!

        # Update user tier with new credits
        success = self._update_user(
            user_id,
            {
                "tier": new_tier_lower,
                "credits_remaining": new_credits,  # ← Full new tier credits
                "monthly_credit_limit": new_monthly_limit,
            },
        )

        if not success:
            raise SubscriptionError("Failed to update user tier")

        logger.info(f"✅ User {user_id} upgraded from {old_tier} to {new_tier_lower}")
        logger.info(f"   Old credits: {old_credits} (discarded)")
        logger.info(f"   New credits: {new_credits} (fresh)")
        logger.info(f"   New monthly limit: {new_monthly_limit}")

        return {
            "success": True,
            "old_tier": old_tier,
            "new_tier": new_tier_lower,
            "old_credits": old_credits,
            "new_credits": new_credits,
            "new_monthly_limit": new_monthly_limit,
            "message": f"Welcome to {new_tier}! You now have {new_credits} credits.",
        }

    # ============================================================
    # SUBSCRIPTION MANAGEMENT
    # ============================================================

    def create_customer(self, user: User, email: str) -> Dict[str, Any]:
        """Create a Stripe customer for a user."""
        if not self.stripe_enabled:
            raise ExternalServiceError("Stripe", "Stripe is not configured")

        try:
            customer = self.stripe.create_customer(
                email=email,
                name=getattr(user, "full_name", email),
                metadata={"user_id": user.id, "tier": user.tier.value},
            )

            # Update user with Stripe customer ID
            self._update_user(user.id, {"stripe_customer_id": customer["id"]})

            return customer
        except Exception as e:
            raise ExternalServiceError("Stripe", str(e))

    def create_checkout_session(
        self, user_id: str, email: str, tier: str, price: int, interval: str
    ) -> str:
        """
        Create a Stripe Checkout session.
        """
        if not self.stripe_enabled:
            # Mock mode - simulate upgrade
            logger.info(
                f"[MOCK] Creating checkout for {tier} ({interval}) - ${price/100}"
            )
            # Process mock upgrade
            self.process_tier_upgrade(user_id, tier)
            return f"/pricing?upgraded={tier}&success=true"

        try:
            # Create or get customer
            customer = self.stripe.get_or_create_customer(email, user_id)

            # Get price ID
            price_id = self._get_price_id_by_tier(tier, interval)

            # Create checkout session
            checkout_session = stripe.checkout.Session.create(
                customer=customer["id"],
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=os.getenv(
                    "CHECKOUT_SUCCESS_URL",
                    f"http://localhost:5000/pricing?upgraded={tier}&success=true",
                ),
                cancel_url=os.getenv(
                    "CHECKOUT_CANCEL_URL", "http://localhost:5000/pricing?canceled=true"
                ),
                metadata={"user_id": user_id, "tier": tier, "interval": interval},
            )

            return checkout_session.url

        except Exception as e:
            logger.error(f"Failed to create checkout session: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))

    def _get_price_id_by_tier(self, tier: str, interval: str) -> str:
        """Get Stripe price ID for a tier and interval."""
        # Map tier and interval to price IDs (from env variables)
        price_map = {
            ("starter", "monthly"): os.getenv("STRIPE_PRICE_STARTER_MONTHLY"),
            ("starter", "yearly"): os.getenv("STRIPE_PRICE_STARTER_YEARLY"),
            ("pro", "monthly"): os.getenv("STRIPE_PRICE_PRO_MONTHLY"),
            ("pro", "yearly"): os.getenv("STRIPE_PRICE_PRO_YEARLY"),
            ("plus", "monthly"): os.getenv("STRIPE_PRICE_PLUS_MONTHLY"),
            ("plus", "yearly"): os.getenv("STRIPE_PRICE_PLUS_YEARLY"),
        }

        price_id = price_map.get((tier, interval))
        if not price_id:
            # For mock mode, return a placeholder
            if not self.stripe_enabled:
                return f"price_{tier}_{interval}"
            raise ValidationError(f"Price not configured for {tier} ({interval})")

        return price_id

    # ============================================================
    # WEBHOOK HANDLING
    # ============================================================

    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """Handle Stripe webhook events."""
        if not self.stripe_enabled:
            logger.warning("Webhook received but Stripe is not configured")
            return {"status": "ignored", "reason": "stripe_not_configured"}

        try:
            event = self.stripe.construct_event(payload, signature)
            event_type = event["type"]
            event_data = event["data"]["object"]

            logger.info(f"Processing Stripe webhook: {event_type}")

            # Handle specific events
            if event_type == "customer.subscription.created":
                self._handle_subscription_created(event_data)
            elif event_type == "customer.subscription.updated":
                self._handle_subscription_updated(event_data)
            elif event_type == "customer.subscription.deleted":
                self._handle_subscription_deleted(event_data)
            elif event_type == "invoice.payment_succeeded":
                self._handle_payment_succeeded(event_data)
            elif event_type == "invoice.payment_failed":
                self._handle_payment_failed(event_data)

            return {"status": "success", "event": event_type}

        except Exception as e:
            logger.error(f"Error processing Stripe webhook: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))

    def _handle_subscription_created(self, data: Dict[str, Any]):
        """Handle subscription created event."""
        user_data = self.db.query_one("users", {"stripe_customer_id": data["customer"]})
        if user_data:
            self._update_user(
                user_data["id"],
                {
                    "stripe_subscription_id": data["id"],
                    "subscription_end_date": datetime.fromtimestamp(
                        data["current_period_end"]
                    ).isoformat(),
                },
            )

    def _handle_subscription_updated(self, data: Dict[str, Any]):
        """Handle subscription updated event."""
        sub = self.db.query_one("subscriptions", {"stripe_subscription_id": data["id"]})
        if sub:
            self.db.update(
                "subscriptions",
                sub["id"],
                {
                    "status": data["status"],
                    "current_period_end": datetime.fromtimestamp(
                        data["current_period_end"]
                    ).isoformat(),
                    "cancel_at_period_end": data["cancel_at_period_end"],
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

    def _handle_subscription_deleted(self, data: Dict[str, Any]):
        """Handle subscription deleted event."""
        sub = self.db.query_one("subscriptions", {"stripe_subscription_id": data["id"]})
        if sub:
            self.db.update(
                "subscriptions",
                sub["id"],
                {
                    "status": "cancelled",
                    "cancelled_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

            # Downgrade user to free
            self._update_user(
                sub["user_id"], {"tier": "free", "subscription_end_date": None}
            )

    def _handle_payment_succeeded(self, data: Dict[str, Any]):
        """Handle payment succeeded event."""
        payment_id = str(uuid4())
        self.db.save(
            "payments",
            payment_id,
            {
                "id": payment_id,
                "invoice_id": data["id"],
                "customer_id": data["customer"],
                "amount_paid": data["amount_paid"] / 100,
                "currency": data["currency"],
                "status": "succeeded",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

    def _handle_payment_failed(self, data: Dict[str, Any]):
        """Handle payment failed event."""
        payment_id = str(uuid4())
        self.db.save(
            "payments",
            payment_id,
            {
                "id": payment_id,
                "invoice_id": data["id"],
                "customer_id": data["customer"],
                "amount_due": data["amount_due"] / 100,
                "currency": data["currency"],
                "status": "failed",
                "failure_reason": data.get("last_payment_error", {}).get(
                    "message", "Unknown"
                ),
                "created_at": datetime.utcnow().isoformat(),
            },
        )

    # ============================================================
    # INVOICE & PAYMENT METHODS
    # ============================================================

    def get_invoices(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's invoices."""
        user = self._get_user(user_id)
        if not user or not getattr(user, "stripe_customer_id", None):
            return []

        if not self.stripe_enabled:
            return []

        try:
            invoices = self.stripe.get_invoices(
                customer=user.stripe_customer_id, limit=limit
            )
            return invoices.get("data", [])
        except Exception as e:
            logger.error(f"Error getting invoices: {e}")
            return []

    def get_payment_methods(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's payment methods."""
        user = self._get_user(user_id)
        if not user or not getattr(user, "stripe_customer_id", None):
            return []

        if not self.stripe_enabled:
            return []

        try:
            methods = self.stripe.get_payment_methods(
                customer=user.stripe_customer_id, type="card"
            )
            return methods.get("data", [])
        except Exception as e:
            logger.error(f"Error getting payment methods: {e}")
            return []
