"""
Billing and subscription router for API v1.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from datetime import datetime

from core.exceptions import ValidationError, UnauthorizedError
from api.dependencies import validate_request, track_analytics, require_tier
from api.schemas.common import WebhookSchema
from services.billing_service import BillingService

# from services.subscription_service import SubscriptionService

router = Blueprint("billing", __name__)
logger = logging.getLogger(__name__)

billing_service = BillingService()
# subscription_service = SubscriptionService()


@router.route("/pricing", methods=["GET"])
def get_pricing():
    """Get pricing plans."""
    try:
        pricing = billing_service.get_pricing_plans()

        return (
            jsonify(
                {
                    "plans": pricing,
                    "currency": "USD",
                    "billing_cycle": "monthly",
                    "yearly_discount": 20,  # 20% discount for yearly billing
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get pricing failed: {str(e)}")
        raise


@router.route("/plans", methods=["GET"])
@jwt_required()
def get_user_plans():
    """Get user's subscription plans."""
    user_id = get_jwt_identity()

    try:
        plans = billing_service.get_user_plans(user_id)

        return (
            jsonify(
                {
                    "plans": plans,
                    "current_plan": plans.get("current"),
                    "available_upgrades": plans.get("upgrades", []),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get user plans failed: {str(e)}")
        raise


@router.route("/subscribe", methods=["POST"])
@jwt_required()
@track_analytics("subscription.create")
def create_subscription():
    """Create a new subscription."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        plan_id = data.get("plan_id")
        billing_cycle = data.get("billing_cycle", "monthly")
        payment_method_id = data.get("payment_method_id")

        if not plan_id:
            raise ValidationError("Plan ID is required", field="plan_id")

        subscription = billing_service.create_subscription(
            user_id=user_id,
            plan_id=plan_id,
            billing_cycle=billing_cycle,
            payment_method_id=payment_method_id,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "subscription": subscription,
                    "message": "Subscription created successfully",
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Create subscription failed: {str(e)}")
        raise


@router.route("/subscription", methods=["GET"])
@jwt_required()
def get_subscription():
    """Get current subscription."""
    user_id = get_jwt_identity()

    try:
        subscription = billing_service.get_subscription(user_id)

        if not subscription:
            return (
                jsonify(
                    {
                        "has_subscription": False,
                        "message": "No active subscription found",
                    }
                ),
                200,
            )

        return (
            jsonify(
                {
                    "has_subscription": True,
                    "subscription": subscription,
                    "next_billing_date": subscription.get("current_period_end"),
                    "status": subscription.get("status"),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get subscription failed: {str(e)}")
        raise


@router.route("/subscription", methods=["PUT"])
@jwt_required()
@track_analytics("subscription.update")
def update_subscription():
    """Update subscription."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        plan_id = data.get("plan_id")
        billing_cycle = data.get("billing_cycle")

        if not plan_id and not billing_cycle:
            raise ValidationError("Either plan_id or billing_cycle is required")

        subscription = billing_service.update_subscription(
            user_id=user_id, plan_id=plan_id, billing_cycle=billing_cycle
        )

        return (
            jsonify(
                {
                    "success": True,
                    "subscription": subscription,
                    "message": "Subscription updated successfully",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Update subscription failed: {str(e)}")
        raise


@router.route("/subscription/cancel", methods=["POST"])
@jwt_required()
@track_analytics("subscription.cancel")
def cancel_subscription():
    """Cancel subscription."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        cancel_at_period_end = data.get("cancel_at_period_end", True)

        subscription = billing_service.cancel_subscription(
            user_id=user_id, cancel_at_period_end=cancel_at_period_end
        )

        message = (
            "Subscription cancelled"
            if not cancel_at_period_end
            else "Subscription scheduled for cancellation at period end"
        )

        return (
            jsonify(
                {"success": True, "subscription": subscription, "message": message}
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Cancel subscription failed: {str(e)}")
        raise


@router.route("/subscription/reactivate", methods=["POST"])
@jwt_required()
@track_analytics("subscription.reactivate")
def reactivate_subscription():
    """Reactivate cancelled subscription."""
    user_id = get_jwt_identity()

    try:
        subscription = billing_service.reactivate_subscription(user_id)

        return (
            jsonify(
                {
                    "success": True,
                    "subscription": subscription,
                    "message": "Subscription reactivated successfully",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Reactivate subscription failed: {str(e)}")
        raise


@router.route("/invoices", methods=["GET"])
@jwt_required()
def get_invoices():
    """Get billing invoices."""
    user_id = get_jwt_identity()

    try:
        invoices = billing_service.get_invoices(user_id)

        return jsonify({"invoices": invoices, "total": len(invoices)}), 200

    except Exception as e:
        logger.error(f"Get invoices failed: {str(e)}")
        raise


@router.route("/invoices/<invoice_id>", methods=["GET"])
@jwt_required()
def get_invoice(invoice_id):
    """Get specific invoice."""
    user_id = get_jwt_identity()

    try:
        invoice = billing_service.get_invoice(user_id, invoice_id)

        if not invoice:
            raise ValidationError("Invoice not found", field="invoice_id")

        return jsonify({"invoice": invoice}), 200

    except Exception as e:
        logger.error(f"Get invoice failed: {str(e)}")
        raise


@router.route("/payment-methods", methods=["GET"])
@jwt_required()
def get_payment_methods():
    """Get payment methods."""
    user_id = get_jwt_identity()

    try:
        payment_methods = billing_service.get_payment_methods(user_id)

        return (
            jsonify(
                {
                    "payment_methods": payment_methods,
                    "default_payment_method": next(
                        (pm for pm in payment_methods if pm.get("is_default", False)),
                        None,
                    ),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get payment methods failed: {str(e)}")
        raise


@router.route("/payment-methods", methods=["POST"])
@jwt_required()
@track_analytics("payment_method.add")
def add_payment_method():
    """Add payment method."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        payment_method_id = data.get("payment_method_id")

        if not payment_method_id:
            raise ValidationError(
                "Payment method ID is required", field="payment_method_id"
            )

        payment_method = billing_service.add_payment_method(
            user_id=user_id, payment_method_id=payment_method_id
        )

        return (
            jsonify(
                {
                    "success": True,
                    "payment_method": payment_method,
                    "message": "Payment method added successfully",
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Add payment method failed: {str(e)}")
        raise


@router.route("/payment-methods/<payment_method_id>", methods=["DELETE"])
@jwt_required()
@track_analytics("payment_method.remove")
def remove_payment_method(payment_method_id):
    """Remove payment method."""
    user_id = get_jwt_identity()

    try:
        success = billing_service.remove_payment_method(
            user_id=user_id, payment_method_id=payment_method_id
        )

        if not success:
            raise ValidationError("Payment method not found", field="payment_method_id")

        return (
            jsonify(
                {"success": True, "message": "Payment method removed successfully"}
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Remove payment method failed: {str(e)}")
        raise


@router.route("/payment-methods/<payment_method_id>/default", methods=["POST"])
@jwt_required()
@track_analytics("payment_method.set_default")
def set_default_payment_method(payment_method_id):
    """Set default payment method."""
    user_id = get_jwt_identity()

    try:
        success = billing_service.set_default_payment_method(
            user_id=user_id, payment_method_id=payment_method_id
        )

        if not success:
            raise ValidationError("Payment method not found", field="payment_method_id")

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Default payment method updated successfully",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Set default payment method failed: {str(e)}")
        raise


@router.route("/coupon/validate", methods=["POST"])
def validate_coupon():
    """Validate coupon code."""
    try:
        data = request.json
        coupon_code = data.get("coupon_code")

        if not coupon_code:
            raise ValidationError("Coupon code is required", field="coupon_code")

        coupon = billing_service.validate_coupon(coupon_code)

        return (
            jsonify({"valid": True, "coupon": coupon, "message": "Coupon is valid"}),
            200,
        )

    except Exception as e:
        logger.error(f"Validate coupon failed: {str(e)}")
        raise


@router.route("/usage", methods=["GET"])
@jwt_required()
def get_usage():
    """Get usage information."""
    user_id = get_jwt_identity()

    try:
        usage = billing_service.get_usage(user_id)

        return (
            jsonify(
                {
                    "usage": usage,
                    "current_period": {
                        "start": usage.get("period_start"),
                        "end": usage.get("period_end"),
                    },
                    "limits": usage.get("limits", {}),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get usage failed: {str(e)}")
        raise


@router.route("/upgrade", methods=["POST"])
@jwt_required()
@require_tier("free")
@track_analytics("tier.upgrade")
def upgrade_tier():
    """Upgrade user tier."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        tier = data.get("tier")

        if not tier:
            raise ValidationError("Tier is required", field="tier")

        # Get current user
        from services.user_service import get_user_by_id

        user = get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        # Check if tier upgrade is valid
        from services.tier_service import TierService

        tier_service = TierService()

        if not tier_service.can_upgrade_to(user.tier, tier):
            raise ValidationError(
                f"Cannot upgrade from {user.tier.value} to {tier}", field="tier"
            )

        # Process upgrade
        upgrade_result = billing_service.process_upgrade(
            user_id=user_id, current_tier=user.tier.value, new_tier=tier
        )

        # Record tier upgrade metric
        from app.monitoring.metrics import record_tier_upgrade

        record_tier_upgrade(user.tier.value, tier)

        return (
            jsonify(
                {
                    "success": True,
                    "upgrade": upgrade_result,
                    "message": f"Successfully upgraded to {tier} tier",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Upgrade tier failed: {str(e)}")
        raise


@router.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    try:
        payload = request.data
        sig_header = request.headers.get("Stripe-Signature")

        event = billing_service.handle_stripe_webhook(payload, sig_header)

        if not event:
            return jsonify({"error": "Invalid webhook signature"}), 400

        # Process event based on type
        event_type = event.get("type")

        if event_type == "customer.subscription.updated":
            # Update subscription in database
            subscription_data = event["data"]["object"]
            billing_service.update_subscription_from_stripe(subscription_data)

        elif event_type == "invoice.payment_succeeded":
            # Record successful payment
            invoice_data = event["data"]["object"]
            billing_service.record_payment(invoice_data)

        elif event_type == "invoice.payment_failed":
            # Handle failed payment
            invoice_data = event["data"]["object"]
            billing_service.handle_failed_payment(invoice_data)

        elif event_type == "customer.subscription.deleted":
            # Handle subscription cancellation
            subscription_data = event["data"]["object"]
            billing_service.handle_subscription_cancellation(subscription_data)

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Stripe webhook failed: {str(e)}")
        return jsonify({"error": str(e)}), 400


@router.route("/enterprise/contact", methods=["POST"])
@track_analytics("enterprise.contact_request")
def enterprise_contact():
    """Submit enterprise contact request."""
    try:
        data = request.json
        name = data.get("name")
        email = data.get("email")
        company = data.get("company")
        message = data.get("message")

        if not email:
            raise ValidationError("Email is required", field="email")

        # Store contact request
        contact_request = {
            "name": name,
            "email": email,
            "company": company,
            "message": message,
            "submitted_at": datetime.utcnow().isoformat(),
            "status": "pending",
        }

        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()
        db.save(
            "enterprise_contacts",
            f"contact_{datetime.utcnow().timestamp()}",
            contact_request,
        )

        # Send notification
        from services.email_service import send_enterprise_contact_email

        send_enterprise_contact_email(email, name, company, message)

        return (
            jsonify(
                {"success": True, "message": "Contact request submitted successfully"}
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Enterprise contact failed: {str(e)}")
        raise
