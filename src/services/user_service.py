"""
User management service.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
import os
from core.domain.entities.user import User, Tier, UserStatus
from core.exceptions import ValidationError, NotFoundError, UnauthorizedError
from core.security import SecurityUtils
from core.validators import validators
from providers.firebase_provider import FirebaseProvider

logger = logging.getLogger(__name__)


class UserService:
    """User management service."""

    def __init__(self):
        """Initialize user service with Firebase provider."""
        try:
            # Always use Firebase provider - it works in both dev and prod
            from providers.firebase_provider import FirebaseProvider

            self.db = FirebaseProvider()
            print("✅ Using Firebase Provider")

            # For development, you might want to seed some test data
            if os.getenv("FLASK_ENV") == "development":
                self._ensure_test_user()

        except Exception as e:
            print(f"❌ Failed to initialize Firebase: {e}")
            raise

    def _ensure_test_user(self):
        """Ensure a test user exists in development."""
        try:
            # Check if test user exists
            test_email = "test@example.com"
            existing = self.get_user_by_email(test_email)

            if not existing:
                # Create test user
                from core.security import SecurityUtils

                test_user = {
                    "id": "user_123",
                    "email": test_email,
                    "hashed_password": SecurityUtils.hash_password("Test@1234"),
                    "tier": "free",
                    "full_name": "Test User",
                    "status": "active",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "email_verified": True,
                    "credits_remaining": 10,
                    "videos_processed_this_month": 0,
                    "monthly_video_limit": 3,
                    "settings": {},
                }
                self.db.save("users", "user_123", test_user)
                print("✅ Test user created: test@example.com / Test@1234")
        except Exception as e:
            print(f"⚠️  Could not create test user: {e}")

    def create_user(
        self,
        email: str,
        password: str,
        tier: str = "free",
        full_name: Optional[str] = None,
        is_admin: bool = False,
    ) -> User:
        """Create a new user."""
        # Validate email
        is_valid, error = validators.validate_email(email)
        if not is_valid:
            raise ValidationError(error, field="email")

        # Validate password
        is_valid, error = validators.validate_password(password)
        if not is_valid:
            raise ValidationError(error, field="password")

        # Validate tier
        is_valid, error = validators.validate_tier(tier)
        if not is_valid:
            raise ValidationError(error, field="tier")

        # Check if user already exists
        existing_users = self.db.query("users", filters={"email": email})
        if existing_users:
            raise ValidationError("User with this email already exists", field="email")

        # Generate user ID
        user_id = str(uuid.uuid4())

        # Hash password
        hashed_password = SecurityUtils.hash_password(password)

        # Determine monthly limit based on tier
        monthly_limits = {
            "free": 3,
            "starter": 50,
            "pro": 100,
            "plus": 250,
            "enterprise": 2000,
        }

        initial_credits = {
            "free": 3,  # Free tier gets 3 credits
            "starter": 50,  # Starter gets 50
            "pro": 100,  # Pro gets 100
            "plus": 250,  # Plus gets 500
            "enterprise": 2000,  # Enterprise gets 5000
        }.get(tier, 3)

        # Create user entity
        user = User(
            id=user_id,
            email=email,
            hashed_password=hashed_password,
            tier=Tier(tier),
            full_name=full_name,
            monthly_video_limit=monthly_limits.get(tier, 3),
            is_admin=is_admin,
            settings={
                "language": "en",
                "timezone": "UTC",
                "email_notifications": True,
                "push_notifications": True,
                "auto_translate": False,
                "default_quality": "720p",
                "default_style": "cinematic",
                "retention_days": 1,
            },
        )

        # Manually ensure password is in the saved data
        user_dict = user.to_dict()
        # Explicitly add password field if it's missing
        if "hashed_password" not in user_dict:
            user_dict["hashed_password"] = hashed_password
        # Save to database
        self.db.save("users", user_id, user.to_dict())

        logger.info(f"Created user: {email} ({tier})")

        return user

    def authenticate_user(self, email, password):
        """Authenticate a user by email and password."""
        try:
            print(f"Authenticating user: {email}")

            # Get user by email
            user = self.get_user_by_email(email)
            if not user:
                print(f"User not found: {email}")
                return None

            print(f"User found: {user.id}")

            # Get password hash from user object
            stored_hash = getattr(user, "hashed_password", None)
            if not stored_hash:
                print("No password hash found in user object")
                return None

            print(f"Stored hash found: {stored_hash[:20]}...")

            # Verify password
            from core.security import SecurityUtils

            if SecurityUtils.verify_password(password, stored_hash):
                print("Password verified successfully")
                return user
            else:
                print("Password verification failed")
                return None

        except Exception as e:
            print(f"Authentication error: {e}")
            import traceback

            traceback.print_exc()
            return None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        user_data = self.db.get("users", user_id)
        if not user_data:
            return None

        return self._dict_to_user(user_data)

    def get_user_by_email(self, email):
        """Get user by email."""
        try:
            print(f"Looking up user by email: {email}")

            # Query Firebase
            users = self.db.query("users", {"email": email})

            if users and len(users) > 0:
                user_data = users[0]
                print(f"User found: {user_data.get('id')}")
                print(f"User data keys: {list(user_data.keys())}")

                # ✅ FIX: Use the existing _dict_to_user method
                return self._dict_to_user(user_data)

            print("User not found")
            return None

        except Exception as e:
            print(f"Error in get_user_by_email: {e}")
            import traceback

            traceback.print_exc()
            return None

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
        """Update user information."""
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # Apply updates
        for key, value in updates.items():
            if hasattr(user, key) and key not in [
                "id",
                "created_at",
                "hashed_password",
            ]:
                setattr(user, key, value)

        user.updated_at = datetime.utcnow()

        # Save to database
        self.db.save("users", user_id, user.to_dict())

        return user

    def update_user_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> bool:
        """Update user password."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        # Verify current password
        if not SecurityUtils.verify_password(current_password, user.hashed_password):
            return False

        # Validate new password
        is_valid, error = validators.validate_password(new_password)
        if not is_valid:
            raise ValidationError(error, field="new_password")

        # Update password
        user.hashed_password = SecurityUtils.hash_password(new_password)
        user.updated_at = datetime.utcnow()

        self.db.save("users", user_id, user.to_dict())

        return True

    def reset_password(self, email: str, token: str, new_password: str) -> bool:
        """Reset user password with token."""
        # Validate new password
        is_valid, error = validators.validate_password(new_password)
        if not is_valid:
            raise ValidationError(error, field="new_password")

        # Get user
        user = self.get_user_by_email(email)
        if not user:
            return False

        # TODO: Validate reset token (would be stored in database)
        # For now, just update password

        user.hashed_password = SecurityUtils.hash_password(new_password)
        user.updated_at = datetime.utcnow()

        self.db.save("users", user.id, user.to_dict())

        return True

    def update_tier(self, user_id: str, new_tier: str) -> Optional[User]:
        """Update user tier."""
        # Validate tier
        is_valid, error = validators.validate_tier(new_tier)
        if not is_valid:
            raise ValidationError(error, field="tier")

        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # Update tier
        user.tier = Tier(new_tier)

        # Update monthly limit based on new tier
        monthly_limits = {
            "free": 3,
            "starter": 50,
            "pro": 100,
            "plus": 500,
            "enterprise": 5000,
        }
        user.monthly_video_limit = monthly_limits.get(new_tier, 3)

        user.updated_at = datetime.utcnow()

        # Save to database
        self.db.save("users", user_id, user.to_dict())

        # Record tier upgrade event
        from app.monitoring.metrics import record_tier_upgrade

        record_tier_upgrade(
            from_tier=user.tier.value, to_tier=new_tier, user_id=user_id
        )

        return user

    def add_credits(self, user_id: str, amount: int, description: str = "") -> bool:
        """Add credits to user account."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        user.credits_remaining += amount
        user.updated_at = datetime.utcnow()

        self.db.save("users", user_id, user.to_dict())

        # Record credit transaction
        transaction_id = str(uuid.uuid4())
        transaction = {
            "id": transaction_id,
            "user_id": user_id,
            "amount": amount,
            "description": description,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.db.save("credit_transactions", transaction_id, transaction)

        return True

    def use_credits(self, user_id: str, amount: int, description: str = "") -> bool:
        """Use credits from user account."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        if user.credits_remaining < amount:
            return False

        user.credits_remaining -= amount
        user.updated_at = datetime.utcnow()

        self.db.save("users", user_id, user.to_dict())

        # Record credit transaction
        transaction_id = str(uuid.uuid4())
        transaction = {
            "id": transaction_id,
            "user_id": user_id,
            "amount": -amount,
            "description": description,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.db.save("credit_transactions", transaction_id, transaction)

        return True

    def record_video_processing(
        self, user_id: str, video_duration: float, cost: float
    ) -> bool:
        """Record video processing for user."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        user.videos_processed_this_month += 1
        user.total_videos_processed += 1
        user.total_processing_time += video_duration

        # Deduct credits for non-unlimited tiers
        if user.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            credits_needed = max(1, int(video_duration) // 60)
            user.credits_remaining = max(0, user.credits_remaining - credits_needed)

        user.updated_at = datetime.utcnow()

        self.db.save("users", user_id, user.to_dict())

        return True

    def reset_monthly_usage(self):
        """Reset monthly usage for all users (to be called monthly)."""
        users = self.db.get_all("users")

        for user_data in users:
            user = self._dict_to_user(user_data)
            user.videos_processed_this_month = 0
            user.updated_at = datetime.utcnow()

            self.db.save("users", user.id, user.to_dict())

    def delete_user(self, user_id: str) -> bool:
        """Delete user (soft delete)."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        # Mark as inactive
        user.status = UserStatus.INACTIVE
        user.updated_at = datetime.utcnow()

        self.db.save("users", user_id, user.to_dict())

        return True

    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """Get all users."""
        users_data = self.db.get_all("users", limit=limit, offset=offset)
        return [self._dict_to_user(data) for data in users_data]

    def get_active_users_count(self) -> int:
        """Get count of active users."""
        active_users = self.db.query("users", filters={"status": "active"})
        return len(active_users)

    def get_users_by_tier(self, tier: str) -> List[User]:
        """Get users by tier."""
        users_data = self.db.query("users", filters={"tier": tier, "status": "active"})
        return [self._dict_to_user(data) for data in users_data]

    def _dict_to_user(self, data: Dict[str, Any]) -> User:
        """Convert dictionary to User entity."""

        # Parse datetime fields safely
        def parse_datetime(value):
            if not value:
                return None
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except:
                    return None
            return value

        return User(
            id=data["id"],
            email=data["email"],
            hashed_password=data["hashed_password"],
            tier=Tier(data.get("tier", "free")),
            status=UserStatus(data.get("status", "active")),
            full_name=data.get("full_name"),
            avatar_url=data.get("avatar_url"),
            language=data.get("language", "en"),
            timezone=data.get("timezone", "UTC"),
            credits_remaining=data.get("credits_remaining", 0),
            videos_processed_this_month=data.get("videos_processed_this_month", 0),
            monthly_video_limit=data.get("monthly_video_limit", 3),
            total_videos_processed=data.get("total_videos_processed", 0),
            total_processing_time=data.get("total_processing_time", 0.0),
            stripe_customer_id=data.get("stripe_customer_id"),
            stripe_subscription_id=data.get("stripe_subscription_id"),
            subscription_start_date=parse_datetime(data.get("subscription_start_date")),
            subscription_end_date=parse_datetime(data.get("subscription_end_date")),
            subscription_cancel_at_period_end=data.get(
                "subscription_cancel_at_period_end", False
            ),
            settings=data.get("settings", {}),
            created_at=parse_datetime(data.get("created_at")) or datetime.utcnow(),
            updated_at=parse_datetime(data.get("updated_at"))
            or datetime.utcnow(),  # Safe now!
            last_login=parse_datetime(data.get("last_login")),
            email_verified_at=parse_datetime(data.get("email_verified_at")),
            is_admin=data.get("is_admin", False),
            permissions=data.get("permissions", []),
        )
