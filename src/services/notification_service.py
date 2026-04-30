"""
Unified notification service for multiple channels.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum

from core.exceptions import ConfigurationError
from services.email_service import EmailService
from core.domain.entities.user import Tier

# from api.websocket import socketio

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
    VIDEO_PROCESSING_STARTED = "video_processing_started"
    VIDEO_PROCESSED = "video_processed"
    VIDEO_FAILED = "video_failed"

    # Other notifications
    TIER_UPGRADED = "tier_upgraded"
    CREDITS_LOW = "credits_low"
    PAYMENT_RECEIVED = "payment_received"
    WELCOME = "welcome"
    NEWSLETTER = "newsletter"
    SYSTEM_ALERT = "system_alert"


class NotificationChannel(str, Enum):
    """Notification channels."""

    EMAIL = "email"
    WEBSOCKET = "websocket"
    IN_APP = "in_app"
    WEBHOOK = "webhook"
    SMS = "sms"  # Future expansion
    PUSH = "push"  # Future expansion


class NotificationService:
    """Unified notification service."""

    def __init__(self):
        self.email_service = EmailService()
        self._webhook_urls = {}
        self._socketio = None

    def get_socketio(self):
        """Lazy load socketio to avoid circular import."""
        if self._socketio is None:
            from api.websocket import socketio

            self._socketio = socketio
        return self._socketio

    def send_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        data: Dict[str, Any],
        channels: Optional[List[NotificationChannel]] = None,
        priority: int = 1,
        video_specific_opt_in: bool = False,  # New param for per-video email opt-in
    ) -> Dict[str, Any]:
        """
        Send notification through specified channels.

        Args:
            user_id: User ID
            notification_type: Type of notification
            data: Notification data
            channels: List of channels to use (default: all available)
            priority: Notification priority (1-5)
            video_specific_opt_in: Whether user opted in for this specific video email

        Returns:
            Send results by channel
        """
        if channels is None:
            channels = [
                NotificationChannel.WEBSOCKET,  # Always try WebSocket
                NotificationChannel.IN_APP,  # Always store in-app
            ]

        results = {}

        # Get user information
        from services.user_service import UserService

        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        if not user:
            logger.error(f"User not found for notification: {user_id}")
            return {"error": "User not found"}

        # Check user notification preferences
        user_settings = user.settings or {}
        notification_preferences = user_settings.get("notification_preferences", {})

        # Prepare base notification data
        notification_data = {
            "user_id": user_id,
            "user_email": user.email,
            "user_tier": user.tier.value,
            "notification_type": notification_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
            "priority": priority,
        }

        # Determine if email should be sent based on tier and notification type
        should_send_email = self._should_send_email(
            user, notification_type, video_specific_opt_in
        )

        # Add email channel if applicable
        if should_send_email and NotificationChannel.EMAIL not in channels:
            channels.append(NotificationChannel.EMAIL)

        # Send through each channel
        for channel in channels:
            # Check if user has opted out of this channel/type
            if not self._is_notification_allowed(
                notification_preferences, notification_type, channel
            ):
                results[channel.value] = {
                    "status": "skipped",
                    "reason": "user_opted_out",
                }
                continue

            try:
                if channel == NotificationChannel.EMAIL:
                    results["email"] = self._send_email_notification(
                        user, notification_type, notification_data
                    )

                elif channel == NotificationChannel.WEBSOCKET:
                    results["websocket"] = self._send_websocket_notification(
                        user_id, notification_type, notification_data
                    )

                elif channel == NotificationChannel.IN_APP:
                    results["in_app"] = self._store_in_app_notification(
                        user_id, notification_type, notification_data
                    )

                elif channel == NotificationChannel.WEBHOOK:
                    results["webhook"] = self._send_webhook_notification(
                        user_id, notification_type, notification_data
                    )

                else:
                    results[channel.value] = {
                        "status": "skipped",
                        "reason": "channel_not_implemented",
                    }

            except Exception as e:
                logger.error(f"Failed to send {channel.value} notification: {str(e)}")
                results[channel.value] = {"status": "error", "error": str(e)}

        # Log notification
        self._log_notification(user_id, notification_type, channels, results)

        return results

    def _should_send_email(
        self, user, notification_type: NotificationType, video_specific_opt_in: bool
    ) -> bool:
        """Determine if email should be sent based on tier and notification type."""

        # CRITICAL NOTIFICATIONS - Send to all tiers
        critical_types = [
            NotificationType.PASSWORD_CHANGED,
            NotificationType.PASSWORD_RESET,
            NotificationType.EMAIL_VERIFIED,
            NotificationType.ACCOUNT_LOCKED,
            NotificationType.PAYMENT_FAILED,
            NotificationType.SECURITY_ALERT,
        ]

        if notification_type in critical_types:
            return True

        # VIDEO PROCESSING NOTIFICATIONS - Tier-based
        if notification_type in [
            NotificationType.VIDEO_PROCESSED,
            NotificationType.VIDEO_FAILED,
        ]:

            # Free tier: No email for video processing
            if user.tier == Tier.FREE:
                return False

            # Starter tier: No email for video processing
            if user.tier == Tier.STARTER:
                return False

            # Pro tier: Email only if opted in for this specific video
            if user.tier == Tier.PRO:
                return video_specific_opt_in

            # Enterprise tier: Email only if opted in
            if user.tier == Tier.ENTERPRISE:
                return video_specific_opt_in

        # CREDITS LOW - Send to paid tiers only
        if notification_type == NotificationType.CREDITS_LOW:
            return user.tier in [Tier.PRO, Tier.ENTERPRISE]

        # PAYMENT RECEIVED - Send to all paying tiers
        if notification_type == NotificationType.PAYMENT_RECEIVED:
            return user.tier in [Tier.STARTER, Tier.PRO, Tier.ENTERPRISE]

        # WELCOME - Send to all
        if notification_type == NotificationType.WELCOME:
            return True

        # NEWSLETTER - Only if user opted in (stored in preferences)
        if notification_type == NotificationType.NEWSLETTER:
            user_prefs = user.settings.get("notification_preferences", {})
            email_prefs = user_prefs.get("email", {})
            return email_prefs.get("newsletter", False)

        # Default: No email
        return False

    def _send_email_notification(
        self, user, notification_type: NotificationType, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send email notification."""
        email_data = {
            "user_email": user.email,
            "user_name": user.full_name or user.email.split("@")[0],
            "app_name": "Video AI Studio",
            "support_email": "support@videoaistudio.com",
            "current_year": datetime.now().year,
            **data["data"],
        }

        # Map notification type to email template
        template_map = {
            NotificationType.VIDEO_PROCESSED: "video_processed",
            NotificationType.VIDEO_FAILED: "video_failed",
            NotificationType.TIER_UPGRADED: "tier_upgrade",
            NotificationType.CREDITS_LOW: "credits_low",
            NotificationType.PAYMENT_RECEIVED: "payment_receipt",
            NotificationType.PAYMENT_FAILED: "payment_failed",
            NotificationType.WELCOME: "welcome",
            NotificationType.SYSTEM_ALERT: "system_alert",
            NotificationType.PASSWORD_CHANGED: "password_changed",
            NotificationType.PASSWORD_RESET: "password_reset",
            NotificationType.EMAIL_VERIFIED: "email_verified",
            NotificationType.ACCOUNT_LOCKED: "account_locked",
            NotificationType.SECURITY_ALERT: "security_alert",
        }

        template_name = template_map.get(notification_type)

        if not template_name:
            # Generic notification
            subject = (
                f"Notification: {notification_type.value.replace('_', ' ').title()}"
            )
            html_content = f"""
            <h1>Notification</h1>
            <p>{data['data'].get('message', 'You have a new notification.')}</p>
            """

            return self.email_service.send_email(
                to_email=user.email, subject=subject, html_content=html_content
            )

        # Use template
        return self.email_service.send_template_email(
            template_name=template_name, to_email=user.email, template_data=email_data
        )

    def _send_websocket_notification(
        self, user_id: str, notification_type: NotificationType, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send WebSocket notification (always sent to all tiers)."""
        try:
            socketio = self.get_socketio()

            # Check if socketio is available
            if socketio is None:
                logger.debug(
                    f"SocketIO not available, skipping WebSocket notification for {user_id}"
                )
                return {"status": "skipped", "reason": "socketio_not_available"}

            # Check if we're in a Celery worker (no app context)
            import os

            if os.environ.get("CELERY_WORKER", "false").lower() == "true":
                logger.debug(
                    f"Skipping WebSocket notification in Celery worker for {user_id}"
                )
                return {"status": "skipped", "reason": "celery_worker"}

            # Emit to user's room
            socketio.emit(
                "notification",
                {
                    "type": notification_type.value,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=user_id,
            )

            logger.debug(f"WebSocket notification sent to user {user_id}")
            return {"status": "sent", "channel": "websocket"}

        except Exception as e:
            logger.error(f"WebSocket notification failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    def _store_in_app_notification(
        self, user_id: str, notification_type: NotificationType, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Store in-app notification in database (always sent to all tiers)."""
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        notification_id = f"notif_{user_id}_{datetime.utcnow().timestamp()}"

        notification = {
            "id": notification_id,
            "user_id": user_id,
            "type": notification_type.value,
            "data": data,
            "read": False,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (
                datetime.utcnow() + timedelta(days=30)
            ).isoformat(),  # Keep for 30 days
        }

        db.save("notifications", notification_id, notification)

        return {"status": "stored", "notification_id": notification_id}

    def _send_webhook_notification(
        self, user_id: str, notification_type: NotificationType, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send webhook notification to user's configured webhook URL."""
        import requests

        # Get user's webhook URL
        webhook_url = self._webhook_urls.get(user_id)
        if not webhook_url:
            return {"status": "skipped", "reason": "no_webhook_configured"}

        try:
            payload = {
                "user_id": user_id,
                "notification_type": notification_type.value,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
                "signature": self._create_webhook_signature(data),
            }

            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            return {
                "status": "sent" if response.status_code == 200 else "error",
                "status_code": response.status_code,
                "response": response.text,
            }

        except Exception as e:
            logger.error(f"Webhook notification failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    def _create_webhook_signature(self, data: Dict[str, Any]) -> str:
        """Create signature for webhook payload."""
        import hmac
        import hashlib
        import json

        secret = os.getenv("WEBHOOK_SECRET", "default_webhook_secret")
        message = json.dumps(data, sort_keys=True)

        signature = hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return signature

    def _is_notification_allowed(
        self,
        preferences: Dict[str, Any],
        notification_type: NotificationType,
        channel: NotificationChannel,
    ) -> bool:
        """Check if notification is allowed based on user preferences."""
        # Default preferences if not set
        default_preferences = {
            "email": {
                "video_processed": True,
                "video_failed": True,
                "tier_upgraded": True,
                "credits_low": True,
                "payment_received": True,
                "payment_failed": True,
                "system_alert": True,
                "welcome": True,
                "newsletter": False,
                "password_changed": True,
                "password_reset": True,
                "email_verified": True,
                "account_locked": True,
                "security_alert": True,
            },
            "websocket": {
                "video_processed": True,
                "video_failed": True,
                "tier_upgraded": True,
                "credits_low": True,
                "payment_received": True,
                "payment_failed": True,
                "system_alert": True,
                "welcome": True,
                "newsletter": False,
                "password_changed": True,
                "password_reset": True,
                "email_verified": True,
                "account_locked": True,
                "security_alert": True,
            },
            "in_app": {
                "video_processed": True,
                "video_failed": True,
                "tier_upgraded": True,
                "credits_low": True,
                "payment_received": True,
                "payment_failed": True,
                "system_alert": True,
                "welcome": True,
                "newsletter": False,
                "password_changed": True,
                "password_reset": True,
                "email_verified": True,
                "account_locked": True,
                "security_alert": True,
            },
        }

        # Merge with user preferences
        channel_prefs = preferences.get(channel.value, {})
        default_channel_prefs = default_preferences.get(channel.value, {})

        # Check if this notification type is allowed
        return channel_prefs.get(
            notification_type.value,
            default_channel_prefs.get(notification_type.value, True),
        )

    def _log_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        channels: List[NotificationChannel],
        results: Dict[str, Any],
    ):
        """Log notification for analytics."""
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        log_entry = {
            "user_id": user_id,
            "notification_type": notification_type.value,
            "channels": [c.value for c in channels],
            "results": results,
            "timestamp": datetime.utcnow().isoformat(),
        }

        log_id = f"notif_log_{user_id}_{datetime.utcnow().timestamp()}"
        db.save("notification_logs", log_id, log_entry)

    def get_user_notifications(
        self, user_id: str, limit: int = 20, offset: int = 0, unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Get user's in-app notifications."""
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        filters = {"user_id": user_id}
        if unread_only:
            filters["read"] = False

        notifications = db.query(
            "notifications",
            filters=filters,
            order_by="created_at",
            descending=True,
            limit=limit,
            offset=offset,
        )

        return notifications

    def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        """Mark notification as read."""
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        notification = db.get("notifications", notification_id)
        if not notification or notification["user_id"] != user_id:
            return False

        notification["read"] = True
        notification["read_at"] = datetime.utcnow().isoformat()

        db.save("notifications", notification_id, notification)

        return True

    def mark_all_notifications_read(self, user_id: str) -> int:
        """Mark all user notifications as read."""
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        notifications = db.query(
            "notifications", filters={"user_id": user_id, "read": False}
        )

        count = 0
        for notification in notifications:
            notification["read"] = True
            notification["read_at"] = datetime.utcnow().isoformat()
            db.save("notifications", notification["id"], notification)
            count += 1

        return count

    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        """Delete notification."""
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        notification = db.get("notifications", notification_id)
        if not notification or notification["user_id"] != user_id:
            return False

        db.delete("notifications", notification_id)

        return True

    def clear_expired_notifications(self, days: int = 30):
        """Clear notifications older than specified days."""
        from providers.firebase_provider import FirebaseProvider
        from datetime import datetime, timedelta

        db = FirebaseProvider()

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        expired = db.query(
            "notifications", filters={"created_at": {"$lt": cutoff_date}}
        )

        count = 0
        for notification in expired:
            db.delete("notifications", notification["id"])
            count += 1

        logger.info(f"Cleared {count} expired notifications")
        return count

    def set_user_webhook(self, user_id: str, webhook_url: str) -> bool:
        """Set user's webhook URL for notifications."""
        if not self._validate_webhook_url(webhook_url):
            return False

        self._webhook_urls[user_id] = webhook_url

        # Store in database for persistence
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        db.save("user_settings", f"{user_id}_webhook", {"webhook_url": webhook_url})

        return True

    def _validate_webhook_url(self, url: str) -> bool:
        """Validate webhook URL."""
        import re

        pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        return bool(re.match(pattern, url))
