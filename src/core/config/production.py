"""
Production configuration.
"""
import os
from .settings import Config

class ProductionConfig(Config):
    """Production configuration."""
    
    DEBUG = False
    TESTING = False
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY')
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    
    # Database
    DATABASE_PROVIDER = os.getenv('DATABASE_PROVIDER', 'firebase')
    
    # File uploads
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
    UPLOAD_FOLDER = '/tmp/video_ai/uploads'
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    
    # CORS
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '').split(',')
    
    # Feature flags
    ENABLE_SILENT_DETECTION = os.getenv('ENABLE_SILENT_DETECTION', 'true').lower() == 'true'
    ENABLE_TRANSLATION = os.getenv('ENABLE_TRANSLATION', 'true').lower() == 'true'
    ENABLE_VIDEO_STYLES = os.getenv('ENABLE_VIDEO_STYLES', 'true').lower() == 'true'
    
    # Email
    EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'sendgrid')
    
    # Monitoring
    ENABLE_TRACING = os.getenv('ENABLE_TRACING', 'false').lower() == 'true'
    OTLP_ENDPOINT = os.getenv('OTLP_ENDPOINT')
    
    # Rate limiting
    RATE_LIMIT_DEFAULT = "100 per hour"
    RATE_LIMIT_FREE = "10 per hour"
    RATE_LIMIT_STARTER = "50 per hour"
    RATE_LIMIT_PRO = "200 per hour"
    RATE_LIMIT_PLUS = "1000 per hour"
    
    @classmethod
    def init_app(cls, app):
        """Initialize production app."""
        Config.init_app(app)
        
        # Production logging
        import logging
        from logging.handlers import RotatingFileHandler
        
        # Create logs directory
        os.makedirs('logs', exist_ok=True)
        
        # File handler
        file_handler = RotatingFileHandler(
            'logs/video_ai_studio.log',
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.WARNING)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        file_handler.setFormatter(formatter)
        
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.WARNING)
        
        # Create upload directories
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs('/tmp/video_ai/processing', exist_ok=True)
        os.makedirs('/tmp/video_ai/outputs', exist_ok=True)