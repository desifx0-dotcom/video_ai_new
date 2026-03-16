# fix_user_passwords.py
import os
from dotenv import load_dotenv

load_dotenv()

from src.providers.firebase_provider import FirebaseProvider
from src.core.security import SecurityUtils

print("🔧 Fixing user passwords...")

db = FirebaseProvider()

# Get all users
users = db.get_all("users")
print(f"Found {len(users)} users")

for user in users:
    user_id = user.get("id")
    email = user.get("email")

    print(f"\nChecking user: {email} ({user_id})")
    print(f"User keys: {list(user.keys())}")

    # Check if password field exists
    if "hashed_password" not in user:
        print(f"  ❌ No password field for {email}")

        # For test users, you might want to set a default password
        if email == "Test1234@gmail.com":
            # Set a default password (you should change this)
            default_password = "Test@1234"
            hashed = SecurityUtils.hash_password(default_password)

            # Update user
            user["hashed_password"] = hashed
            db.save("users", user_id, user)
            print(f"  ✅ Added password for {email}")
    else:
        print(f"  ✅ Password field exists: {user['hashed_password'][:20]}...")
