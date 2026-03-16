"""
Notification tasks for user notifications.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from .celery_app import celery_app as celery
from providers.firebase_provider import FirebaseProvider
from services.notification_service import NotificationService
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Notification types."""

    # Critical notifications (for all tiers)
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFIED = "email_verified"
    ACCOUNT_LOCKED = "account_locked"
    PAYMENT_FAILED = "payment_failed"
    SECURITY_ALERT = "security_alert"

    # Processing notifications (tier-controlled)
    VIDEO_PROCESSING_STARTED = "video_processing_started"  # New!
    VIDEO_PROCESSED = "video_processed"
    VIDEO_FAILED = "video_failed"

    # Other notifications
    TIER_UPGRADED = "tier_upgraded"
    CREDITS_LOW = "credits_low"
    PAYMENT_RECEIVED = "payment_received"
    WELCOME = "welcome"
    NEWSLETTER = "newsletter"
    SYSTEM_ALERT = "system_alert"


@celery.task
def send_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    channels: Optional[List[str]] = None,
) -> bool:
    """
    Send a notification to a user.

    Args:
        user_id: User ID to send notification to
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        data: Additional data for the notification
        channels: Channels to send through (email, websocket, in_app)

    Returns:
        bool: True if notification was sent successfully
    """
    try:
        notification_service = NotificationService()

        success = notification_service.send_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data or {},
            channels=channels or ["in_app", "email"],
        )

        return success
    except Exception as e:
        logger.error(f"Error sending notification to user {user_id}: {str(e)}")
        return False


