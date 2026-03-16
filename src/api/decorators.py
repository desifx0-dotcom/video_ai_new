"""Unified authentication decorator that supports both session and JWT."""

from functools import wraps
from flask import session, jsonify, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from services.user_service import UserService


def get_current_user():
    """Get current user from session OR JWT."""
    # First check session
    user_id = session.get("user_id")
    if user_id:
        g.auth_method = "session"
        return user_id

    # Then check JWT
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            g.auth_method = "jwt"
            return user_id
    except:
        pass

    return None


def login_required(f):
    """Decorator that allows both session and JWT authentication."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_current_user()

        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        # Load user into g for easy access
        try:
            user_service = UserService()
            g.current_user = user_service.get_user_by_id(user_id)
            g.user_id = user_id
        except Exception as e:
            return jsonify({"error": f"Failed to load user: {str(e)}"}), 500

        return f(*args, **kwargs)

    return decorated_function


def optional_auth(f):
    """Decorator that checks auth but doesn't require it."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_current_user()

        if user_id:
            try:
                user_service = UserService()
                g.current_user = user_service.get_user_by_id(user_id)
                g.user_id = user_id
            except:
                pass

        return f(*args, **kwargs)

    return decorated_function
