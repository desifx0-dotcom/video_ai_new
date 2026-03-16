"""
User management router for API v1.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
import datetime
from flask import g
from core.exceptions import ValidationError, UnauthorizedError, ForbiddenError
from api.dependencies import (
    validate_request,
    paginate,
    require_tier,
    track_analytics,
    require_permission,
)
from api.schemas.user import (
    UserResponseSchema,
    UserUpdateSchema,
    UserStatsSchema,
    UserListSchema,
    UserSearchSchema,
    UserActivitySchema,
    UserPreferencesSchema,
    UserExportSchema,
    ChangePasswordSchema,
)
from services.user_service import UserService

#     get_user_by_id, update_user_profile, get_user_stats,
#     search_users, get_user_activity, update_user_preferences,
#     export_user_data
# )
user_service = UserService()


from services.tier_service import TierService
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

router = Blueprint("users", __name__)
logger = logging.getLogger(__name__)

# Create a limiter for this blueprint
limiter = Limiter(key_func=get_remote_address)

tier_service = TierService()


def get_current_user_id():
    """Get current user ID from JWT or session."""
    # Try JWT first
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            return user_id
    except:
        pass

    # Try session
    from flask import session

    user_id = session.get("user_id")
    if user_id:
        return user_id

    return None


@router.route("/profile", methods=["GET"])
# Remove @jwt_required() - using session middleware
def get_user_profile():
    """Get current user profile."""
    from flask import session, g

    # Get user_id from session (set by middleware)
    user_id = session.get("user_id") or g.get("user_id")

    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        user = user_service.get_user_by_id(user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Convert user to dict for response
        user_dict = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "tier": user.tier.value if hasattr(user.tier, "value") else user.tier,
            "avatar_url": user.avatar_url,
            "language": user.language,
            "timezone": user.timezone,
            "credits_remaining": user.credits_remaining,
            "videos_processed_this_month": user.videos_processed_this_month,
            "monthly_video_limit": user.monthly_video_limit,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

        return jsonify(user_dict), 200

    except Exception as e:
        logger.error(f"Get user profile failed: {str(e)}")
        return jsonify({"error": str(e)}), 500


@router.route("/profile", methods=["PUT"])
@jwt_required()
@validate_request(UserUpdateSchema)
@track_analytics("user.profile_update")
def update_user_profile_route():
    """Update current user profile."""
    user_id = get_current_user_id()
    data = request.validated_data

    try:
        user = user_service.update_user_profile(user_id, data)

        response_schema = UserResponseSchema()
        return jsonify(response_schema.dump(user.to_dict())), 200

    except Exception as e:
        logger.error(f"Update user profile failed: {str(e)}")
        raise


@router.route("/stats", methods=["GET"])
@jwt_required()
def get_user_stats_route():
    """Get user statistics."""
    user_id = get_current_user_id()

    try:
        stats = user_service.get_user_stats(user_id)

        response_schema = UserStatsSchema()
        return jsonify(response_schema.dump(stats)), 200

    except Exception as e:
        logger.error(f"Get user stats failed: {str(e)}")
        raise


@router.route("/activity", methods=["GET"])
@jwt_required()
def get_user_activity_route():
    """Get user activity."""
    user_id = get_current_user_id()

    try:
        activity = user_service.get_user_activity(user_id)

        response_schema = UserActivitySchema()
        return jsonify(response_schema.dump(activity)), 200

    except Exception as e:
        logger.error(f"Get user activity failed: {str(e)}")
        raise


@router.route("/preferences", methods=["GET"])
@jwt_required()
def get_user_preferences():
    """Get user preferences."""
    user_id = get_current_user_id()

    try:
        user = user_service.get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        response_schema = UserPreferencesSchema()
        return jsonify(response_schema.dump(user.settings)), 200

    except Exception as e:
        logger.error(f"Get user preferences failed: {str(e)}")
        raise


@router.route("/preferences", methods=["PUT"])
@jwt_required()
@validate_request(UserPreferencesSchema)
@track_analytics("user.preferences_update")
def update_user_preferences_route():
    """Update user preferences."""
    user_id = get_current_user_id()
    data = request.validated_data

    try:
        user = user_service.update_user_preferences(user_id, data)

        response_schema = UserPreferencesSchema()
        return jsonify(response_schema.dump(user.settings)), 200

    except Exception as e:
        logger.error(f"Update user preferences failed: {str(e)}")
        raise


@router.route("/password", methods=["PUT"])
@jwt_required()
@validate_request(ChangePasswordSchema)
def update_password():
    """Update user password."""
    user_id = get_current_user_id()
    data = request.validated_data

    try:
        success = user_service.update_user_password(
            user_id=user_id,
            current_password=data["current_password"],
            new_password=data["new_password"],
        )

        if success:
            # Optional: Invalidate other sessions
            # from providers.redis_provider import RedisProvider
            # redis = RedisProvider()
            # redis.delete(f"user_sessions:{user_id}")

            return (
                jsonify({"success": True, "message": "Password updated successfully"}),
                200,
            )
        else:
            return (
                jsonify({"success": False, "message": "Current password is incorrect"}),
                401,
            )

    except ValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Password update failed: {str(e)}")
        return jsonify({"success": False, "message": "An error occurred"}), 500


@router.route("/tier", methods=["GET"])
@jwt_required()
def get_user_tier():
    """Get user tier information."""
    user_id = get_current_user_id()

    try:
        user = user_service.get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        tier_info = tier_service.get_tier_info(user.tier)

        return (
            jsonify(
                {
                    "tier": user.tier.value,
                    "info": tier_info.to_dict(),
                    "limits": {
                        "videos_processed_this_month": user.videos_processed_this_month,
                        "monthly_video_limit": user.monthly_video_limit,
                        "credits_remaining": user.credits_remaining,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get user tier failed: {str(e)}")
        raise


@router.route("/tier/upgrade", methods=["POST"])
@jwt_required()
@track_analytics("user.tier_upgrade_request")
def request_tier_upgrade():
    """Request tier upgrade."""
    user_id = get_current_user_id()

    try:
        # This would typically integrate with a payment system
        # For now, just return upgrade options
        user = user_service.get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        # Get available upgrade options
        upgrade_options = tier_service.get_upgrade_options(user.tier)

        return (
            jsonify(
                {
                    "current_tier": user.tier.value,
                    "upgrade_options": upgrade_options,
                    "message": "Please visit /api/v1/billing/upgrade to complete the upgrade",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Request tier upgrade failed: {str(e)}")
        raise


@router.route("/export", methods=["POST"])
@jwt_required()
@validate_request(UserExportSchema)
def export_user_data_route():
    """Export user data."""
    user_id = get_current_user_id()
    data = request.validated_data

    try:
        export_result = user_service.export_user_data(user_id, data)

        return (
            jsonify(
                {
                    "success": True,
                    "data": export_result,
                    "message": "Data export completed successfully",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Export user data failed: {str(e)}")
        raise


@router.route("/credits", methods=["GET"])
@jwt_required()
def get_user_credits():
    """Get user credit information."""
    user_id = get_current_user_id()

    try:
        user = user_service.get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        # Get credit transactions
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        transactions = db.query(
            "credit_transactions",
            filters={"user_id": user_id},
            order_by="created_at",
            descending=True,
            limit=10,
        )

        return (
            jsonify(
                {
                    "credits_remaining": user.credits_remaining,
                    "transactions": transactions,
                    "credit_value": 1.00,  # $1 per credit
                    "next_reset_date": None,  # Would be calculated based on billing cycle
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get user credits failed: {str(e)}")
        raise


@router.route("/credits/purchase", methods=["POST"])
@jwt_required()
@require_tier("free")  # Only free tier users need to purchase credits
@track_analytics("user.credit_purchase")
def purchase_credits():
    """Purchase additional credits."""
    user_id = get_current_user_id()

    try:
        data = request.json
        credit_amount = data.get("amount", 10)

        if credit_amount < 1:
            raise ValidationError("Amount must be at least 1", field="amount")

        if credit_amount > 1000:
            raise ValidationError(
                "Maximum purchase amount is 1000 credits", field="amount"
            )

        # Calculate cost
        cost = credit_amount * 1.00  # $1 per credit

        # This would integrate with a payment gateway
        # For now, simulate successful purchase
        from services.credit_service import CreditService

        credit_service = CreditService()

        transaction = credit_service.add_credits(
            user_id=user_id,
            amount=credit_amount,
            description=f"Credit purchase: {credit_amount} credits",
            payment_method="simulated",
        )

        return (
            jsonify(
                {
                    "success": True,
                    "transaction": transaction,
                    "new_balance": transaction["new_balance"],
                    "message": f"Successfully purchased {credit_amount} credits",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Purchase credits failed: {str(e)}")
        raise


# Admin endpoints (require admin permissions)
@router.route("/admin/users", methods=["GET"])
@jwt_required()
@require_permission("admin:users:read")
@paginate(default_per_page=50, max_per_page=200)
def admin_list_users():
    """Admin: List all users."""
    try:
        # Get filters
        tier = request.args.get("tier")
        status = request.args.get("status")
        search = request.args.get("search")

        filters = {}
        if tier:
            filters["tier"] = tier
        if status:
            filters["is_active"] = status == "active"

        users_data = user_service.search_users(
            query=search,
            filters=filters,
            page=request.pagination["page"],
            per_page=request.pagination["per_page"],
        )

        response_schema = UserListSchema()
        return jsonify(response_schema.dump(users_data)), 200

    except Exception as e:
        logger.error(f"Admin list users failed: {str(e)}")
        raise


@router.route("/admin/users/<target_user_id>", methods=["GET"])
@jwt_required()
@require_permission("admin:users:read")
def admin_get_user(target_user_id):
    """Admin: Get user details."""
    try:
        user = user_service.get_user_by_id(target_user_id)

        if not user:
            raise ValidationError("User not found", field="user_id")

        # Get additional admin data
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        videos = db.query("videos", filters={"user_id": target_user_id}, limit=10)

        subscriptions = db.query("subscriptions", filters={"user_id": target_user_id})

        response_schema = UserResponseSchema()
        return (
            jsonify(
                {
                    "user": response_schema.dump(user.to_dict()),
                    "recent_videos": videos,
                    "subscriptions": subscriptions,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Admin get user failed: {str(e)}")
        raise


@router.route("/admin/users/<target_user_id>", methods=["PUT"])
@jwt_required()
@require_permission("admin:users:write")
@validate_request(UserUpdateSchema)
def admin_update_user(target_user_id):
    """Admin: Update user."""
    data = request.validated_data

    try:
        user = user_service.get_user_by_id(target_user_id)

        if not user:
            raise ValidationError("User not found", field="user_id")

        # Update user (admin can update more fields)
        if "tier" in data:
            from services.user_service import update_user_tier

            user = update_user_tier(target_user_id, data["tier"])

        if "is_active" in data:
            from services.user_service import update_user_status

            user = update_user_status(target_user_id, data["is_active"])

        # Update profile fields
        profile_data = {k: v for k, v in data.items() if k not in ["tier", "is_active"]}
        if profile_data:
            user = user_service.update_user_profile(target_user_id, profile_data)

        response_schema = UserResponseSchema()
        return jsonify(response_schema.dump(user.to_dict())), 200

    except Exception as e:
        logger.error(f"Admin update user failed: {str(e)}")
        raise


@router.route("/admin/users/<target_user_id>/credits", methods=["POST"])
@jwt_required()
@require_permission("admin:users:write")
def admin_add_credits(target_user_id):
    """Admin: Add credits to user account."""
    try:
        data = request.json
        amount = data.get("amount", 0)
        reason = data.get("reason", "Administrative adjustment")

        if amount == 0:
            raise ValidationError("Amount cannot be zero", field="amount")

        from services.credit_service import CreditService

        credit_service = CreditService()

        transaction = credit_service.add_credits(
            user_id=target_user_id,
            amount=amount,
            description=f"Admin adjustment: {reason}",
            payment_method="admin",
        )

        # Get updated user
        user = user_service.get_user_by_id(target_user_id)

        return (
            jsonify(
                {
                    "success": True,
                    "transaction": transaction,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "credits_remaining": user.credits_remaining,
                    },
                    "message": f"Added {amount} credits to user account",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Admin add credits failed: {str(e)}")
        raise


@router.route("/admin/stats", methods=["GET"])
@jwt_required()
@require_permission("admin:analytics:read")
def admin_system_stats():
    """Admin: Get system statistics."""
    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        # Get counts
        total_users = db.count("users")
        active_users = db.count("users", {"is_active": True})
        total_videos = db.count("videos")
        completed_videos = db.count("videos", {"status": "completed"})

        # Get tier distribution
        tiers = ["free", "starter", "pro", "plus", "enterprise"]
        tier_distribution = {}

        for tier in tiers:
            count = db.count("users", {"tier": tier})
            tier_distribution[tier] = count

        # Get recent activity
        recent_videos = db.query(
            "videos", order_by="created_at", descending=True, limit=10
        )

        # Get revenue estimate (simulated)
        revenue_estimate = {
            "monthly": tier_distribution["starter"] * 24
            + tier_distribution["pro"] * 79
            + tier_distribution["plus"] * 250
            + tier_distribution["enterprise"] * 999,
            "yearly": 0,  # Would calculate based on actual subscriptions
        }

        return (
            jsonify(
                {
                    "users": {
                        "total": total_users,
                        "active": active_users,
                        "tier_distribution": tier_distribution,
                    },
                    "videos": {
                        "total": total_videos,
                        "completed": completed_videos,
                        "processing": db.count("videos", {"status": "processing"}),
                        "failed": db.count("videos", {"status": "failed"}),
                    },
                    "revenue": revenue_estimate,
                    "recent_activity": {
                        "videos": recent_videos,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Admin system stats failed: {str(e)}")
        raise


@router.route("/sessions", methods=["GET"])
@jwt_required()
def get_sessions():
    """Get active user sessions."""
    user_id = get_current_user_id()

    try:
        # Get sessions from wherever you store them (Redis/Firebase)
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()

        sessions_key = f"user_sessions:{user_id}"
        sessions = redis.get(sessions_key) or []

        # Mark current session
        current_session_id = request.cookies.get("session_id")
        for session in sessions:
            session["current"] = session["id"] == current_session_id

        return jsonify({"sessions": sessions}), 200

    except Exception as e:
        logger.error(f"Get sessions failed: {str(e)}")
        return jsonify({"sessions": []}), 200


@router.route("/sessions/<session_id>", methods=["DELETE"])
@jwt_required()
def logout_session(session_id):
    """Logout a specific session."""
    user_id = get_current_user_id()

    try:
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()

        sessions_key = f"user_sessions:{user_id}"
        sessions = redis.get(sessions_key) or []

        # Remove session
        sessions = [s for s in sessions if s["id"] != session_id]
        redis.set(sessions_key, sessions)

        # If this is a JWT session, add to blacklist
        from flask_jwt_extended import decode_token
        from flask import current_app

        # Blacklist the token
        from app.extensions import jwt_redis_blocklist

        jwt_redis_blocklist.set(session_id, "revoked")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Logout session failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/sessions", methods=["DELETE"])
@jwt_required()
def logout_all_sessions():
    """Logout all sessions except current."""
    user_id = get_current_user_id()

    try:
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()

        current_session_id = request.cookies.get("session_id")
        sessions_key = f"user_sessions:{user_id}"
        sessions = redis.get(sessions_key) or []

        # Keep only current session
        sessions = [s for s in sessions if s["id"] == current_session_id]
        redis.set(sessions_key, sessions)

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Logout all sessions failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/api-keys", methods=["GET"])
@jwt_required()
def get_api_keys():
    """Get user API keys."""
    user_id = get_current_user_id()

    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        keys = db.query("api_keys", filters={"user_id": user_id})

        # Remove actual key for security, show only prefix
        for key in keys:
            key["key_prefix"] = key["key"][:8]
            key["key"] = None

        return jsonify({"keys": keys}), 200

    except Exception as e:
        logger.error(f"Get API keys failed: {str(e)}")
        return jsonify({"keys": []}), 200


@router.route("/api-keys", methods=["POST"])
@jwt_required()
@limiter.limit("5 per day")  # Limit API key creation
def create_api_key():
    """Create new API key."""
    import uuid

    user_id = get_current_user_id()
    data = request.json or {}

    try:
        from providers.firebase_provider import FirebaseProvider
        import secrets
        import hashlib

        db = FirebaseProvider()

        # Check tier limits
        user = user_service.get_user_by_id(user_id)
        max_keys = tier_service.get_max_api_keys(user.tier)
        existing_keys = db.count("api_keys", filters={"user_id": user_id})

        if existing_keys >= max_keys:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Maximum {max_keys} API keys allowed for {user.tier} tier",
                    }
                ),
                400,
            )

        # Generate key
        key = f"sk_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        new_key = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": data.get("name", "Unnamed Key"),
            "key_hash": key_hash,
            "key_prefix": key[:8],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "permissions": data.get("permissions", ["read"]),
            "is_active": True,
        }

        db.save("api_keys", new_key["id"], new_key)

        return (
            jsonify(
                {"success": True, "api_key": key, "key": new_key}  # Only shown once!
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Create API key failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/api-keys/<key_id>", methods=["DELETE"])
@jwt_required()
def revoke_api_key(key_id):
    """Revoke API key."""
    user_id = get_current_user_id()

    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        key = db.get("api_keys", key_id)
        if not key or key["user_id"] != user_id:
            return jsonify({"success": False, "message": "Key not found"}), 404

        # Soft delete
        key["is_active"] = False
        key["revoked_at"] = datetime.utcnow().isoformat()
        db.save("api_keys", key_id, key)

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Revoke API key failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/webhook-secret", methods=["POST"])
@jwt_required()
def regenerate_webhook_secret():
    """Regenerate webhook secret."""
    import hashlib

    user_id = get_current_user_id()
    try:
        from providers.firebase_provider import FirebaseProvider
        import secrets

        db = FirebaseProvider()
        user = user_service.get_user_by_id(user_id)

        # Generate new secret
        secret = f"whsec_{secrets.token_urlsafe(32)}"
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()

        # Update user settings
        settings = user.settings
        settings["webhook_secret"] = secret_hash
        settings["webhook_secret_preview"] = secret[:12] + "..."

        user_service.update_user_preferences(user_id, settings)

        return jsonify({"success": True, "secret": secret}), 200  # Only shown once!

    except Exception as e:
        logger.error(f"Regenerate webhook secret failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/api/stats", methods=["GET"])
@jwt_required()
def get_api_stats():
    """Get API usage statistics."""
    user_id = get_current_user_id()

    try:
        from providers.redis_provider import RedisProvider
        import time

        redis = RedisProvider()

        # Get stats from Redis (tracked by middleware)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        stats_key = f"api_stats:{user_id}:{today}"

        stats = redis.get(stats_key) or {
            "total_requests": 0,
            "success_count": 0,
            "total_response_time": 0,
            "endpoints": {},
        }

        total = stats["total_requests"]
        success = stats["success_count"]

        return (
            jsonify(
                {
                    "stats": {
                        "total_requests": total,
                        "success_rate": round(
                            (success / total * 100) if total > 0 else 0
                        ),
                        "avg_response_time": (
                            round(stats["total_response_time"] / total)
                            if total > 0
                            else 0
                        ),
                        "remaining_requests": 1000 - total,  # Adjust based on tier
                    }
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get API stats failed: {str(e)}")
        return (
            jsonify(
                {
                    "stats": {
                        "total_requests": 0,
                        "success_rate": 0,
                        "avg_response_time": 0,
                        "remaining_requests": 1000,
                    }
                }
            ),
            200,
        )


@router.route("/2fa/enable", methods=["POST"])
@jwt_required()
def enable_2fa():
    """Enable two-factor authentication."""
    user_id = get_current_user_id()

    try:
        import pyotp

        user = user_service.get_user_by_id(user_id)

        # Check if 2FA already enabled
        if user.settings.get("two_factor_enabled"):
            return jsonify({"success": False, "message": "2FA already enabled"}), 400

        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Store temporarily (expires in 10 minutes)
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()
        redis.setex(f"2fa_pending:{user_id}", 600, secret)

        return (
            jsonify(
                {
                    "success": True,
                    "secret": secret,  # User manually enters this in Google Authenticator
                    "instructions": "Open Google Authenticator and add this secret manually",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Enable 2FA failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/2fa/verify", methods=["POST"])
@jwt_required()
@limiter.limit("5 per minute")  # prevent brute force attacks
def verify_2fa():
    """Verify and enable 2FA with code."""
    user_id = get_current_user_id()
    data = request.json
    code = data.get("code")

    try:
        import pyotp
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()
        secret = redis.get(f"2fa_pending:{user_id}")

        if not secret:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "2FA setup expired. Please try again.",
                    }
                ),
                400,
            )

        # Verify the code
        totp = pyotp.TOTP(secret)
        if not totp.verify(code):
            return (
                jsonify({"success": False, "message": "Invalid verification code"}),
                400,
            )

        # Enable 2FA for user
        user = user_service.get_user_by_id(user_id)

        # Update user settings
        settings = user.settings
        settings["two_factor_enabled"] = True
        settings["two_factor_secret"] = secret

        # Update user
        updated_user = user_service.update_user_preferences(user_id, settings)

        # Clean up
        redis.delete(f"2fa_pending:{user_id}")

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Two-factor authentication enabled successfully",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Verify 2FA failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/2fa/disable", methods=["POST"])
@jwt_required()
@limiter.limit("3 per hour")  # Limit disable attempts
def disable_2fa():
    """Disable two-factor authentication."""
    user_id = get_current_user_id()
    data = request.json
    code = data.get("code")  # Require verification to disable

    try:
        import pyotp

        user = user_service.get_user_by_id(user_id)

        if not user.settings.get("two_factor_enabled"):
            return jsonify({"success": False, "message": "2FA is not enabled"}), 400

        # Verify code before disabling
        secret = user.settings.get("two_factor_secret")
        if not secret:
            return (
                jsonify({"success": False, "message": "2FA configuration error"}),
                500,
            )

        totp = pyotp.TOTP(secret)
        if not totp.verify(code):
            return (
                jsonify({"success": False, "message": "Invalid verification code"}),
                400,
            )

        # Disable 2FA
        settings = user.settings
        settings["two_factor_enabled"] = False
        settings["two_factor_secret"] = None

        updated_user = user_service.update_user_preferences(user_id, settings)

        return (
            jsonify({"success": True, "message": "Two-factor authentication disabled"}),
            200,
        )

    except Exception as e:
        logger.error(f"Disable 2FA failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@router.route("/account", methods=["DELETE"])
@jwt_required()
@limiter.limit("1 per hour")  # Critical action
def delete_account():
    """Delete user account permanently."""
    user_id = get_current_user_id()
    data = request.json or {}

    try:
        confirm_email = data.get("confirm_email")
        reason = data.get("reason")

        user = user_service.get_user_by_id(user_id)

        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        if confirm_email != user.email:
            return (
                jsonify(
                    {"success": False, "message": "Email confirmation does not match"}
                ),
                400,
            )

        # Log reason if provided
        if reason:
            from providers.firebase_provider import FirebaseProvider

            db = FirebaseProvider()
            db.save(
                "deletion_reasons",
                f"{user_id}_{datetime.utcnow().timestamp()}",
                {
                    "user_id": user_id,
                    "email": user.email,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        # Delete user data (implement async cleanup)
        # For now, just mark as deleted
        user.settings["deleted_at"] = datetime.utcnow().isoformat()
        user.settings["deletion_reason"] = reason
        user_service.update_user_preferences(user_id, user.settings)

        # Blacklist all tokens
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()
        redis.setex(f"user_deleted:{user_id}", 86400, "true")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Delete account failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
