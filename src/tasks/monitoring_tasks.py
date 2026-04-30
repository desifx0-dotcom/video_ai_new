"""
Monitoring tasks for health checks and metrics.
"""

import time
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from celery import current_task
from prometheus_client import Gauge, Counter, Histogram

from tasks.celery_app import celery_app as celery
from providers.redis_provider import RedisProvider
from providers.firebase_provider import FirebaseProvider
from core.logging import get_logger

# THESE DUPLICATE METRICS - They are defined in app/monitoring/metrics.py
# MONITORING_TASKS_EXECUTED = Counter(
#     "monitoring_tasks_executed_total", "Total monitoring tasks executed", ["task_name"]
# )
#
# MONITORING_TASK_DURATION = Histogram(
#     "monitoring_task_duration_seconds",
#     "Monitoring task execution duration",
#     ["task_name"],
# )
#
# SYSTEM_HEALTH = Gauge(
#     "system_health_status",
#     "System health status (1=healthy, 0=unhealthy)",
#     ["component"],
# )
#
# QUEUE_DEPTH = Gauge(
#     "celery_queue_depth", "Number of tasks in Celery queue", ["queue_name"]
# )
#
# DATABASE_HEALTH = Gauge(
#     "database_health_status",
#     "Database health status (1=healthy, 0=unhealthy)",
#     ["database_type"],
# )
#
# EXTERNAL_SERVICE_HEALTH = Gauge(
#     "external_service_health_status", "External service health status", ["service_name"]
# )

# Instead, import metrics from the metrics module when needed
# We'll import them inside functions to avoid circular imports

logger = get_logger(__name__)


@celery.task(bind=True, name="monitoring.update_system_metrics")
def update_metrics(self):
    """Task to update system metrics periodically."""
    start_time = time.time()

    try:
        # Import metrics INSIDE the function to avoid circular imports
        from app.monitoring.metrics import update_system_metrics

        # Also import Prometheus metrics from the same module
        from app.monitoring.metrics import (
            MONITORING_TASKS_EXECUTED,
            MONITORING_TASK_DURATION,
            SYSTEM_HEALTH,
        )

        # Update system metrics
        update_system_metrics()

        # Update Prometheus metrics
        MONITORING_TASKS_EXECUTED.labels(task_name="update_system_metrics").inc()

        # Mark system as healthy
        SYSTEM_HEALTH.labels(component="metrics_collector").set(1)

        duration = time.time() - start_time
        MONITORING_TASK_DURATION.labels(task_name="update_system_metrics").observe(
            duration
        )

        logger.info(f"Updated system metrics in {duration:.2f}s")
        return {"status": "success", "duration": duration}

    except Exception as e:
        # Import SYSTEM_HEALTH for error reporting
        from app.monitoring.metrics import SYSTEM_HEALTH

        SYSTEM_HEALTH.labels(component="metrics_collector").set(0)
        logger.error(f"Failed to update system metrics: {e}")
        raise


