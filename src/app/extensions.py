"""
Flask extensions initialization.
"""

from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from celery import Celery

# Global extensions
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)
celery = Celery()


def init_extensions(app):
    """Initialize all Flask extensions."""

    # JWT Authentication
    jwt.init_app(app)

    # Rate Limiting
    limiter.init_app(app)

    # This allows status polling without hitting rate limits
    exempt_endpoints = [
        "api_v1_bp.videos.get_processing_status",  # Status endpoint
        "health",  # Health check
        "metrics",  # Metrics endpoint
    ]

    for endpoint in exempt_endpoints:
        try:
            limiter.exempt(endpoint)
        except Exception as e:
            print(f"Warning: Could not exempt {endpoint}: {e}")

    # Celery
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=30 * 60,  # 30 minutes
        task_soft_time_limit=25 * 60,  # 25 minutes
        worker_max_tasks_per_child=100,
        worker_prefetch_multiplier=1,
        # redis connection pool settings
        broker_transport_options={
            "visibility_timeout": 3600,  # 1 hour
            "socket_timeout": app.config.get("REDIS_SOCKET_TIMEOUT", 5),
            "socket_connect_timeout": app.config.get("REDIS_SOCKET_TIMEOUT", 5),
            "retry_on_timeout": True,
            "max_connections": app.config.get("REDIS_MAX_CONNECTIONS", 10),
        },
    )

    # Make celery aware of Flask app context
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    return app
