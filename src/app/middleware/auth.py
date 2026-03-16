"""
Authentication middleware.
"""

from functools import wraps
from flask import request, jsonify, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
import jwt as pyjwt

from core.exceptions import UnauthorizedError, ForbiddenError


def jwt_required(f):
    """Decorator for JWT-protected endpoints."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from services.user_service import get_user_by_id

        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()

            if not user_id:
                raise UnauthorizedError("Invalid token")

            # Get user from database
            user = get_user_by_id(user_id)
            if not user or not user.is_active:
                raise UnauthorizedError("User not found or inactive")

            # Store user in Flask's g object
            g.current_user = user

            return f(*args, **kwargs)
        except pyjwt.ExpiredSignatureError:
            raise UnauthorizedError("Token has expired")
        except pyjwt.InvalidTokenError:
            raise UnauthorizedError("Invalid token")
        except Exception as e:
            raise UnauthorizedError(str(e))

    return decorated_function


def admin_required(f):
    """Decorator for admin-only endpoints."""

    @wraps(f)
    @jwt_required
    def decorated_function(*args, **kwargs):
        if not g.current_user.is_admin:
            raise ForbiddenError("Admin access required")
        return f(*args, **kwargs)

    return decorated_function


def tier_required(min_tier):
    """Decorator for tier-restricted endpoints."""

    def decorator(f):
        @wraps(f)
        @jwt_required
        def decorated_function(*args, **kwargs):
            from core.domain.value_objects.tier import Tier

            # Convert string tier to Tier enum
            if isinstance(min_tier, str):
                required_tier = Tier(min_tier.lower())
            else:
                required_tier = min_tier

            # Get user's current tier
            user_tier = Tier(g.current_user.tier)

            # Check if user meets tier requirement
            tier_hierarchy = {
                Tier.FREE: 0,
                Tier.STARTER: 1,
                Tier.PRO: 2,
                Tier.PLUS: 3,
                Tier.ENTERPRISE: 4,
            }

            if tier_hierarchy[user_tier] < tier_hierarchy[required_tier]:
                raise ForbiddenError(
                    f"{required_tier.value.capitalize()} tier or higher required"
                )

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_current_user():
    """Get current user from Flask's g object."""
    return getattr(g, "current_user", None)
