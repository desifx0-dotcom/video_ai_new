"""
Development configuration.
"""
import os
from .settings import Config

class DevelopmentConfig(Config):
    """Development configuration."""
    
    DEBUG = True
    TESTING = False
    
    # Database
    DATABASE_PROVIDER = 'firebase'
    
    # Security
    SECRET_KEY = 'dev-secret-key-change-in-production'
    
    # File uploads
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
    UPLOAD_FOLDER = 'data/uploads'
    
    # Redis
    REDIS_URL = 'redis://localhost:6379/0'
    
    # CORS
    CORS_ORIGINS = ['http://localhost:3000', 'http://localhost:5000']
    
    # Feature flags
    ENABLE_SILENT_DETECTION = True
    ENABLE_TRANSLATION = True
    ENABLE_VIDEO_STYLES = True
    
    # Email
    EMAIL_PROVIDER = 'console'  # Print emails to console in dev
    
    # Monitoring
    ENABLE_TRACING = False
    
    @classmethod
    def init_app(cls, app):
        """Initialize development app."""
        Config.init_app(app)
        
        # Development-specific middleware
        from flask_debugtoolbar import DebugToolbarExtension
        toolbar = DebugToolbarExtension()
        toolbar.init_app(app)
        
        # Log to console
        import logging
        logging.basicConfig(level=logging.DEBUG)
        
        # Create upload directories
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs('data/processing', exist_ok=True)
        os.makedirs('data/outputs', exist_ok=True)