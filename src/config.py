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

# Print config status (helpful for debugging)
if FLASK_ENV == "development":
    print(f"🔧 Config loaded: FLASK_ENV={FLASK_ENV}")
    print(f"🔑 GOOGLE_API_KEY: {'✅ Found' if GOOGLE_API_KEY else '❌ Missing'}")
