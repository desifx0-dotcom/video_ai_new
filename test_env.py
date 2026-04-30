# test_env.py
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path("D:/video_ai_new/.env")
print(f"Looking for .env at: {env_path}")
print(f"File exists: {env_path.exists()}")

load_dotenv(dotenv_path=env_path)

redis_url = os.getenv("REDIS_URL")
print(f"REDIS_URL: {redis_url}")
print(f"Type: {type(redis_url)}")
print(f'Is memory? {redis_url == "memory://"}')
print(f"Is None? {redis_url is None}")

# Also check all Redis-related env vars
print("\nAll Redis-related env vars:")
for key in os.environ:
    if "REDIS" in key or "CELERY" in key:
        print(f"  {key}: {os.environ[key]}")
