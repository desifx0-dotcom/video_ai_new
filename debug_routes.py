# debug_routes.py
import os
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv(verbose=True)
print("📋 Environment variables loaded:")
print(f"GOOGLE_API_KEY: {os.getenv('GOOTGLE_API_KEY', '❌ NOT FOUND')}")
print(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY', '❌ NOT FOUND')}")
print(f"FLASK_ENV: {os.getenv('FLASK_ENV', 'development')}")

# Now import the app
from src.main import app

print("\n✅ Routes registered in your app:")
print("=" * 60)
for rule in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
    methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
    print(f"  {rule.endpoint:30} {rule} [{methods}]")
print("=" * 60)

print(f"\n📊 Total routes: {len(list(app.url_map.iter_rules()))}")
