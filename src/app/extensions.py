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
    
    # Celery
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=30 * 60,  # 30 minutes
        task_soft_time_limit=25 * 60,  # 25 minutes
        worker_max_tasks_per_child=100,
        worker_prefetch_multiplier=1,
    )
    
    # Make celery aware of Flask app context
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    
    return app