@celery.task
def broadcast_progress_update(video_id: str, progress: float, status: str) -> bool:
    """
    Broadcast video processing progress update via WebSocket.

    Args:
        video_id: Video ID
        progress: Progress percentage (0-100)
        status: Processing status

    Returns:
        bool: True if broadcast was successful
    """
    try:
        db = FirebaseProvider()

        # Get video data
        video_data = db.get("videos", video_id)
        if not video_data:
            logger.error(f"Video not found: {video_id}")
            return False

        # Broadcast via WebSocket
        from api.websocket import socketio

        socketio.emit(
            "video_progress",
            {
                "video_id": video_id,
                "user_id": video_data["user_id"],
                "progress": progress,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        return True
    except Exception as e:
        logger.error(f"Error broadcasting progress update: {str(e)}")
        return False


@celery.task
def send_bulk_notifications(
    user_ids: List[str],
    notification_type: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send notifications to multiple users.

    Args:
        user_ids: List of user IDs
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        data: Additional data for the notification

    Returns:
        Dict with statistics
    """
    stats = {
        "total_users": len(user_ids),
        "notifications_sent": 0,
        "notifications_failed": 0,
        "errors": [],
    }

    for user_id in user_ids:
        try:
            success = send_notification.delay(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                data=data,
            )

            if success:
                stats["notifications_sent"] += 1
            else:
                stats["notifications_failed"] += 1

        except Exception as e:
            stats["notifications_failed"] += 1
            stats["errors"].append(f"User {user_id}: {str(e)}")

    return stats


@celery.task
def send_system_maintenance_notification(
    maintenance_start: datetime, maintenance_end: datetime, message: str
) -> Dict[str, Any]:
    """
    Send system maintenance notification to all users.

    Args:
        maintenance_start: Maintenance start time
        maintenance_end: Maintenance end time
        message: Maintenance message

    Returns:
        Dict with statistics
    """
    db = FirebaseProvider()

    try:
        # Get all active users
        users = db.query("users", filters={"is_active": True})
        user_ids = [user["id"] for user in users]

        # Send notifications
        return send_bulk_notifications.delay(
            user_ids=user_ids,
            notification_type="system_maintenance",
            title="System Maintenance Scheduled",
            message=message,
            data={
                "maintenance_start": maintenance_start.isoformat(),
                "maintenance_end": maintenance_end.isoformat(),
                "duration_hours": (maintenance_end - maintenance_start).total_seconds()
                / 3600,
            },
        )
    except Exception as e:
        logger.error(f"Error sending system maintenance notification: {str(e)}")
        return {"status": "failed", "error": str(e)}


@celery.task
def send_feature_update_notification(
    feature_name: str,
    feature_description: str,
    update_type: str = "new_feature",  # new_feature, improvement, bug_fix
) -> Dict[str, Any]:
    """
    Send feature update notification to all users.

    Args:
        feature_name: Name of the feature
        feature_description: Description of the feature
        update_type: Type of update

    Returns:
        Dict with statistics
    """
    db = FirebaseProvider()

    try:
        # Get all active users
        users = db.query("users", filters={"is_active": True})
        user_ids = [user["id"] for user in users]

        # Map update type to title
        title_map = {
            "new_feature": "🎉 New Feature Available",
            "improvement": "✨ Feature Improvement",
            "bug_fix": "🐛 Bug Fix Released",
        }

        title = title_map.get(update_type, "📢 System Update")

        # Send notifications
        return send_bulk_notifications.delay(
            user_ids=user_ids,
            notification_type="feature_update",
            title=title,
            message=f"{feature_name}: {feature_description}",
            data={
                "feature_name": feature_name,
                "feature_description": feature_description,
                "update_type": update_type,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"Error sending feature update notification: {str(e)}")
        return {"status": "failed", "error": str(e)}


@celery.task
def send_usage_alert_notifications() -> Dict[str, Any]:
    """
    Send usage alert notifications to users.
    Runs daily to alert users about usage limits.
    """
    db = FirebaseProvider()

    stats = {"low_credit_alerts": 0, "limit_warning_alerts": 0, "errors": []}

    try:
        # Get all active users
        users = db.query("users", filters={"is_active": True})

        for user_data in users:
            user = dict(user_data)

            try:
                # Check for low credits (for non-unlimited tiers)
                if user.get("tier") not in ["plus", "enterprise"]:
                    credits = user.get("credits_remaining", 0)

                    if credits <= 10:  # Alert when credits are low
                        send_notification.delay(
                            user_id=user["id"],
                            notification_type="credits_low",
                            title="⚠️ Credits Running Low",
                            message=f"You have {credits} credits remaining. Consider purchasing more credits.",
                            data={
                                "current_credits": credits,
                                "tier": user.get("tier", "free"),
                                "buy_credits_url": "https://app.videoaistudio.com/billing/credits",
                            },
                        )
                        stats["low_credit_alerts"] += 1

                # Check for monthly limit warnings
                videos_processed = user.get("videos_processed_this_month", 0)
                monthly_limit = user.get("monthly_video_limit", 3)

                if monthly_limit > 0:  # Only for tiers with limits
                    usage_percentage = (videos_processed / monthly_limit) * 100

                    if usage_percentage >= 80:  # Alert at 80% usage
                        remaining = monthly_limit - videos_processed

                        send_notification.delay(
                            user_id=user["id"],
                            notification_type="usage_warning",
                            title="📊 Monthly Usage Warning",
                            message=f"You have used {videos_processed}/{monthly_limit} videos this month. {remaining} videos remaining.",
                            data={
                                "videos_processed": videos_processed,
                                "monthly_limit": monthly_limit,
                                "remaining": remaining,
                                "usage_percentage": usage_percentage,
                                "upgrade_url": "https://app.videoaistudio.com/billing/upgrade",
                            },
                        )
                        stats["limit_warning_alerts"] += 1

            except Exception as e:
                stats["errors"].append(f"User {user['id']}: {str(e)}")

        logger.info(f"Usage alert notifications sent: {stats}")
        return {"status": "completed", "stats": stats}

    except Exception as e:
        logger.error(f"Error sending usage alert notifications: {str(e)}")
        return {"status": "failed", "error": str(e), "stats": stats}
