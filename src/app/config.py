"""
Flask configuration settings.
"""
import os
from pathlib import Path
from datetime import timedelta
from core.config.settings import load_settings

class Config:
    """Base configuration."""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_ENV', 'development') == 'development'
    
    # Security
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Uploads
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
    UPLOAD_FOLDER = Path('data/uploads').resolve()
    PROCESSING_FOLDER = Path('data/processing').resolve()
    OUTPUT_FOLDER = Path('data/outputs').resolve()
    
    # Ensure directories exist
    for folder in [UPLOAD_FOLDER, PROCESSING_FOLDER, OUTPUT_FOLDER]:
        folder.mkdir(parents=True, exist_ok=True)
    
    ALLOWED_EXTENSIONS = {
        'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'mpeg', 'mpg',
        'm4v', '3gp', 'ogv'
    }
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    
    # Database Provider
    DATABASE_PROVIDER = os.getenv('DATABASE_PROVIDER', 'firebase')
    
    # Firebase
    FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID')
    FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH')
    
    # PostgreSQL (alternative)
    POSTGRES_URL = os.getenv('POSTGRES_URL')
    
    # AI Providers
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    STABILITY_API_KEY = os.getenv('STABILITY_API_KEY')
    
    # Email Provider
    EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'sendgrid')
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    RESEND_API_KEY = os.getenv('RESEND_API_KEY')
    
    # Stripe
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
    
    # Feature Flags
    ENABLE_SILENT_DETECTION = os.getenv('ENABLE_SILENT_DETECTION', 'true').lower() == 'true'
    ENABLE_TRANSLATION = os.getenv('ENABLE_TRANSLATION', 'true').lower() == 'true'
    ENABLE_VIDEO_STYLES = os.getenv('ENABLE_VIDEO_STYLES', 'true').lower() == 'true'
    
    # Rate Limiting
    RATE_LIMIT_DEFAULT = "100 per hour"
    RATE_LIMIT_FREE = "10 per hour"
    RATE_LIMIT_STARTER = "50 per hour"
    RATE_LIMIT_PRO = "200 per hour"
    RATE_LIMIT_PLUS = "1000 per hour"
    
    # WebSocket
    SOCKETIO_MESSAGE_QUEUE = REDIS_URL
    
    # Load settings from config files
    settings = load_settings()
    
    @classmethod
    def init_app(cls, app):
        """Initialize application with configuration."""
        pass


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = True
    
    # Development-specific settings
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB for dev
    
    # Use local Redis
    REDIS_URL = 'redis://localhost:6379/0'
    
    # Enable debug features
    SQLALCHEMY_ECHO = True


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True
    
    # Use test database
    DATABASE_PROVIDER = 'memory'
    
    # Disable external APIs
    OPENAI_API_KEY = 'test-key'
    GOOGLE_API_KEY = 'test-key'
    
    # Fast processing for tests
    ENABLE_SILENT_DETECTION = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    
    # Security
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    
    # Production Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    
    # Production storage
    UPLOAD_FOLDER = Path('/tmp/video_ai/uploads').resolve()
    PROCESSING_FOLDER = Path('/tmp/video_ai/processing').resolve()
    OUTPUT_FOLDER = Path('/tmp/video_ai/outputs').resolve()


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}