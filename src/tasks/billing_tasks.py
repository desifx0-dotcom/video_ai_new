"""
Billing and subscription related tasks.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from .celery_app import celery_app as celery
from services.billing_service import BillingService
from services.user_service import UserService
from providers.firebase_provider import FirebaseProvider
from core.domain.entities.subscription import SubscriptionStatus

logger = logging.getLogger(__name__)


@celery.task
def process_subscription_renewals() -> Dict[str, Any]:
    """
    Process subscription renewals for active subscriptions.
    Runs daily to check for subscriptions that need renewal.
    """
    db = FirebaseProvider()
    billing_service = BillingService()

    try:
        # Get subscriptions that are ending in the next 7 days
        seven_days_from_now = datetime.utcnow() + timedelta(days=7)

        subscriptions = db.query(
            "subscriptions",
            filters={
                "status": SubscriptionStatus.ACTIVE.value,
                "cancel_at_period_end": False,
            },
        )

        renewals_processed = 0
        renewals_failed = 0
        upcoming_renewals = []

        for sub_data in subscriptions:
            subscription = dict(sub_data)

            # Check if renewal is due
            period_end = datetime.fromisoformat(subscription["current_period_end"])
            days_until_renewal = (period_end - datetime.utcnow()).days

            if 0 <= days_until_renewal <= 7:
                upcoming_renewals.append(
                    {
                        "subscription_id": subscription["id"],
                        "user_id": subscription["user_id"],
                        "tier": subscription["tier"],
                        "renewal_date": period_end.isoformat(),
                        "days_until_renewal": days_until_renewal,
                    }
                )

                # If renewal is due today or past due
                if days_until_renewal <= 0:
                    try:
                        # Get user
                        user_data = db.get("users", subscription["user_id"])
                        if not user_data:
                            logger.error(f"User not found: {subscription['user_id']}")
                            renewals_failed += 1
                            continue

                        # In a real implementation, Stripe would handle automatic renewals
                        # For now, just log and update the subscription
                        logger.info(
                            f"Processing renewal for subscription {subscription['id']}"
                        )

                        # Update subscription dates
                        new_period_end = period_end + timedelta(
                            days=30
                        )  # Monthly renewal
                        subscription["current_period_start"] = period_end.isoformat()
                        subscription["current_period_end"] = new_period_end.isoformat()
                        subscription["updated_at"] = datetime.utcnow().isoformat()

                        db.update("subscriptions", subscription["id"], subscription)

                        # Update user subscription end date
                        db.update(
                            "users",
                            subscription["user_id"],
                            {
                                "subscription_end_date": new_period_end.isoformat(),
                                "updated_at": datetime.utcnow().isoformat(),
                            },
                        )

                        renewals_processed += 1

                        # Send renewal confirmation email
                        from .email_tasks import send_email_async

                        send_email_async.delay(
                            template_name="payment_received",
                            to_email=user_data["email"],
                            subject="Subscription Renewal Successful",
                            context={
                                "user_name": user_data.get(
                                    "full_name", user_data["email"].split("@")[0]
                                ),
                                "amount": subscription["amount"],
                                "tier": subscription["tier"].capitalize(),
                                "next_billing_date": new_period_end.strftime(
                                    "%B %d, %Y"
                                ),
                                "billing_url": "https://app.videoaistudio.com/billing",
                            },
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to process renewal for subscription {subscription['id']}: {str(e)}"
                        )
                        renewals_failed += 1

        return {
            "status": "completed",
            "renewals_processed": renewals_processed,
            "renewals_failed": renewals_failed,
            "upcoming_renewals": upcoming_renewals,
            "total_subscriptions": len(subscriptions),
        }
    except Exception as e:
        logger.error(f"Error processing subscription renewals: {str(e)}")
        return {"status": "failed", "error": str(e)}


@celery.task
def send_payment_reminders() -> Dict[str, Any]:
    """
    Send payment reminder emails for upcoming or past due payments.
    Runs daily.
    """
    db = FirebaseProvider()

    try:
        # Get past due subscriptions
        past_due_subscriptions = db.query(
            "subscriptions", filters={"status": SubscriptionStatus.PAST_DUE.value}
        )

        # Get subscriptions ending in 3 days
        three_days_from_now = datetime.utcnow() + timedelta(days=3)
        upcoming_subscriptions = db.query(
            "subscriptions",
            filters={
                "status": SubscriptionStatus.ACTIVE.value,
                "cancel_at_period_end": False,
            },
        )

        upcoming_reminders = []
        for sub_data in upcoming_subscriptions:
            subscription = dict(sub_data)
            period_end = datetime.fromisoformat(subscription["current_period_end"])

            if 0 <= (period_end - datetime.utcnow()).days <= 3:
                upcoming_reminders.append(subscription)

        reminders_sent = 0
        reminders_failed = 0

        # Send reminders for past due subscriptions
        for subscription in past_due_subscriptions:
            try:
                user_data = db.get("users", subscription["user_id"])
                if not user_data:
                    continue

                from .email_tasks import send_payment_failed_email

                send_payment_failed_email.delay(
                    user_id=subscription["user_id"],
                    invoice_id=f"inv_{subscription['id']}",
                    amount=subscription["amount"],
                )

                reminders_sent += 1
            except Exception as e:
                logger.error(f"Failed to send past due reminder: {str(e)}")
                reminders_failed += 1

        # Send reminders for upcoming renewals
        for subscription in upcoming_reminders:
            try:
                user_data = db.get("users", subscription["user_id"])
                if not user_data:
                    continue

                period_end = datetime.fromisoformat(subscription["current_period_end"])
                days_until = (period_end - datetime.utcnow()).days

                from .email_tasks import send_email_async

                send_email_async.delay(
                    template_name="payment_reminder",
                    to_email=user_data["email"],
                    subject=f'Reminder: Subscription Renewal in {days_until} day{"s" if days_until != 1 else ""}',
                    context={
                        "user_name": user_data.get(
                            "full_name", user_data["email"].split("@")[0]
                        ),
                        "amount": subscription["amount"],
                        "tier": subscription["tier"].capitalize(),
                        "renewal_date": period_end.strftime("%B %d, %Y"),
                        "days_until": days_until,
                        "billing_url": "https://app.videoaistudio.com/billing",
                    },
                )

                reminders_sent += 1
            except Exception as e:
                logger.error(f"Failed to send upcoming renewal reminder: {str(e)}")
                reminders_failed += 1

        return {
            "status": "completed",
            "reminders_sent": reminders_sent,
            "reminders_failed": reminders_failed,
            "past_due_count": len(past_due_subscriptions),
            "upcoming_count": len(upcoming_reminders),
        }
    except Exception as e:
        logger.error(f"Error sending payment reminders: {str(e)}")
        return {"status": "failed", "error": str(e)}


@celery.task
def process_trial_expirations() -> Dict[str, Any]:
    """
    Process trial expirations.
    Runs daily to check for trials that have ended.
    """
    db = FirebaseProvider()

    try:
        # Get subscriptions in trial that are ending today or have ended
        today = datetime.utcnow().date()

        trial_subscriptions = db.query("subscriptions", filters={"is_in_trial": True})

        expired_trials = 0
        expiring_trials = []

        for sub_data in trial_subscriptions:
            subscription = dict(sub_data)
            period_end = datetime.fromisoformat(
                subscription["current_period_end"]
            ).date()

            if period_end < today:
                # Trial has ended, downgrade to free tier
                try:
                    # Update subscription
                    subscription["is_in_trial"] = False
                    subscription["status"] = SubscriptionStatus.CANCELLED.value
                    subscription["updated_at"] = datetime.utcnow().isoformat()

                    db.update("subscriptions", subscription["id"], subscription)

                    # Update user to free tier
                    db.update(
                        "users",
                        subscription["user_id"],
                        {
                            "tier": "free",
                            "subscription_end_date": None,
                            "updated_at": datetime.utcnow().isoformat(),
                        },
                    )

                    expired_trials += 1

                    # Send trial ended email
                    user_data = db.get("users", subscription["user_id"])
                    if user_data:
                        from .email_tasks import send_email_async

                        send_email_async.delay(
                            template_name="trial_ended",
                            to_email=user_data["email"],
                            subject="Your Video AI Studio Trial Has Ended",
                            context={
                                "user_name": user_data.get(
                                    "full_name", user_data["email"].split("@")[0]
                                ),
                                "trial_end_date": period_end.strftime("%B %d, %Y"),
                                "upgrade_url": "https://app.videoaistudio.com/billing/upgrade",
                                "support_email": "support@videoaistudio.com",
                            },
                        )

                except Exception as e:
                    logger.error(f"Failed to process expired trial: {str(e)}")

            elif period_end == today:
                # Trial ends today
                expiring_trials.append(
                    {
                        "subscription_id": subscription["id"],
                        "user_id": subscription["user_id"],
                        "tier": subscription["tier"],
                    }
                )

        return {
            "status": "completed",
            "expired_trials": expired_trials,
            "expiring_trials": expiring_trials,
            "total_trials": len(trial_subscriptions),
        }
    except Exception as e:
        logger.error(f"Error processing trial expirations: {str(e)}")
        return {"status": "failed", "error": str(e)}


@celery.task
def sync_stripe_data() -> Dict[str, Any]:
    """
    Sync local database with Stripe data.
    Runs weekly to ensure data consistency.
    """
    billing_service = BillingService()
    db = FirebaseProvider()

    if not billing_service.stripe_enabled:
        return {"status": "skipped", "reason": "Stripe not configured"}

    try:
        # Sync customers
        customers_synced = 0
        try:
            customers = billing_service.stripe.list_customers(limit=100)
            for customer in customers.get("data", []):
                # Update user with Stripe customer data
                user_data = db.query_one(
                    "users", {"stripe_customer_id": customer["id"]}
                )

                if user_data:
                    updates = {
                        "stripe_customer_id": customer["id"],
                        "updated_at": datetime.utcnow().isoformat(),
                    }

                    if customer.get("email"):
                        updates["email"] = customer["email"]

                    if customer.get("name"):
                        updates["full_name"] = customer["name"]

                    db.update("users", user_data["id"], updates)
                    customers_synced += 1
        except Exception as e:
            logger.error(f"Error syncing customers: {str(e)}")

        # Sync subscriptions
        subscriptions_synced = 0
        try:
            subscriptions = billing_service.stripe.list_subscriptions(limit=100)
            for stripe_sub in subscriptions.get("data", []):
                # Update local subscription
                local_sub = db.query_one(
                    "subscriptions", {"stripe_subscription_id": stripe_sub["id"]}
                )

                if local_sub:
                    subscription = dict(local_sub)
                    subscription["status"] = stripe_sub["status"]
                    subscription["current_period_start"] = datetime.fromtimestamp(
                        stripe_sub["current_period_start"]
                    ).isoformat()
                    subscription["current_period_end"] = datetime.fromtimestamp(
                        stripe_sub["current_period_end"]
                    ).isoformat()
                    subscription["cancel_at_period_end"] = stripe_sub[
                        "cancel_at_period_end"
                    ]
                    subscription["updated_at"] = datetime.utcnow().isoformat()

                    db.update("subscriptions", subscription["id"], subscription)
                    subscriptions_synced += 1
        except Exception as e:
            logger.error(f"Error syncing subscriptions: {str(e)}")

        return {
            "status": "completed",
            "customers_synced": customers_synced,
            "subscriptions_synced": subscriptions_synced,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error syncing Stripe data: {str(e)}")
        return {"status": "failed", "error": str(e)}
