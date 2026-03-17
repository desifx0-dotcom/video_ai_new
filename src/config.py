# config.py
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
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 500 * 1024 * 1024))
DEFAULT_QUALITY = os.getenv("DEFAULT_QUALITY", "720p")

# Print config status (helpful for debugging)
if FLASK_ENV == "development":
    print(f"🔧 Config loaded: FLASK_ENV={FLASK_ENV}")
    print(f"🔑 GOOGLE_API_KEY: {'✅ Found' if GOOGLE_API_KEY else '❌ Missing'}")
    print(f"📦 Database Provider: {DATABASE_PROVIDER}")
    print(f"📦 Redis Provider: {REDIS_PROVIDER}")
