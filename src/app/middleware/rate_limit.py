"""
Rate limiting middleware.
"""

from flask import request, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import functools

from core.exceptions import RateLimitExceeded
from services.user_service import UserService


def tier_based_rate_limit(key_func=None):
    """
    Rate limit decorator that applies different limits based on user tier.
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Get rate limits from config
            from app.config import Config

            # Default rate limit for unauthenticated users
            rate_limit = Config.RATE_LIMIT_DEFAULT

            # Check if user is authenticated
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    from flask_jwt_extended import decode_token

                    token = auth_header.split(" ")[1]
                    decoded = decode_token(token)
                    user_id = decoded["sub"]

                    # Get user tier
                    user = UserService(user_id)
                    if user:
                        # Set rate limit based on tier
                        if user.tier == "free":
                            rate_limit = Config.RATE_LIMIT_FREE
                        elif user.tier == "starter":
                            rate_limit = Config.RATE_LIMIT_STARTER
                        elif user.tier == "pro":
                            rate_limit = Config.RATE_LIMIT_PRO
                        elif user.tier == "plus" or user.tier == "enterprise":
                            rate_limit = Config.RATE_LIMIT_PLUS
                except Exception:
                    pass  # Use default rate limit

            # Create a Limiter instance for this specific endpoint
            limiter = Limiter(
                key_func=key_func or get_remote_address, default_limits=[rate_limit]
            )

            # Apply rate limiting
            @limiter.limit(rate_limit)
            def limited_function(*args, **kwargs):
                return f(*args, **kwargs)

            return limited_function(*args, **kwargs)

        return decorated_function

    return decorator
