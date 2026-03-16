"""
Testing configuration.
"""
import os
from .settings import Config

class TestingConfig(Config):
    """Testing configuration."""
    
    DEBUG = True
    TESTING = True
    
    # Database
    DATABASE_PROVIDER = 'memory'  # Use in-memory database for tests
    
    # Security
    SECRET_KEY = 'test-secret-key'
    
    # File uploads
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB for tests
    UPLOAD_FOLDER = 'tests/test_uploads'
    
    # Redis
    REDIS_URL = 'redis://localhost:6379/1'  # Use different DB for tests
    
    # CORS
    CORS_ORIGINS = ['http://test.local']
    
    # Feature flags
    ENABLE_SILENT_DETECTION = False
    ENABLE_TRANSLATION = False
    ENABLE_VIDEO_STYLES = False
    
    # Email
    EMAIL_PROVIDER = 'mock'  # Mock email for tests
    
    # Disable external APIs
    OPENAI_API_KEY = 'test-key'
    GOOGLE_API_KEY = 'test-key'
    STABILITY_API_KEY = 'test-key'
    
    # Disable monitoring
    ENABLE_TRACING = False
    
    @classmethod
    def init_app(cls, app):
        """Initialize testing app."""
        Config.init_app(app)
        
        # Create test directories
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs('tests/test_processing', exist_ok=True)
        os.makedirs('tests/test_outputs', exist_ok=True)