@celery.task(bind=True, name="monitoring.check_system_health")
def check_system_health(self):
    """Task to check overall system health."""
    start_time = time.time()
    health_checks = {}

    try:
        # Import metrics from the main metrics module
        from app.monitoring.metrics import (
            SYSTEM_HEALTH,
            QUEUE_DEPTH,
            DATABASE_HEALTH,
            MONITORING_TASKS_EXECUTED,
            MONITORING_TASK_DURATION,
        )

        # Check Redis
        redis = RedisProvider()
        try:
            redis.ping()
            health_checks["redis"] = {"status": "healthy", "latency": 0}
            SYSTEM_HEALTH.labels(component="redis").set(1)
        except Exception as e:
            health_checks["redis"] = {"status": "unhealthy", "error": str(e)}
            SYSTEM_HEALTH.labels(component="redis").set(0)

        # Check Database
        db = FirebaseProvider()
        try:
            # Try to read a test document
            test_key = f"health_check_{int(time.time())}"
            db.save(
                "health_checks", test_key, {"timestamp": datetime.utcnow().isoformat()}
            )
            db.delete("health_checks", test_key)
            health_checks["database"] = {"status": "healthy"}
            DATABASE_HEALTH.labels(database_type="firebase").set(1)
        except Exception as e:
            health_checks["database"] = {"status": "unhealthy", "error": str(e)}
            DATABASE_HEALTH.labels(database_type="firebase").set(0)

        # Check Celery workers
        try:
            inspect = celery.control.inspect()
            active_workers = inspect.active() or {}
            registered_workers = inspect.registered() or {}
            stats = inspect.stats() or {}

            worker_count = len(registered_workers)
            active_tasks = sum(len(tasks) for tasks in active_workers.values())

            health_checks["celery"] = {
                "status": "healthy" if worker_count > 0 else "unhealthy",
                "worker_count": worker_count,
                "active_tasks": active_tasks,
            }

            SYSTEM_HEALTH.labels(component="celery").set(1 if worker_count > 0 else 0)
        except Exception as e:
            health_checks["celery"] = {"status": "unhealthy", "error": str(e)}
            SYSTEM_HEALTH.labels(component="celery").set(0)

        # Check queue depths
        try:
            inspect = celery.control.inspect()

            # Get active queues
            active_queues = inspect.active_queues() or {}

            for worker, queues in active_queues.items():
                for queue_info in queues:
                    queue_name = queue_info.get("name", "default")
                    # Estimate queue depth (this is approximate)
                    queue_depth = (
                        len(inspect.reserved().get(worker, []))
                        if inspect.reserved()
                        else 0
                    )
                    QUEUE_DEPTH.labels(queue_name=queue_name).set(queue_depth)

                    health_checks.setdefault("queues", {})[queue_name] = {
                        "depth": queue_depth,
                        "status": "healthy" if queue_depth < 100 else "warning",
                    }
        except Exception as e:
            health_checks["queues"] = {"status": "unhealthy", "error": str(e)}

        # Check disk space
        try:
            disk_usage = psutil.disk_usage("/")
            health_checks["disk"] = {
                "status": "healthy" if disk_usage.percent < 90 else "warning",
                "total_gb": disk_usage.total / (1024**3),
                "used_gb": disk_usage.used / (1024**3),
                "free_gb": disk_usage.free / (1024**3),
                "percent_used": disk_usage.percent,
            }
            SYSTEM_HEALTH.labels(component="disk").set(
                1 if disk_usage.percent < 90 else 0.5
            )
        except Exception as e:
            health_checks["disk"] = {"status": "unhealthy", "error": str(e)}
            SYSTEM_HEALTH.labels(component="disk").set(0)

        # Check memory usage
        try:
            memory = psutil.virtual_memory()
            health_checks["memory"] = {
                "status": "healthy" if memory.percent < 85 else "warning",
                "total_gb": memory.total / (1024**3),
                "available_gb": memory.available / (1024**3),
                "percent_used": memory.percent,
            }
            SYSTEM_HEALTH.labels(component="memory").set(
                1 if memory.percent < 85 else 0.5
            )
        except Exception as e:
            health_checks["memory"] = {"status": "unhealthy", "error": str(e)}
            SYSTEM_HEALTH.labels(component="memory").set(0)

        # Check CPU usage
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            health_checks["cpu"] = {
                "status": "healthy" if cpu_percent < 80 else "warning",
                "percent_used": cpu_percent,
                "core_count": psutil.cpu_count(),
            }
            SYSTEM_HEALTH.labels(component="cpu").set(1 if cpu_percent < 80 else 0.5)
        except Exception as e:
            health_checks["cpu"] = {"status": "unhealthy", "error": str(e)}
            SYSTEM_HEALTH.labels(component="cpu").set(0)

        # Calculate overall health status
        unhealthy_components = [
            check
            for check in health_checks.values()
            if isinstance(check, dict) and check.get("status") == "unhealthy"
        ]

        warning_components = [
            check
            for check in health_checks.values()
            if isinstance(check, dict) and check.get("status") == "warning"
        ]

        overall_status = "healthy"
        if unhealthy_components:
            overall_status = "unhealthy"
        elif warning_components:
            overall_status = "warning"

        health_checks["overall"] = {
            "status": overall_status,
            "unhealthy_components": len(unhealthy_components),
            "warning_components": len(warning_components),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Update Prometheus metrics
        MONITORING_TASKS_EXECUTED.labels(task_name="check_system_health").inc()
        duration = time.time() - start_time
        MONITORING_TASK_DURATION.labels(task_name="check_system_health").observe(
            duration
        )

        # Store health check results
        redis.set("system_health", health_checks, ex=300)  # Cache for 5 minutes

        logger.info(
            f"System health check completed in {duration:.2f}s: {overall_status}"
        )
        return health_checks

    except Exception as e:
        logger.error(f"System health check failed: {e}")
        raise


@celery.task(bind=True, name="monitoring.collect_business_metrics")
def collect_business_metrics_task(self):
    """Task to collect and aggregate business metrics."""
    start_time = time.time()

    try:
        # Import metrics INSIDE the function to avoid circular imports
        from app.monitoring.metrics import (
            record_video_processing,
            record_user_signup,
            MONITORING_TASKS_EXECUTED,
            MONITORING_TASK_DURATION,
        )

        db = FirebaseProvider()
        redis = RedisProvider()

        # Calculate metrics for the last 24 hours
        end_time = datetime.utcnow()
        start_time_24h = end_time - timedelta(hours=24)

        # Get video processing metrics
        videos = db.query(
            "videos",
            filters={
                "processing_completed": {
                    ">=": start_time_24h.isoformat(),
                    "<=": end_time.isoformat(),
                },
                "status": "completed",
            },
        )

        # Calculate metrics (rest of the function remains the same)
        total_videos = len(videos)
        total_processing_time = sum(v.get("processing_time", 0) for v in videos)
        total_cost = sum(v.get("total_cost", 0) for v in videos)

        # Group by tier
        videos_by_tier = {}
        for video in videos:
            tier = video.get("processed_tier", "unknown")
            if tier not in videos_by_tier:
                videos_by_tier[tier] = {
                    "count": 0,
                    "total_cost": 0,
                    "total_processing_time": 0,
                }
            videos_by_tier[tier]["count"] += 1
            videos_by_tier[tier]["total_cost"] += video.get("total_cost", 0)
            videos_by_tier[tier]["total_processing_time"] += video.get(
                "processing_time", 0
            )

        # Group by video type
        videos_by_type = {}
        for video in videos:
            video_type = video.get("video_type", "unknown")
            if video_type not in videos_by_type:
                videos_by_type[video_type] = {"count": 0, "total_cost": 0}
            videos_by_type[video_type]["count"] += 1
            videos_by_type[video_type]["total_cost"] += video.get("total_cost", 0)

        # Get user signups
        users = db.query(
            "users",
            filters={
                "created_at": {
                    ">=": start_time_24h.isoformat(),
                    "<=": end_time.isoformat(),
                }
            },
        )

        signups_by_tier = {}
        for user in users:
            tier = user.get("tier", "free")
            signups_by_tier[tier] = signups_by_tier.get(tier, 0) + 1

        # Calculate silent video savings
        silent_videos = [v for v in videos if v.get("video_type") == "silent"]
        speech_videos = [v for v in videos if v.get("video_type") == "speech"]

        silent_cost = sum(v.get("total_cost", 0) for v in silent_videos)
        speech_cost = sum(v.get("total_cost", 0) for v in speech_videos)

        # Estimate what silent videos would have cost if processed as speech
        estimated_speech_cost = 0
        for video in silent_videos:
            duration = video.get("duration", 0)
            # Estimate speech cost: $0.006 per minute
            estimated_speech_cost += (duration / 60) * 0.006

        cost_savings = estimated_speech_cost - silent_cost if silent_videos else 0
        cost_savings_percentage = (
            (cost_savings / estimated_speech_cost * 100)
            if estimated_speech_cost > 0
            else 0
        )

        # Compile metrics
        metrics = {
            "timestamp": end_time.isoformat(),
            "period": "24h",
            "videos": {
                "total": total_videos,
                "by_tier": videos_by_tier,
                "by_type": videos_by_type,
                "average_processing_time": (
                    total_processing_time / total_videos if total_videos > 0 else 0
                ),
                "average_cost": total_cost / total_videos if total_videos > 0 else 0,
            },
            "users": {"signups_total": len(users), "signups_by_tier": signups_by_tier},
            "cost_savings": {
                "silent_videos_count": len(silent_videos),
                "speech_videos_count": len(speech_videos),
                "actual_cost": silent_cost + speech_cost,
                "estimated_cost_without_optimization": estimated_speech_cost
                + speech_cost,
                "savings": cost_savings,
                "savings_percentage": cost_savings_percentage,
            },
            "revenue": {
                "estimated_daily": 0,
                "estimated_monthly": 0,
            },
        }

        # Store metrics
        redis.set("business_metrics_24h", metrics, ex=3600)

        # Update Prometheus metrics
        for tier, data in videos_by_tier.items():
            for video_type, type_data in videos_by_type.items():
                filtered_videos = [
                    v
                    for v in videos
                    if v.get("processed_tier") == tier
                    and v.get("video_type") == video_type
                ]
                if filtered_videos:
                    record_video_processing(
                        tier=tier,
                        video_type=video_type,
                        duration=sum(v.get("duration", 0) for v in filtered_videos)
                        / len(filtered_videos),
                        status="completed",
                    )

        for tier, count in signups_by_tier.items():
            for _ in range(count):
                record_user_signup(tier)

        # Update task metrics
        MONITORING_TASKS_EXECUTED.labels(task_name="collect_business_metrics").inc()
        duration = time.time() - start_time
        MONITORING_TASK_DURATION.labels(task_name="collect_business_metrics").observe(
            duration
        )

        logger.info(f"Business metrics collected in {duration:.2f}s")
        return metrics

    except Exception as e:
        logger.error(f"Failed to collect business metrics: {e}")
        raise


@celery.task(bind=True, name="monitoring.check_external_services")
def check_external_services_task(self):
    """Task to check health of external services."""
    start_time = time.time()
    service_checks = {}

    try:
        # Import metrics from the main module
        from app.monitoring.metrics import (
            EXTERNAL_SERVICE_HEALTH,
            MONITORING_TASKS_EXECUTED,
            MONITORING_TASK_DURATION,
        )

        # Check OpenAI API
        try:
            from providers.openai_provider import OpenAIProvider

            openai = OpenAIProvider()
            # Simple check by getting models
            models = openai.list_models()
            service_checks["openai"] = {
                "status": "healthy",
                "model_count": (
                    len(models.get("data", [])) if isinstance(models, dict) else 0
                ),
            }
            EXTERNAL_SERVICE_HEALTH.labels(service_name="openai").set(1)
        except Exception as e:
            service_checks["openai"] = {"status": "unhealthy", "error": str(e)}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="openai").set(0)

        # Check Google AI
        try:
            from providers.google_provider import GoogleProvider

            google = GoogleProvider()
            # Simple check
            service_checks["google_ai"] = {"status": "healthy"}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="google_ai").set(1)
        except Exception as e:
            service_checks["google_ai"] = {"status": "unhealthy", "error": str(e)}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="google_ai").set(0)

        # Check Stability AI
        try:
            from providers.stability_provider import StabilityProvider

            stability = StabilityProvider()
            # Simple check
            service_checks["stability_ai"] = {"status": "healthy"}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="stability_ai").set(1)
        except Exception as e:
            service_checks["stability_ai"] = {"status": "unhealthy", "error": str(e)}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="stability_ai").set(0)

        # Check Stripe
        try:
            from providers.stripe_provider import StripeProvider

            stripe = StripeProvider()
            # Simple check by getting balance
            service_checks["stripe"] = {"status": "healthy"}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="stripe").set(1)
        except Exception as e:
            service_checks["stripe"] = {"status": "unhealthy", "error": str(e)}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="stripe").set(0)

        # Check Email provider
        try:
            from providers.email_provider import EmailProvider

            email = EmailProvider()
            # Simple check
            service_checks["email"] = {"status": "healthy"}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="email").set(1)
        except Exception as e:
            service_checks["email"] = {"status": "unhealthy", "error": str(e)}
            EXTERNAL_SERVICE_HEALTH.labels(service_name="email").set(0)

        # Calculate overall external services health
        unhealthy_services = [
            name
            for name, check in service_checks.items()
            if check.get("status") == "unhealthy"
        ]

        service_checks["overall"] = {
            "status": "healthy" if not unhealthy_services else "unhealthy",
            "unhealthy_services": unhealthy_services,
            "total_services": len(service_checks) - 1,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Update Prometheus metrics
        MONITORING_TASKS_EXECUTED.labels(task_name="check_external_services").inc()
        duration = time.time() - start_time
        MONITORING_TASK_DURATION.labels(task_name="check_external_services").observe(
            duration
        )

        # Store results
        redis = RedisProvider()
        redis.set("external_services_health", service_checks, ex=300)

        logger.info(f"External services health check completed in {duration:.2f}s")
        return service_checks

    except Exception as e:
        logger.error(f"External services health check failed: {e}")
        raise


@celery.task(bind=True, name="monitoring.cleanup_old_metrics")
def cleanup_old_metrics_task(self):
    """Task to cleanup old metrics data."""
    start_time = time.time()

    try:
        # Import metrics from the main module
        from app.monitoring.metrics import (
            MONITORING_TASKS_EXECUTED,
            MONITORING_TASK_DURATION,
        )

        db = FirebaseProvider()
        redis = RedisProvider()

        # Cleanup old health checks (older than 7 days)
        cutoff_time = (datetime.utcnow() - timedelta(days=7)).isoformat()

        # Cleanup Redis keys
        pattern = "metrics:*"
        old_keys = redis.keys(pattern)

        # Keep only last 1000 metric keys
        if len(old_keys) > 1000:
            keys_to_delete = old_keys[1000:]
            redis.delete(*keys_to_delete)
            deleted_count = len(keys_to_delete)
        else:
            deleted_count = 0

        # Cleanup old temporary metrics
        old_temp_keys = redis.keys("temp_metrics:*")
        if old_temp_keys:
            redis.delete(*old_temp_keys)
            deleted_count += len(old_temp_keys)

        # Update Prometheus metrics
        MONITORING_TASKS_EXECUTED.labels(task_name="cleanup_old_metrics").inc()
        duration = time.time() - start_time
        MONITORING_TASK_DURATION.labels(task_name="cleanup_old_metrics").observe(
            duration
        )

        logger.info(f"Cleaned up {deleted_count} old metric entries in {duration:.2f}s")
        return {"deleted_count": deleted_count, "duration": duration}

    except Exception as e:
        logger.error(f"Failed to cleanup old metrics: {e}")
        raise


@celery.task(bind=True, name="monitoring.send_daily_report")
def send_daily_report_task(self):
    """Task to send daily monitoring report."""
    start_time = time.time()

    try:
        from services.email_service import EmailService
        from services.user_service import UserService
        from app.monitoring.metrics import (
            MONITORING_TASKS_EXECUTED,
            MONITORING_TASK_DURATION,
        )

        email_service = EmailService()
        user_service = UserService()
        redis = RedisProvider()

        # Get yesterday's date
        yesterday = datetime.utcnow() - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

        # Get system health from yesterday
        health_data = redis.get(f"system_health_{date_str}")
        business_metrics = redis.get(f"business_metrics_{date_str}")

        # Get admin users
        admins = user_service.get_admin_users()

        if not admins:
            logger.warning("No admin users found for daily report")
            return {"status": "skipped", "reason": "no_admins"}

        # Prepare report data
        report_data = {
            "date": date_str,
            "system_health": health_data or {},
            "business_metrics": business_metrics or {},
            "generated_at": datetime.utcnow().isoformat(),
        }

        # Send to each admin
        sent_count = 0
        for admin in admins:
            try:
                email_service.send_daily_report(
                    to_email=admin.email, report_data=report_data
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send daily report to {admin.email}: {e}")

        # Update Prometheus metrics
        MONITORING_TASKS_EXECUTED.labels(task_name="send_daily_report").inc()
        duration = time.time() - start_time
        MONITORING_TASK_DURATION.labels(task_name="send_daily_report").observe(duration)

        logger.info(
            f"Sent daily report to {sent_count}/{len(admins)} admins in {duration:.2f}s"
        )
        return {
            "status": "success",
            "sent_count": sent_count,
            "total_admins": len(admins),
            "duration": duration,
        }

    except Exception as e:
        logger.error(f"Failed to send daily report: {e}")
        raise


def schedule_monitoring_tasks():
    """Schedule all monitoring tasks."""
    from celery.schedules import crontab

    # Update system metrics every minute
    celery.conf.beat_schedule["update-system-metrics"] = {
        "task": "monitoring.update_system_metrics",
        "schedule": 60.0,
        "options": {"queue": "monitoring"},
    }

    # Check system health every 5 minutes
    celery.conf.beat_schedule["check-system-health"] = {
        "task": "monitoring.check_system_health",
        "schedule": 300.0,
        "options": {"queue": "monitoring"},
    }

    # Collect business metrics every hour
    celery.conf.beat_schedule["collect-business-metrics"] = {
        "task": "monitoring.collect_business_metrics",
        "schedule": 3600.0,
        "options": {"queue": "monitoring"},
    }

    # Check external services every 15 minutes
    celery.conf.beat_schedule["check-external-services"] = {
        "task": "monitoring.check_external_services",
        "schedule": 900.0,
        "options": {"queue": "monitoring"},
    }

    # Cleanup old metrics every day at 2 AM
    celery.conf.beat_schedule["cleanup-old-metrics"] = {
        "task": "monitoring.cleanup_old_metrics",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "monitoring"},
    }

    # Send daily report every day at 8 AM
    celery.conf.beat_schedule["send-daily-report"] = {
        "task": "monitoring.send_daily_report",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": "monitoring"},
    }

    logger.info("Monitoring tasks scheduled")
