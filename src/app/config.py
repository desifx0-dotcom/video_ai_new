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
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_ENV", "development") == "development"

    # Security
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # Uploads
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
    UPLOAD_FOLDER = Path("data/uploads").resolve()
    PROCESSING_FOLDER = Path("data/processing").resolve()
    OUTPUT_FOLDER = Path("data/outputs").resolve()

    # Ensure directories exist
    for folder in [UPLOAD_FOLDER, PROCESSING_FOLDER, OUTPUT_FOLDER]:
        folder.mkdir(parents=True, exist_ok=True)

    ALLOWED_EXTENSIONS = {
        "mp4",
        "avi",
        "mov",
        "mkv",
        "webm",
        "flv",
        "wmv",
        "mpeg",
        "mpg",
        "m4v",
        "3gp",
        "ogv",
    }

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # Redis Connection Settings
    REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", 5))
    REDIS_RETRY_ON_TIMEOUT = True
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", 10))

    # Database Provider
    DATABASE_PROVIDER = os.getenv("DATABASE_PROVIDER", "firebase")

    # Firebase
    FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

    # PostgreSQL (alternative)
    POSTGRES_URL = os.getenv("POSTGRES_URL")

    # AI Providers - Timeout Settings
    AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", 30))
    AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 3))
    AI_RETRY_DELAY = int(os.getenv("AI_RETRY_DELAY", 2))

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", AI_TIMEOUT))
    OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", AI_MAX_RETRIES))
    AI_RETRY_BACKOFF = int(
        os.getenv("AI_RETRY_BACKOFF", 2)
    )  # Exponential backoff factor

    # Google
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_TIMEOUT = int(os.getenv("GOOGLE_TIMEOUT", AI_TIMEOUT))
    GOOGLE_MAX_RETRIES = int(os.getenv("GOOGLE_MAX_RETRIES", AI_MAX_RETRIES))

    # Stability AI
    STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
    STABILITY_TIMEOUT = int(os.getenv("STABILITY_TIMEOUT", AI_TIMEOUT))
    STABILITY_MAX_RETRIES = int(os.getenv("STABILITY_MAX_RETRIES", AI_MAX_RETRIES))

    # Email Provider
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "sendgrid")
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")

    # Stripe
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

    # Feature Flags
    ENABLE_SILENT_DETECTION = (
        os.getenv("ENABLE_SILENT_DETECTION", "true").lower() == "true"
    )
    ENABLE_TRANSLATION = os.getenv("ENABLE_TRANSLATION", "true").lower() == "true"
    ENABLE_VIDEO_STYLES = os.getenv("ENABLE_VIDEO_STYLES", "true").lower() == "true"
    ENABLE_AI_THUMBNAILS = os.getenv("ENABLE_AI_THUMBNAILS", "true").lower() == "true"

    # Rate Limiting - Per Minute
    RATE_LIMIT_DEFAULT = "100 per hour"
    RATE_LIMIT_FREE = "10 per hour"
    RATE_LIMIT_STARTER = "50 per hour"
    RATE_LIMIT_PRO = "200 per hour"
    RATE_LIMIT_PLUS = "1000 per hour"
    RATE_LIMIT_ENTERPRISE = "10000 per hour"

    # Rate Limiting - Per Minute (for bursts)
    RATE_LIMIT_PER_MINUTE_FREE = 5
    RATE_LIMIT_PER_MINUTE_STARTER = 20
    RATE_LIMIT_PER_MINUTE_PRO = 50
    RATE_LIMIT_PER_MINUTE_PLUS = 100
    RATE_LIMIT_PER_MINUTE_ENTERPRISE = 500

    # WebSocket
    SOCKETIO_MESSAGE_QUEUE = REDIS_URL
    SOCKETIO_PING_TIMEOUT = int(os.getenv("SOCKETIO_PING_TIMEOUT", 60))
    SOCKETIO_PING_INTERVAL = int(os.getenv("SOCKETIO_PING_INTERVAL", 25))

    # Cache Settings
    CACHE_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", 3600))  # 1 hour
    CACHE_TRANSCRIPTION_TTL = int(
        os.getenv("CACHE_TRANSCRIPTION_TTL", 86400)
    )  # 24 hours
    CACHE_TRANSLATION_TTL = int(os.getenv("CACHE_TRANSLATION_TTL", 86400))  # 24 hours
    CACHE_THUMBNAIL_TTL = int(os.getenv("CACHE_THUMBNAIL_TTL", 604800))  # 7 days

    # Load settings from config files
    settings = load_settings()

    @classmethod
    def init_app(cls, app):
        """Initialize application with configuration."""
        # Set up logging level
        if cls.DEBUG:
            import logging

            logging.basicConfig(level=logging.DEBUG)


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    TESTING = True

    # Development-specific settings
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB for dev

    # Use local Redis
    REDIS_URL = "redis://localhost:6379/0"

    # Enable debug features
    SQLALCHEMY_ECHO = True

    # Development rate limits (higher for testing)
    RATE_LIMIT_FREE = "100 per hour"
    RATE_LIMIT_PER_MINUTE_FREE = 20

    # Cache shorter in development
    CACHE_DEFAULT_TTL = 300  # 5 minutes
    CACHE_TRANSCRIPTION_TTL = 3600  # 1 hour

    # Disable retries for faster testing
    AI_MAX_RETRIES = 1
    AI_RETRY_DELAY = 0


class TestingConfig(Config):
    """Testing configuration."""

    DEBUG = True
    TESTING = True

    # Use test database
    DATABASE_PROVIDER = "memory"

    # Disable external APIs
    OPENAI_API_KEY = "test-key"
    GOOGLE_API_KEY = "test-key"
    STABILITY_API_KEY = "test-key"

    # Fast processing for tests
    ENABLE_SILENT_DETECTION = False

    # Test Redis (use memory)
    REDIS_URL = "memory://"

    # Disable rate limiting in tests
    RATE_LIMIT_FREE = "10000 per hour"
    RATE_LIMIT_PER_MINUTE_FREE = 1000


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    TESTING = False

    # Security
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Production Redis with connection pool
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", 10))
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", 20))

    # Production storage - use /tmp or cloud storage
    UPLOAD_FOLDER = Path("/tmp/video_ai/uploads").resolve()
    PROCESSING_FOLDER = Path("/tmp/video_ai/processing").resolve()
    OUTPUT_FOLDER = Path("/tmp/video_ai/outputs").resolve()

    # Production retry settings
    AI_MAX_RETRIES = 3
    AI_RETRY_DELAY = 2
    AI_TIMEOUT = 60

    # Production rate limits
    RATE_LIMIT_FREE = "10 per hour"
    RATE_LIMIT_STARTER = "50 per hour"
    RATE_LIMIT_PRO = "200 per hour"
    RATE_LIMIT_PLUS = "1000 per hour"

    RATE_LIMIT_PER_MINUTE_FREE = 5
    RATE_LIMIT_PER_MINUTE_STARTER = 20
    RATE_LIMIT_PER_MINUTE_PRO = 50
    RATE_LIMIT_PER_MINUTE_PLUS = 100

    # Production cache TTLs
    CACHE_DEFAULT_TTL = 3600  # 1 hour
    CACHE_TRANSCRIPTION_TTL = 86400  # 24 hours
    CACHE_TRANSLATION_TTL = 86400  # 24 hours

    # Logging
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "json"


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
