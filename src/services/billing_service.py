"""
Billing and subscription service.
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
    """Billing and subscription management service."""

    def __init__(self):
        self.stripe = StripeProvider()
        self.db = None  # Temporarily disabled for development

        # Check if Stripe is configured
        stripe_key = os.getenv("STRIPE_SECRET_KEY")
        self.stripe_enabled = bool(stripe_key and stripe_key.startswith("sk_"))

        if not self.stripe_enabled:
            print("⚠️  Stripe not configured - using mock mode")
            # Initialize mock data for development
            self._mock_subscriptions = {}
            self._mock_customers = {}

    def create_customer(self, user: User, email: str) -> Dict[str, Any]:
        """Create a Stripe customer for a user."""
        if not self.stripe_enabled:
            raise ExternalServiceError("Stripe", "Stripe is not configured")

        try:
            customer = self.stripe.create_customer(
                email=email,
                name=user.full_name,
                metadata={"user_id": user.id, "tier": user.tier.value},
            )

            # Update user with Stripe customer ID
            user.stripe_customer_id = customer["id"]
            self.db.update(
                "users",
                user.id,
                {
                    "stripe_customer_id": customer["id"],
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

            return customer
        except Exception as e:
            raise ExternalServiceError("Stripe", str(e))

    def create_subscription(
        self,
        user: User,
        tier: Tier,
        billing_cycle: BillingCycle = BillingCycle.MONTHLY,
        trial_days: int = TRIAL_PERIOD,
        coupon: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a subscription for a user."""
        if not self.stripe_enabled:
            raise ExternalServiceError("Stripe", "Stripe is not configured")

        # Get price ID for the tier
        price_id = self._get_price_id(tier, billing_cycle)

        # Create subscription
        try:
            subscription_data = {
                "customer": user.stripe_customer_id,
                "items": [{"price": price_id}],
                "payment_behavior": "default_incomplete",
                "expand": ["latest_invoice.payment_intent"],
                "metadata": {
                    "user_id": user.id,
                    "tier": tier.value,
                    "billing_cycle": billing_cycle.value,
                },
            }

            if trial_days > 0 and user.tier == Tier.FREE:
                subscription_data["trial_period_days"] = trial_days

            if coupon:
                subscription_data["coupon"] = coupon

            subscription = self.stripe.create_subscription(**subscription_data)

            # Save subscription to database
            subscription_id = str(uuid4())
            subscription_entity = Subscription(
                id=subscription_id,
                user_id=user.id,
                tier=tier.value,
                stripe_subscription_id=subscription["id"],
                stripe_customer_id=user.stripe_customer_id,
                stripe_price_id=price_id,
                current_period_start=datetime.fromtimestamp(
                    subscription["current_period_start"]
                ),
                current_period_end=datetime.fromtimestamp(
                    subscription["current_period_end"]
                ),
                billing_cycle=billing_cycle,
                amount=self._calculate_amount(tier, billing_cycle),
                features=self._get_tier_features(tier),
                is_in_trial="trial_end" in subscription
                and subscription["trial_end"] is not None,
            )

            self.db.save(
                "subscriptions", subscription_id, subscription_entity.to_dict()
            )

            # Update user tier
            user.tier = tier
            user.stripe_subscription_id = subscription["id"]
            user.subscription_end_date = subscription_entity.current_period_end

            self.db.update(
                "users",
                user.id,
                {
                    "tier": tier.value,
                    "stripe_subscription_id": subscription["id"],
                    "subscription_end_date": subscription_entity.current_period_end.isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

            return {
                "subscription": subscription,
                "client_secret": (
                    subscription["latest_invoice"]["payment_intent"]["client_secret"]
                    if subscription["latest_invoice"]
                    and subscription["latest_invoice"]["payment_intent"]
                    else None
                ),
            }
        except Exception as e:
            raise ExternalServiceError("Stripe", str(e))

    def cancel_subscription(
        self, user: User, cancel_at_period_end: bool = True
    ) -> bool:
        """Cancel a subscription."""
        if not user.stripe_subscription_id:
            raise ValidationError("User does not have an active subscription")

        try:
            subscription = self.stripe.cancel_subscription(
                user.stripe_subscription_id, cancel_at_period_end=cancel_at_period_end
            )

            # Update subscription in database
            subscription_data = self.db.query_one(
                "subscriptions", {"stripe_subscription_id": user.stripe_subscription_id}
            )

            if subscription_data:
                subscription_entity = Subscription(**subscription_data)
                subscription_entity.cancel_at_period_end = cancel_at_period_end
                subscription_entity.updated_at = datetime.utcnow()

                if not cancel_at_period_end:
                    subscription_entity.status = SubscriptionStatus.CANCELLED
                    subscription_entity.cancelled_at = datetime.utcnow()

                    # Downgrade user to free tier
                    user.tier = Tier.FREE
                    user.subscription_end_date = None
                    self.db.update(
                        "users",
                        user.id,
                        {
                            "tier": Tier.FREE.value,
                            "subscription_end_date": None,
                            "updated_at": datetime.utcnow().isoformat(),
                        },
                    )

                self.db.update(
                    "subscriptions",
                    subscription_entity.id,
                    subscription_entity.to_dict(),
                )

            return True
        except Exception as e:
            raise ExternalServiceError("Stripe", str(e))

    def upgrade_subscription(self, user: User, new_tier: Tier) -> Dict[str, Any]:
        """Upgrade a user's subscription tier."""
        if not user.stripe_subscription_id:
            raise ValidationError("User does not have an active subscription")

        # Get current subscription
        subscription_data = self.db.query_one(
            "subscriptions", {"stripe_subscription_id": user.stripe_subscription_id}
        )

        if not subscription_data:
            raise ValidationError("Subscription not found")

        subscription_entity = Subscription(**subscription_data)

        # Get price ID for new tier
        price_id = self._get_price_id(new_tier, subscription_entity.billing_cycle)

        try:
            # Update subscription in Stripe
            subscription = self.stripe.update_subscription(
                user.stripe_subscription_id,
                items=[{"id": subscription_entity.stripe_price_id, "price": price_id}],
                proration_behavior="create_prorations",
                metadata={
                    "upgraded_from": subscription_entity.tier,
                    "upgraded_to": new_tier.value,
                    "user_id": user.id,
                },
            )

            # Update subscription in database
            subscription_entity.tier = new_tier.value
            subscription_entity.stripe_price_id = price_id
            subscription_entity.amount = self._calculate_amount(
                new_tier, subscription_entity.billing_cycle
            )
            subscription_entity.features = self._get_tier_features(new_tier)
            subscription_entity.updated_at = datetime.utcnow()

            self.db.update(
                "subscriptions", subscription_entity.id, subscription_entity.to_dict()
            )

            # Update user tier
            user.tier = new_tier
            self.db.update(
                "users",
                user.id,
                {"tier": new_tier.value, "updated_at": datetime.utcnow().isoformat()},
            )

            return {
                "subscription": subscription,
                "proration_amount": subscription.get("pending_update", {}).get(
                    "proration_amount", 0
                ),
            }
        except Exception as e:
            raise ExternalServiceError("Stripe", str(e))

    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """Handle Stripe webhook events."""
        if not self.stripe_enabled:
            raise ExternalServiceError("Stripe", "Stripe is not configured")

        try:
            event = self.stripe.construct_event(payload, signature)
            event_type = event["type"]
            event_data = event["data"]["object"]

            logger.info(f"Processing Stripe webhook: {event_type}")

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
            elif event_type == "customer.subscription.trial_will_end":
                self._handle_trial_will_end(event_data)

            return {"status": "success", "event": event_type}
        except Exception as e:
            logger.error(f"Error processing Stripe webhook: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))

    def _handle_subscription_created(self, subscription_data: Dict[str, Any]):
        """Handle subscription created event."""
        # Find user by Stripe customer ID
        user_data = self.db.query_one(
            "users", {"stripe_customer_id": subscription_data["customer"]}
        )

        if user_data:
            user = User(**user_data)

            # Update user subscription info
            self.db.update(
                "users",
                user.id,
                {
                    "stripe_subscription_id": subscription_data["id"],
                    "subscription_end_date": datetime.fromtimestamp(
                        subscription_data["current_period_end"]
                    ).isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

    def _handle_subscription_updated(self, subscription_data: Dict[str, Any]):
        """Handle subscription updated event."""
        subscription = self.db.query_one(
            "subscriptions", {"stripe_subscription_id": subscription_data["id"]}
        )

        if subscription:
            subscription_entity = Subscription(**subscription)
            subscription_entity.status = SubscriptionStatus(subscription_data["status"])
            subscription_entity.current_period_end = datetime.fromtimestamp(
                subscription_data["current_period_end"]
            )
            subscription_entity.cancel_at_period_end = subscription_data[
                "cancel_at_period_end"
            ]
            subscription_entity.updated_at = datetime.utcnow()

            self.db.update(
                "subscriptions", subscription_entity.id, subscription_entity.to_dict()
            )

    def _handle_subscription_deleted(self, subscription_data: Dict[str, Any]):
        """Handle subscription deleted event."""
        subscription = self.db.query_one(
            "subscriptions", {"stripe_subscription_id": subscription_data["id"]}
        )

        if subscription:
            subscription_entity = Subscription(**subscription)
            subscription_entity.status = SubscriptionStatus.CANCELLED
            subscription_entity.cancelled_at = datetime.utcnow()
            subscription_entity.updated_at = datetime.utcnow()

            self.db.update(
                "subscriptions", subscription_entity.id, subscription_entity.to_dict()
            )

            # Downgrade user to free tier
            user_data = self.db.get("users", subscription_entity.user_id)
            if user_data:
                user = User(**user_data)
                user.tier = Tier.FREE
                user.subscription_end_date = None

                self.db.update(
                    "users",
                    user.id,
                    {
                        "tier": Tier.FREE.value,
                        "subscription_end_date": None,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                )

    def _handle_payment_succeeded(self, invoice_data: Dict[str, Any]):
        """Handle payment succeeded event."""
        # Record successful payment
        payment_id = str(uuid4())
        payment_data = {
            "id": payment_id,
            "invoice_id": invoice_data["id"],
            "customer_id": invoice_data["customer"],
            "amount_paid": invoice_data["amount_paid"] / 100,  # Convert from cents
            "currency": invoice_data["currency"],
            "status": "succeeded",
            "created_at": datetime.utcnow().isoformat(),
        }

        self.db.save("payments", payment_id, payment_data)

        # Update subscription next payment date
        if invoice_data.get("subscription"):
            subscription = self.db.query_one(
                "subscriptions",
                {"stripe_subscription_id": invoice_data["subscription"]},
            )

            if subscription:
                subscription_entity = Subscription(**subscription)
                subscription_entity.last_payment_date = datetime.utcnow()
                subscription_entity.next_payment_date = (
                    subscription_entity.current_period_end
                )
                subscription_entity.updated_at = datetime.utcnow()

                self.db.update(
                    "subscriptions",
                    subscription_entity.id,
                    subscription_entity.to_dict(),
                )

    def _handle_payment_failed(self, invoice_data: Dict[str, Any]):
        """Handle payment failed event."""
        # Record failed payment
        payment_id = str(uuid4())
        payment_data = {
            "id": payment_id,
            "invoice_id": invoice_data["id"],
            "customer_id": invoice_data["customer"],
            "amount_due": invoice_data["amount_due"] / 100,  # Convert from cents
            "currency": invoice_data["currency"],
            "status": "failed",
            "failure_reason": invoice_data.get("last_payment_error", {}).get(
                "message", "Unknown"
            ),
            "created_at": datetime.utcnow().isoformat(),
        }

        self.db.save("payments", payment_id, payment_data)

        # Update subscription status to past due
        if invoice_data.get("subscription"):
            subscription = self.db.query_one(
                "subscriptions",
                {"stripe_subscription_id": invoice_data["subscription"]},
            )

            if subscription:
                subscription_entity = Subscription(**subscription)
                subscription_entity.status = SubscriptionStatus.PAST_DUE
                subscription_entity.updated_at = datetime.utcnow()

                self.db.update(
                    "subscriptions",
                    subscription_entity.id,
                    subscription_entity.to_dict(),
                )

    def _handle_trial_will_end(self, subscription_data: Dict[str, Any]):
        """Handle trial will end event."""
        # Send notification to user about trial ending
        user_data = self.db.query_one(
            "users", {"stripe_customer_id": subscription_data["customer"]}
        )

        if user_data:
            user = User(**user_data)

            # Send email notification
            from services.email_service import EmailService

            email_service = EmailService()

            email_service.send_trial_ending_notification(
                user.email,
                user.full_name or user.email,
                datetime.fromtimestamp(subscription_data["trial_end"]),
            )

    def _get_price_id(self, tier: Tier, billing_cycle: BillingCycle) -> str:
        """Get Stripe price ID for a tier and billing cycle."""
        # In a real implementation, these would be configured in Stripe
        price_ids = {
            (Tier.STARTER, BillingCycle.MONTHLY): "price_starter_monthly",
            (Tier.STARTER, BillingCycle.YEARLY): "price_starter_yearly",
            (Tier.PRO, BillingCycle.MONTHLY): "price_pro_monthly",
            (Tier.PRO, BillingCycle.YEARLY): "price_pro_yearly",
            (Tier.PLUS, BillingCycle.MONTHLY): "price_plus_monthly",
            (Tier.PLUS, BillingCycle.YEARLY): "price_plus_yearly",
        }

        price_id = price_ids.get((tier, billing_cycle))
        if not price_id:
            raise ValidationError(
                f"Price not configured for {tier.value} {billing_cycle.value}"
            )

        return price_id

    def _calculate_amount(self, tier: Tier, billing_cycle: BillingCycle) -> float:
        """Calculate subscription amount."""
        monthly_price = PRICE_TIERS.get(tier.value, 0)

        if billing_cycle == BillingCycle.YEARLY:
            yearly_price = monthly_price * 12 * (1 - YEARLY_DISCOUNT / 100)
            return round(yearly_price, 2)

        return monthly_price

    def _get_tier_features(self, tier: Tier) -> Dict[str, Any]:
        """Get features for a tier."""
        from services.tier_service import TierService

        tier_service = TierService()
        tier_spec = tier_service.get_tier_spec(tier)

        return {
            "videos_per_month": tier_spec.videos_per_month,
            "max_video_length": tier_spec.max_video_length,
            "max_quality": tier_spec.max_quality,
            "ai_thumbnails_count": tier_spec.ai_thumbnails_count,
            "video_styles_available": tier_spec.video_styles_available,
            "retention_days": tier_spec.retention_days,
            "priority": tier_spec.priority,
        }

    def get_invoice_history(self, user: User, limit: int = 10) -> List[Dict[str, Any]]:
        """Get invoice history for a user."""
        if not user.stripe_customer_id:
            return []

        try:
            invoices = self.stripe.get_invoices(
                customer=user.stripe_customer_id, limit=limit
            )

            return [
                {
                    "id": inv["id"],
                    "number": inv["number"],
                    "amount_due": inv["amount_due"] / 100,
                    "amount_paid": inv["amount_paid"] / 100,
                    "status": inv["status"],
                    "created": datetime.fromtimestamp(inv["created"]).isoformat(),
                    "period_start": datetime.fromtimestamp(
                        inv["period_start"]
                    ).isoformat(),
                    "period_end": datetime.fromtimestamp(inv["period_end"]).isoformat(),
                    "pdf_url": inv.get("invoice_pdf"),
                }
                for inv in invoices.get("data", [])
            ]
        except Exception as e:
            logger.error(f"Error getting invoice history: {str(e)}")
            return []

    def create_payment_method(self, user: User, payment_method_id: str) -> bool:
        """Attach a payment method to a customer."""
        if not self.stripe_enabled:
            raise ExternalServiceError("Stripe", "Stripe is not configured")

        try:
            self.stripe.attach_payment_method(
                payment_method_id, user.stripe_customer_id
            )

            # Set as default payment method
            self.stripe.update_customer(
                user.stripe_customer_id,
                invoice_settings={"default_payment_method": payment_method_id},
            )

            return True
        except Exception as e:
            raise ExternalServiceError("Stripe", str(e))

    def get_payment_methods(self, user: User) -> List[Dict[str, Any]]:
        """Get payment methods for a customer."""
        if not user.stripe_customer_id:
            return []

        try:
            payment_methods = self.stripe.get_payment_methods(
                customer=user.stripe_customer_id, type="card"
            )

            return [
                {
                    "id": pm["id"],
                    "type": pm["type"],
                    "card": {
                        "brand": pm["card"]["brand"],
                        "last4": pm["card"]["last4"],
                        "exp_month": pm["card"]["exp_month"],
                        "exp_year": pm["card"]["exp_year"],
                    },
                    "is_default": pm.get("metadata", {}).get("is_default", False),
                }
                for pm in payment_methods.get("data", [])
            ]
        except Exception as e:
            logger.error(f"Error getting payment methods: {str(e)}")
            return []
