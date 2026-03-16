# delete_user.py
import os
from dotenv import load_dotenv

load_dotenv()

from src.providers.firebase_provider import FirebaseProvider

# Email of the account to delete
email_to_delete = "Test1234@gmail.com"  # Change to your email

print(f"🔍 Looking for user: {email_to_delete}")

db = FirebaseProvider()
users = db.query("users", {"email": email_to_delete})

if users and len(users) > 0:
    user = users[0]
    user_id = user.get("id")
    print(f"✅ Found user: {user_id}")

    # Delete the user
    db.delete("users", user_id)
    print(f"✅ Deleted user: {email_to_delete}")

    # Also delete any related data (videos, etc.)
    videos = db.query("videos", {"user_id": user_id})
    for video in videos:
        db.delete("videos", video.get("id"))
    print(f"✅ Deleted {len(videos)} related videos")
else:
    print(f"❌ User not found: {email_to_delete}")
