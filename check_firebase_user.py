# check_firebase_user.py
import os
from dotenv import load_dotenv

load_dotenv()

from src.providers.firebase_provider import FirebaseProvider
from src.services.user_service import UserService

print("🔍 Checking Firebase user data...")
print("=" * 50)

# Initialize Firebase
db = FirebaseProvider()
print(f"✅ Firebase initialized: {db.test_connection()}")

# Check if user exists
email = "Test1234@gmail.com"  # Your test email
print(f"\n📧 Looking up user: {email}")

# Try different query approaches
print("\n1. Query by email (simple):")
users = db.query("users", {"email": email})
if users:
    print(f"✅ Found {len(users)} user(s)")
    for i, user in enumerate(users):
        print(f"\n   User {i+1}:")
        print(f"   - ID: {user.get('id')}")
        print(f"   - Email: {user.get('email')}")
        print(
            f"   - Password field keys: {[k for k in user.keys() if 'password' in k.lower()]}"
        )

        # Check all possible password field names
        password_fields = ["password_hash", "hashed_password", "password", "hash"]
        for field in password_fields:
            if field in user:
                print(f"   - {field}: {user[field][:30]}...")
                break
        else:
            print("   - ❌ No password field found!")

        # Show all user fields
        print(f"   - All fields: {list(user.keys())}")
else:
    print(f"❌ No user found with email: {email}")

print("\n" + "=" * 50)

# Try to authenticate directly
print("\n🔐 Testing authentication directly:")
from src.core.security import SecurityUtils
from src.services.user_service import UserService

user_service = UserService()
user = user_service.get_user_by_email(email)

if user:
    print(f"✅ User object from get_user_by_email: {type(user)}")

    # Check if it's a dict or object
    if isinstance(user, dict):
        print("   User is a dictionary")
        print(f"   Keys: {list(user.keys())}")
        password_field = user.get("password_hash") or user.get("hashed_password")
        if password_field:
            print(f"   Password field found: {password_field[:30]}...")
        else:
            print("   ❌ No password field in dict!")
    else:
        print(f"   User is an object with attributes: {dir(user)}")
        password_field = getattr(user, "password_hash", None) or getattr(
            user, "hashed_password", None
        )
        if password_field:
            print(f"   Password field found: {password_field[:30]}...")
        else:
            print("   ❌ No password field in object!")

    # Try authentication
    auth_result = user_service.authenticate_user(email, "Test@1234")
    if auth_result:
        print(f"✅ Authentication successful!")
    else:
        print(f"❌ Authentication failed!")
else:
    print(f"❌ Could not retrieve user via get_user_by_email")
