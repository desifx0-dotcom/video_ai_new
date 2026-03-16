"""
Celery tasks package.
"""

from .celery_app import celery_app as celery
from .video_tasks import process_video_async, retry_failed_videos
from .email_tasks import (
    send_email_async,
    send_welcome_email,
    send_video_completed_email,
)
from .billing_tasks import process_subscription_renewals, send_payment_reminders
from .cleanup_tasks import cleanup_expired_data, cleanup_temporary_files , cleanup_orphaned_files , cleanup_failed_videos
from .notification_tasks import send_notification, broadcast_progress_update
from .monitoring_tasks import (
    check_system_health,
    update_metrics,
    send_daily_report_task,
)

__all__ = [
    "celery",
    "process_video_async",
    "retry_failed_video",
    "send_email_async",
    "send_welcome_email",
    "send_video_completed_email",
    "process_subscription_renewals",
    "send_payment_reminders",
    "cleanup_expired_data",
    "cleanup_temporary_files",
    "cleanup_orphaned_files",
    "cleanup_failed_videos",
    "send_notification",
    "broadcast_progress_update",
    "check_system_health",
    "update_metrics",
    "send_daily_report_task",
]
