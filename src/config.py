# config.py - PRODUCTION VERSION with timeout and chunk settings
"""Configuration module - loads environment variables once at import time."""
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")

# App configuration
FLASK_ENV = os.getenv("FLASK_ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)

# Database Configuration
DATABASE_PROVIDER = os.getenv("DATABASE_PROVIDER", "firebase")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# Redis Configuration
REDIS_PROVIDER = os.getenv("REDIS_PROVIDER", "mock")
REDIS_URL = os.getenv("REDIS_URL", "mock://")
SOCKETIO_MESSAGE_QUEUE = os.getenv("SOCKETIO_MESSAGE_QUEUE", "")

# Application URLs
APP_URL = os.getenv("APP_URL", "http://localhost:5000")
API_URL = os.getenv("API_URL", "http://localhost:5000/api/v1")

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5000").split(",")

# Video Processing
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 2 * 1024 * 1024 * 1024))  # 2GB for video upload and processing
DEFAULT_QUALITY = os.getenv("DEFAULT_QUALITY", "720p")

# ========== PRODUCTION: Upload Streaming Configuration ==========
UPLOAD_CHUNK_SIZE = int(os.getenv("UPLOAD_CHUNK_SIZE", 8192))  # 8KB chunks
UPLOAD_TIMEOUT = int(os.getenv("UPLOAD_TIMEOUT", 300))  # 5 minutes timeout
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 300))  # 5 minutes

# Flask server settings (for production)
if FLASK_ENV == "production":
    # These settings help with large file uploads
    os.environ["FLASK_RUN_EXTRA_FILES"] = ""  # Disable file watching
    os.environ["WERKZEUG_RUN_MAIN"] = "true"  # Disable reloader

# Tier-based upload limits (MB)
TIER_UPLOAD_LIMITS = {
    "free": 100,      # 100MB
    "starter": 500,   # 500MB
    "pro": 1024,      # 1GB
    "plus": 2048,     # 2GB
    "enterprise": 5120, # 5GB
}

# Print config status (helpful for debugging)
if FLASK_ENV == "development":
    print(f"🔧 Config loaded: FLASK_ENV={FLASK_ENV}")
    print(f"🔑 GOOGLE_API_KEY: {'✅ Found' if GOOGLE_API_KEY else '❌ Missing'}")
    print(f"📦 Database Provider: {DATABASE_PROVIDER}")
    print(f"📦 Redis Provider: {REDIS_PROVIDER}")
    print(f"📤 Upload chunk size: {UPLOAD_CHUNK_SIZE} bytes")
    print(f"⏱️  Upload timeout: {UPLOAD_TIMEOUT} seconds")