"""
Celery configuration.
"""

import os
from pathlib import Path
from celery import Celery
from kombu import Queue, Exchange
from dotenv import load_dotenv

# Load .env file explicitly
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

#  Get Redis URL from environment (now it should work)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Also check alternative env vars
if not redis_url or redis_url == "memory://":
    redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    print(f"⚠️  Using CELERY_BROKER_URL: {redis_url}")

# Print for debugging
print(
    f"🔍 Redis URL: {redis_url[:50]}..."
    if len(redis_url) > 50
    else f"🔍 Redis URL: {redis_url}"
)

# Use the Redis URL directly
celery_broker = redis_url
celery_backend = redis_url

print(f"✅ Using Redis transport for Celery")

# Create Celery instance
celery_app = Celery(
    "video_ai_studio",
    broker=celery_broker,
    backend=celery_backend,
)

# Configure Celery
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task settings

    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    # Worker settings
    worker_max_tasks_per_child=100,
    worker_prefetch_multiplier=1,
    worker_max_memory_per_child=300000,  # 300MB
    # Queue configuration
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # Beat schedule
    beat_schedule={
        # Video processing
        "retry-failed-videos-every-hour": {
            "task": "tasks.video_tasks.retry_failed_videos",
            "schedule": 3600.0,  # Every hour
        },
        # Billing
        "process-subscription-renewals-daily": {
            "task": "tasks.billing_tasks.process_subscription_renewals",
            "schedule": 86400.0,  # Daily
            "args": (),
        },
        "handle-failed-payments-daily": {
            "task": "tasks.billing_tasks.handle_failed_payments",
            "schedule": 86400.0,  # Daily
        },
        # Cleanup
        "cleanup-expired-data-daily": {
            "task": "tasks.cleanup_tasks.cleanup_expired_data",
            "schedule": 86400.0,  # Daily
            "args": (30,),  # Keep 30 days of data
        },
        "cleanup-temp-files-hourly": {
            "task": "tasks.cleanup_tasks.cleanup_temp_files",
            "schedule": 3600.0,  # Hourly
        },
        # Monitoring
        "update-system-metrics-every-5-minutes": {
            "task": "tasks.monitoring_tasks.update_system_metrics",
            "schedule": 300.0,  # Every 5 minutes
        },
        "check-system-health-every-15-minutes": {
            "task": "tasks.monitoring_tasks.check_system_health",
            "schedule": 900.0,  # Every 15 minutes
        },
        "generate-daily-report": {
            "task": "tasks.monitoring_tasks.generate_daily_report",
            "schedule": 86400.0,  # Daily
            "args": (),
        },
        # User management
        "send-monthly-summaries": {
            "task": "tasks.email_tasks.send_monthly_summary_async",
            "schedule": 86400.0,  # Daily (will check if it's month end)
        },
    },
    # Production retry settings
    task_reject_on_worker_lost=True,
    task_acks_late=True,
    task_track_started=True,
    task_send_sent_event=True,

    # Dead letter queue configuration
    task_default_retry_delay=60,
    task_max_retries=3,

    # Result expiration
    result_expires=86400,  # 24 hours

    # Rate limits for API calls
    task_annotations={
        'tasks.video_tasks.process_video_async': {
            'rate_limit': '10/m',  # Max 10 video processes per minute
            'max_retries': 3,
            'default_retry_delay': 60,
        },
        'tasks.video_tasks.apply_different_styles_async': {
            'rate_limit': '20/m',  # Max 20 style applications per minute
            'max_retries': 2,
            'default_retry_delay': 30,
        }
    },

    # Dead letter exchange
    task_queues=(
        Queue('video_processing', Exchange('video_processing'), routing_key='video_processing'),
        Queue('dead_letter', Exchange('dead_letter'), routing_key='dead_letter'),
        Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
        Queue(
            "medium_priority",
            Exchange("medium_priority"),
            routing_key="medium_priority",
        ),
        Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
        Queue("default", Exchange("default"), routing_key="default"),
    ),
# Route configuration
    task_routes={
        'tasks.video_tasks.process_video_async': {
            'queue': 'video_processing',
            'routing_key': 'video_processing',
        },
        'tasks.video_tasks.apply_different_styles_async': {
            'queue': 'video_processing',
            'routing_key': 'video_processing',
        },
        "tasks.video_tasks.process_video_async": {
            "queue": "high_priority",
            "routing_key": "high_priority",
        },
        "tasks.video_tasks.process_video_batch": {
            "queue": "medium_priority",
            "routing_key": "medium_priority",
        },
        "tasks.email_tasks.*": {"queue": "low_priority", "routing_key": "low_priority"},
        "tasks.cleanup_tasks.*": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "tasks.billing_tasks.*": {
            "queue": "medium_priority",
            "routing_key": "medium_priority",
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["tasks"])


if __name__ == "__main__":
    celery_app.start()
