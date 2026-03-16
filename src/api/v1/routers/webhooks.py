"""
Webhook endpoints for external service callbacks.
"""

from flask import Blueprint, request, jsonify, current_app
import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.middleware.auth import admin_required
from core.exceptions import ValidationError
from services.billing_service import BillingService
from services.notification_service import NotificationService
from providers.stripe_provider import StripeProvider

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

billing_service = BillingService()
notification_service = NotificationService()
stripe_provider = StripeProvider()


@webhook_bp.route("/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        # Verify webhook signature
        event = stripe_provider.construct_event(
            payload=payload,
            sig_header=sig_header,
            webhook_secret=current_app.config.get("STRIPE_WEBHOOK_SECRET"),
        )

        # Handle event
        event_type = event["type"]
        event_data = event["data"]["object"]

        current_app.logger.info(f"Processing Stripe webhook: {event_type}")

        if event_type == "checkout.session.completed":
            handle_checkout_session_completed(event_data)
        elif event_type == "customer.subscription.created":
            handle_subscription_created(event_data)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(event_data)
        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(event_data)
        elif event_type == "invoice.payment_succeeded":
            handle_invoice_payment_succeeded(event_data)
        elif event_type == "invoice.payment_failed":
            handle_invoice_payment_failed(event_data)
        elif event_type == "payment_intent.succeeded":
            handle_payment_intent_succeeded(event_data)
        elif event_type == "payment_intent.payment_failed":
            handle_payment_intent_failed(event_data)
        elif event_type == "charge.refunded":
            handle_charge_refunded(event_data)
        else:
            current_app.logger.debug(f"Unhandled Stripe event type: {event_type}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        current_app.logger.error(f"Stripe webhook error: {e}")
        return jsonify({"error": str(e)}), 400


def handle_checkout_session_completed(session):
    """Handle checkout session completion."""
    try:
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        metadata = session.get("metadata", {})

        user_id = metadata.get("user_id")
        tier = metadata.get("tier", "starter")

        if user_id and subscription_id:
            # Update user subscription
            billing_service.update_user_subscription(
                user_id=user_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                tier=tier,
            )

            # Send confirmation email
            notification_service.send_subscription_confirmation(
                user_id=user_id, tier=tier
            )

            current_app.logger.info(f"Updated subscription for user {user_id}")

    except Exception as e:
        current_app.logger.error(f"Error handling checkout session: {e}")


def handle_subscription_created(subscription):
    """Handle subscription creation."""
    try:
        customer_id = subscription.get("customer")
        subscription_id = subscription.get("id")
        status = subscription.get("status")

        # Find user by customer ID
        from services.user_service import UserService

        user_service = UserService()
        user = user_service.get_user_by_stripe_customer_id(customer_id)

        if user:
            # Update subscription status
            billing_service.update_subscription_status(
                subscription_id=subscription_id,
                status=status,
                current_period_end=subscription.get("current_period_end"),
            )

            current_app.logger.info(f"Subscription created: {subscription_id}")

    except Exception as e:
        current_app.logger.error(f"Error handling subscription creation: {e}")


def handle_subscription_updated(subscription):
    """Handle subscription updates."""
    try:
        subscription_id = subscription.get("id")
        status = subscription.get("status")
        cancel_at_period_end = subscription.get("cancel_at_period_end", False)
        current_period_end = subscription.get("current_period_end")

        # Update subscription in database
        billing_service.update_subscription(
            subscription_id=subscription_id,
            status=status,
            cancel_at_period_end=cancel_at_period_end,
            current_period_end=current_period_end,
        )

        # If subscription was canceled or expired, downgrade user
        if status in ["canceled", "unpaid", "past_due"]:
            from services.user_service import UserService

            user_service = UserService()

            # Find user by subscription ID
            user = user_service.get_user_by_stripe_subscription_id(subscription_id)
            if user:
                # Downgrade to free tier
                user_service.update_user_tier(user.id, "free")

                # Send notification
                notification_service.send_subscription_canceled(user.id)

                current_app.logger.info(f"Downgraded user {user.id} to free tier")

    except Exception as e:
        current_app.logger.error(f"Error handling subscription update: {e}")


def handle_subscription_deleted(subscription):
    """Handle subscription deletion."""
    try:
        subscription_id = subscription.get("id")

        # Mark subscription as deleted in database
        billing_service.delete_subscription(subscription_id)

        current_app.logger.info(f"Subscription deleted: {subscription_id}")

    except Exception as e:
        current_app.logger.error(f"Error handling subscription deletion: {e}")


def handle_invoice_payment_succeeded(invoice):
    """Handle successful invoice payment."""
    try:
        subscription_id = invoice.get("subscription")
        amount_paid = invoice.get("amount_paid", 0) / 100  # Convert from cents
        currency = invoice.get("currency", "usd")

        # Record payment
        billing_service.record_payment(
            subscription_id=subscription_id,
            amount=amount_paid,
            currency=currency,
            invoice_id=invoice.get("id"),
        )

        # Send receipt
        from services.user_service import UserService

        user_service = UserService()

        user = user_service.get_user_by_stripe_subscription_id(subscription_id)
        if user:
            notification_service.send_payment_receipt(
                user_id=user.id, amount=amount_paid, currency=currency
            )

        current_app.logger.info(f"Payment succeeded for subscription {subscription_id}")

    except Exception as e:
        current_app.logger.error(f"Error handling invoice payment: {e}")


def handle_invoice_payment_failed(invoice):
    """Handle failed invoice payment."""
    try:
        subscription_id = invoice.get("subscription")

        # Send payment failure notification
        from services.user_service import UserService

        user_service = UserService()

        user = user_service.get_user_by_stripe_subscription_id(subscription_id)
        if user:
            notification_service.send_payment_failed(
                user_id=user.id, subscription_id=subscription_id
            )

        current_app.logger.warning(f"Payment failed for subscription {subscription_id}")

    except Exception as e:
        current_app.logger.error(f"Error handling payment failure: {e}")


def handle_payment_intent_succeeded(payment_intent):
    """Handle successful payment intent."""
    try:
        # This could be for one-time payments (credits, upgrades, etc.)
        amount = payment_intent.get("amount", 0) / 100
        currency = payment_intent.get("currency", "usd")
        metadata = payment_intent.get("metadata", {})

        user_id = metadata.get("user_id")
        payment_type = metadata.get("type", "unknown")

        if user_id:
            # Handle based on payment type
            if payment_type == "credits":
                credits_amount = metadata.get("credits", 0)
                billing_service.add_credits(user_id, credits_amount)

                notification_service.send_credits_purchased(
                    user_id=user_id, credits=credits_amount, amount=amount
                )

            elif payment_type == "upgrade":
                tier = metadata.get("tier")
                if tier:
                    from services.user_service import UserService

                    user_service = UserService()
                    user_service.update_user_tier(user_id, tier)

                    notification_service.send_tier_upgraded(
                        user_id=user_id, tier=tier, amount=amount
                    )

        current_app.logger.info(f"Payment intent succeeded: {payment_intent.get('id')}")

    except Exception as e:
        current_app.logger.error(f"Error handling payment intent: {e}")


def handle_payment_intent_failed(payment_intent):
    """Handle failed payment intent."""
    try:
        metadata = payment_intent.get("metadata", {})
        user_id = metadata.get("user_id")
        error_message = payment_intent.get("last_payment_error", {}).get(
            "message", "Unknown error"
        )

        if user_id:
            notification_service.send_payment_failed(
                user_id=user_id, error_message=error_message
            )

        current_app.logger.warning(f"Payment intent failed: {payment_intent.get('id')}")

    except Exception as e:
        current_app.logger.error(f"Error handling payment intent failure: {e}")


def handle_charge_refunded(charge):
    """Handle charge refund."""
    try:
        amount_refunded = charge.get("amount_refunded", 0) / 100
        refund_reason = (
            charge.get("refunds", {})
            .get("data", [{}])[0]
            .get("reason", "requested_by_customer")
        )

        # Update subscription or handle refund logic
        # This would typically involve updating billing records

        current_app.logger.info(f"Charge refunded: {charge.get('id')}")

    except Exception as e:
        current_app.logger.error(f"Error handling charge refund: {e}")


@webhook_bp.route("/sendgrid", methods=["POST"])
def sendgrid_webhook():
    """Handle SendGrid email webhook events."""
    try:
        events = request.get_json()

        for event in events:
            event_type = event.get("event")
            email = event.get("email")
            timestamp = event.get("timestamp")

            current_app.logger.debug(f"SendGrid event: {event_type} for {email}")

            # Track email events for analytics
            # You could store these in a database for analytics

        return jsonify({"status": "success"}), 200

    except Exception as e:
        current_app.logger.error(f"SendGrid webhook error: {e}")
        return jsonify({"error": str(e)}), 400


@webhook_bp.route("/stability", methods=["POST"])
@admin_required
def stability_webhook():
    """Handle Stability AI webhook events."""
    try:
        data = request.get_json()
        event_type = data.get("event")

        if event_type == "image.generated":
            # Handle generated image
            image_id = data.get("image_id")
            status = data.get("status")
            cost = data.get("cost", 0)

            # Update image generation record
            # This would typically update a database record

            current_app.logger.info(f"Image generated: {image_id}, cost: ${cost}")

        elif event_type == "generation.failed":
            # Handle failed generation
            error = data.get("error", "Unknown error")
            current_app.logger.error(f"Image generation failed: {error}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        current_app.logger.error(f"Stability webhook error: {e}")
        return jsonify({"error": str(e)}), 400


@webhook_bp.route("/monitoring", methods=["POST"])
@admin_required
def monitoring_webhook():
    """Handle monitoring service webhooks (e.g., UptimeRobot, Sentry)."""
    try:
        data = request.get_json()
        service = request.headers.get("X-Service", "unknown")

        if service == "uptimerobot":
            # Handle uptime monitoring alerts
            alert_type = data.get("alertType")
            monitor_name = data.get("monitorFriendlyName")

            if alert_type == "1":  # Down
                current_app.logger.error(f"Monitor down: {monitor_name}")
                notification_service.send_system_alert(
                    f"Monitor {monitor_name} is DOWN",
                    "UptimeRobot",
                    severity="critical",
                )
            elif alert_type == "2":  # Up
                current_app.logger.info(f"Monitor up: {monitor_name}")

        elif service == "sentry":
            # Handle error tracking alerts
            event_id = data.get("event", {}).get("event_id")
            message = data.get("event", {}).get("message", "Unknown error")
            level = data.get("event", {}).get("level", "error")

            current_app.logger.error(f"Sentry alert: {message} (level: {level})")

            # Send alert to admin
            if level in ["error", "fatal"]:
                notification_service.send_system_alert(
                    f"Sentry Alert: {message}",
                    "Sentry",
                    severity="error",
                    metadata={"event_id": event_id},
                )

        return jsonify({"status": "success"}), 200

    except Exception as e:
        current_app.logger.error(f"Monitoring webhook error: {e}")
        return jsonify({"error": str(e)}), 400


@webhook_bp.route("/custom", methods=["POST"])
@jwt_required
def custom_webhook():
    """Handle custom webhooks for user-defined integrations."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate webhook configuration
        webhook_url = data.get("url")
        event_types = data.get("events", [])
        secret = data.get("secret")

        if not webhook_url:
            raise ValidationError("Webhook URL is required")

        # Register webhook for user
        # This would typically store in a database

        current_app.logger.info(f"Registered custom webhook for user {user_id}")

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Webhook registered successfully",
                    "webhook_id": "generated_id_here",  # Would be from database
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Custom webhook error: {e}")
        return jsonify({"error": str(e)}), 400


@webhook_bp.route("/test", methods=["POST"])
@admin_required
def test_webhook():
    """Test webhook endpoint for debugging."""
    try:
        data = request.get_json() or {}
        headers = dict(request.headers)

        # Remove sensitive headers
        sensitive_headers = ["Authorization", "X-Api-Key", "X-Secret"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "***REDACTED***"

        current_app.logger.info(f"Test webhook received:")
        current_app.logger.info(f"Headers: {headers}")
        current_app.logger.info(f"Body: {data}")

        return (
            jsonify(
                {
                    "status": "success",
                    "received": {
                        "headers": headers,
                        "body": data,
                        "method": request.method,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Test webhook error: {e}")
        return jsonify({"error": str(e)}), 400
