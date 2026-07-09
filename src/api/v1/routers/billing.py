"""
Billing and subscription router for API v1 - Production Ready
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from datetime import datetime
import os

from core.exceptions import ValidationError, UnauthorizedError
from api.dependencies import validate_request, track_analytics
from services.billing_service import BillingService
from services.user_service import UserService

router = Blueprint("billing", __name__)
logger = logging.getLogger(__name__)

billing_service = BillingService()
user_service = UserService()


# ============================================================
# PRICING & PLANS
# ============================================================

@router.route("/pricing", methods=["GET"])
def get_pricing():
    """Get all pricing plans."""
    try:
        plans = billing_service.get_pricing_plans()
        return jsonify({
            "plans": plans,
            "currency": "USD",
            "yearly_discount": 20
        }), 200
    except Exception as e:
        logger.error(f"Get pricing failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


@router.route("/plans", methods=["GET"])
@jwt_required()
def get_user_plans():
    """Get user's current plan and available upgrades."""
    user_id = get_jwt_identity()
    try:
        plans = billing_service.get_user_plans(user_id)
        return jsonify(plans), 200
    except Exception as e:
        logger.error(f"Get user plans failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# CHECKOUT & UPGRADE
# ============================================================

@router.route("/checkout", methods=["POST"])
@jwt_required()
@track_analytics("billing.checkout")
def create_checkout():
    """Create a checkout session for upgrading."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        tier = data.get("tier")
        price = data.get("price")
        interval = data.get("interval", "monthly")

        if not tier:
            return jsonify({"error": "Tier is required"}), 400

        # Get user
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Check if already on this tier
        if user.tier.value.lower() == tier.lower():
            return jsonify({
                "success": True,
                "checkout_url": f"/pricing?already={tier}&success=true",
                "message": f"You're already on the {tier} tier"
            }), 200

        #  For mock mode, process upgrade directly
        if not os.getenv("STRIPE_SECRET_KEY"):
            result = billing_service.process_tier_upgrade(user_id, tier)
            return jsonify({
                "success": True,
                "checkout_url": f"/pricing?upgraded={tier}&success=true",
                "message": result.get("message", f"Upgraded to {tier}"),
                "credits_remaining": result.get("credits_remaining", 0),
                "new_monthly_limit": result.get("new_monthly_limit", 0)
            }), 200

        # Stripe mode - create checkout session
        checkout_url = billing_service.create_checkout_session(
            user_id=user_id,
            email=user.email,
            tier=tier,
            price=price,
            interval=interval
        )

        return jsonify({
            "success": True,
            "checkout_url": checkout_url,
            "message": f"Checkout created for {tier} tier"
        }), 200

    except Exception as e:
        logger.error(f"Create checkout failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


@router.route("/upgrade", methods=["POST"])
@jwt_required()
@track_analytics("tier.upgrade")
def upgrade_tier():
    """Upgrade user tier directly (no payment)."""
    user_id = get_jwt_identity()

    try:
        data = request.json
        tier = data.get("tier")

        if not tier:
            return jsonify({"error": "Tier is required"}), 400

        result = billing_service.process_tier_upgrade(user_id, tier)

        return jsonify({
            "success": True,
            "message": result.get("message"),
            "old_tier": result.get("old_tier"),
            "new_tier": result.get("new_tier"),
            "credits_remaining": result.get("credits_remaining"),
            "new_monthly_limit": result.get("new_monthly_limit")
        }), 200

    except Exception as e:
        logger.error(f"Upgrade tier failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# CREDITS
# ============================================================

@router.route("/credits", methods=["GET"])
@jwt_required()
def get_credits():
    """Get user's credit balance."""
    user_id = get_jwt_identity()
    try:
        credits = billing_service.get_user_credits(user_id)
        return jsonify(credits), 200
    except Exception as e:
        logger.error(f"Get credits failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# SUBSCRIPTION MANAGEMENT
# ============================================================

@router.route("/subscription", methods=["GET"])
@jwt_required()
def get_subscription():
    """Get current subscription."""
    user_id = get_jwt_identity()
    try:
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        return jsonify({
            "has_subscription": user.tier.value != "free",
            "tier": user.tier.value,
            "credits_remaining": user.credits_remaining or 0,
            "monthly_limit": billing_service.MONTHLY_CREDITS.get(user.tier.value, 3)
        }), 200
    except Exception as e:
        logger.error(f"Get subscription failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


@router.route("/subscription/cancel", methods=["POST"])
@jwt_required()
@track_analytics("subscription.cancel")
def cancel_subscription():
    """Cancel subscription."""
    user_id = get_jwt_identity()

    try:
        # Downgrade to free
        result = billing_service.process_tier_upgrade(user_id, "free")
        return jsonify({
            "success": True,
            "message": "Subscription cancelled. Downgraded to Free tier.",
            "credits_remaining": result.get("credits_remaining", 0)
        }), 200
    except Exception as e:
        logger.error(f"Cancel subscription failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# WEBHOOKS
# ============================================================

@router.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    try:
        payload = request.data
        sig_header = request.headers.get("Stripe-Signature")

        if not sig_header:
            return jsonify({"error": "Missing signature header"}), 400

        result = billing_service.handle_webhook(payload, sig_header)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Stripe webhook failed: {str(e)}")
        return jsonify({"error": str(e)}), 400


# ============================================================
# ENTERPRISE
# ============================================================

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
            return jsonify({"error": "Email is required"}), 400

        from providers.firebase_provider import FirebaseProvider
        db = FirebaseProvider()

        contact = {
            "name": name,
            "email": email,
            "company": company,
            "message": message,
            "submitted_at": datetime.utcnow().isoformat(),
            "status": "pending"
        }

        db.save("enterprise_contacts", f"contact_{datetime.utcnow().timestamp()}", contact)

        return jsonify({
            "success": True,
            "message": "Contact request submitted successfully"
        }), 201

    except Exception as e:
        logger.error(f"Enterprise contact failed: {str(e)}")
        return jsonify({"error": str(e)}), 500