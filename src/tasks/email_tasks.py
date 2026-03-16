"""
Async email sending tasks.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .celery_app import celery_app as celery
from services.email_service import EmailService
from providers.email_provider import EmailProvider
from core.domain.entities.user import User

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_async(
    self,
    template_name: str,
    to_email: str,
    subject: str,
    context: Dict[str, Any],
    from_email: Optional[str] = None,
) -> bool:
    """
    Send an email asynchronously.

    Args:
        template_name: Name of the email template
        to_email: Recipient email address
        subject: Email subject
        context: Template context variables
        from_email: Sender email address (optional)

    Returns:
        bool: True if email was sent successfully
    """
    try:
        email_service = EmailService()
        success = email_service.send_email(
            template_name=template_name,
            to_email=to_email,
            subject=subject,
            context=context,
            from_email=from_email,
        )

        if not success:
            logger.warning(f"Failed to send email to {to_email}")
            self.retry(countdown=60 * (self.request.retries + 1))

        return success
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        self.retry(exc=e, countdown=60 * (self.request.retries + 1))

    return False


@celery.task
def send_welcome_email(user_id: str) -> bool:
    """Send welcome email to new user."""
    from services.user_service import UserService

    try:
        user_service = UserService()
        user = user_service.get_user(user_id)

        if not user:
            logger.error(f"User not found: {user_id}")
            return False

        context = {
            "user_name": user.full_name or user.email.split("@")[0],
            "user_email": user.email,
            "signup_date": datetime.utcnow().strftime("%B %d, %Y"),
            "tier": user.tier.value,
            "dashboard_url": "https://app.videoaistudio.com/dashboard",
            "support_email": "support@videoaistudio.com",
        }

        return send_email_async.delay(
            template_name="welcome",
            to_email=user.email,
            subject="Welcome to Video AI Studio! 🎬",
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending welcome email to {user_id}: {str(e)}")
        return False


@celery.task
def send_video_completed_email(video_id: str, user_id: str) -> bool:
    """Send email notification when video processing is completed."""
    from services.video_service import VideoService
    from services.user_service import UserService

    try:
        video_service = VideoService()
        user_service = UserService()

        video = video_service.get_video(video_id, user_id)
        user = user_service.get_user(user_id)

        if not video or not user:
            logger.error(f"Video or user not found: video={video_id}, user={user_id}")
            return False

        # Only send if user has email notifications enabled
        if not user.settings.get("email_notifications", True):
            return True

        context = {
            "user_name": user.full_name or user.email.split("@")[0],
            "video_title": video.title or video.original_filename,
            "video_duration": f"{int(video.duration // 60)}:{int(video.duration % 60):02d}",
            "processing_time": (
                f"{video.processing_time:.1f}s" if video.processing_time else "N/A"
            ),
            "output_quality": video.output_quality,
            "download_url": video.output_video_url,
            "thumbnail_url": video.selected_thumbnail or "",
            "dashboard_url": f"https://app.videoaistudio.com/dashboard/videos/{video_id}",
            "processed_date": datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC"),
        }

        return send_email_async.delay(
            template_name="video_completed",
            to_email=user.email,
            subject=f'Your video "{video.title or video.original_filename}" is ready! ✅',
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending video completed email: {str(e)}")
        return False


@celery.task
def send_password_reset_email(email: str, reset_token: str) -> bool:
    """Send password reset email."""
    try:
        reset_url = (
            f"https://app.videoaistudio.com/auth/reset-password?token={reset_token}"
        )

        context = {
            "reset_url": reset_url,
            "expiration_hours": 24,
            "support_email": "support@videoaistudio.com",
        }

        return send_email_async.delay(
            template_name="password_reset",
            to_email=email,
            subject="Reset Your Video AI Studio Password",
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending password reset email to {email}: {str(e)}")
        return False


@celery.task
def send_tier_upgrade_email(
    user_id: str, from_tier: str, to_tier: str, amount: float
) -> bool:
    """Send tier upgrade confirmation email."""
    from services.user_service import UserService

    try:
        user_service = UserService()
        user = user_service.get_user(user_id)

        if not user:
            logger.error(f"User not found: {user_id}")
            return False

        tier_features = {
            "free": {"videos": 3, "quality": "720p", "retention": "24h"},
            "starter": {"videos": 50, "quality": "1080p", "retention": "7d"},
            "pro": {"videos": 100, "quality": "4K", "retention": "30d"},
            "plus": {"videos": 500, "quality": "4K+HDR", "retention": "90d"},
        }

        from_features = tier_features.get(from_tier, {})
        to_features = tier_features.get(to_tier, {})

        context = {
            "user_name": user.full_name or user.email.split("@")[0],
            "from_tier": from_tier.capitalize(),
            "to_tier": to_tier.capitalize(),
            "amount": f"${amount:.2f}",
            "from_videos": from_features.get("videos", 0),
            "to_videos": to_features.get("videos", 0),
            "from_quality": from_features.get("quality", "720p"),
            "to_quality": to_features.get("quality", "720p"),
            "from_retention": from_features.get("retention", "24h"),
            "to_retention": to_features.get("retention", "24h"),
            "billing_url": "https://app.videoaistudio.com/billing",
            "support_email": "support@videoaistudio.com",
        }

        return send_email_async.delay(
            template_name="tier_upgraded",
            to_email=user.email,
            subject=f"🎉 Welcome to {to_tier.capitalize()} Tier!",
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending tier upgrade email: {str(e)}")
        return False


@celery.task
def send_payment_failed_email(user_id: str, invoice_id: str, amount: float) -> bool:
    """Send payment failed notification email."""
    from services.user_service import UserService

    try:
        user_service = UserService()
        user = user_service.get_user(user_id)

        if not user:
            logger.error(f"User not found: {user_id}")
            return False

        context = {
            "user_name": user.full_name or user.email.split("@")[0],
            "invoice_id": invoice_id,
            "amount": f"${amount:.2f}",
            "retry_url": "https://app.videoaistudio.com/billing/payment",
            "grace_period_days": 3,
            "support_email": "support@videoaistudio.com",
        }

        return send_email_async.delay(
            template_name="payment_failed",
            to_email=user.email,
            subject="⚠️ Payment Failed - Action Required",
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending payment failed email: {str(e)}")
        return False


@celery.task
def send_credits_low_email(user_id: str, current_credits: int) -> bool:
    """Send credits low warning email."""
    from services.user_service import UserService

    try:
        user_service = UserService()
        user = user_service.get_user(user_id)

        if not user:
            logger.error(f"User not found: {user_id}")
            return False

        # Only send for non-unlimited tiers
        if user.tier.value in ["plus", "enterprise"]:
            return True

        context = {
            "user_name": user.full_name or user.email.split("@")[0],
            "current_credits": current_credits,
            "tier": user.tier.value.capitalize(),
            "buy_credits_url": "https://app.videoaistudio.com/billing/credits",
            "upgrade_url": "https://app.videoaistudio.com/billing/upgrade",
            "support_email": "support@videoaistudio.com",
        }

        return send_email_async.delay(
            template_name="credits_low",
            to_email=user.email,
            subject="📉 Your Video AI Studio credits are running low",
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending credits low email: {str(e)}")
        return False


@celery.task
def send_monthly_summary_email(user_id: str) -> bool:
    """Send monthly usage summary email."""
    from services.user_service import UserService
    from services.video_service import VideoService

    try:
        user_service = UserService()
        video_service = VideoService()

        user = user_service.get_user(user_id)

        if not user:
            logger.error(f"User not found: {user_id}")
            return False

        # Get videos processed this month
        videos = video_service.get_user_videos(user_id, limit=100)
        this_month_videos = [
            v for v in videos if v.created_at.month == datetime.utcnow().month
        ]

        total_processing_time = sum(v.duration for v in this_month_videos)
        total_cost = sum(v.total_cost for v in this_month_videos)

        context = {
            "user_name": user.full_name or user.email.split("@")[0],
            "month": datetime.utcnow().strftime("%B %Y"),
            "videos_processed": len(this_month_videos),
            "total_processing_time": f"{int(total_processing_time // 3600)}h {int((total_processing_time % 3600) // 60)}m",
            "average_processing_time": (
                f"{(total_processing_time / len(this_month_videos)):.1f}s"
                if this_month_videos
                else "0s"
            ),
            "total_cost": f"${total_cost:.2f}",
            "tier": user.tier.value.capitalize(),
            "credits_remaining": user.credits_remaining,
            "dashboard_url": "https://app.videoaistudio.com/dashboard",
            "billing_url": "https://app.videoaistudio.com/billing",
            "support_email": "support@videoaistudio.com",
        }

        return send_email_async.delay(
            template_name="monthly_summary",
            to_email=user.email,
            subject=f'📊 Your {datetime.utcnow().strftime("%B")} Video AI Studio Summary',
            context=context,
        )
    except Exception as e:
        logger.error(f"Error sending monthly summary email: {str(e)}")
        return False
