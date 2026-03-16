"""Public authentication routes (no JWT required)."""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token
import logging

from core.exceptions import ValidationError, UnauthorizedError
from api.dependencies import validate_request
from api.schemas.auth import (
    LoginSchema,
    RegisterSchema,
    ForgotPasswordSchema,
    ResetPasswordSchema,
    VerifyEmailSchema,
    AuthResponseSchema,
)
from services.user_service import UserService
from services.email_service import EmailService
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

public_auth_bp = Blueprint("public_auth", __name__)
logger = logging.getLogger(__name__)

user_service = UserService()
email_service = EmailService()
limiter = Limiter(key_func=get_remote_address)


@public_auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute, 100 per day")  # Prevent brute force
@validate_request(LoginSchema)
def login():
    """Authenticate user and return tokens with session."""
    from flask import g, session

    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        # Authenticate using instance method
        user = user_service.authenticate_user(email, password)

        if not user:
            return jsonify({"error": {"message": "Invalid email or password"}}), 401

        if not user.is_active():
            return jsonify({"error": {"message": "Account is not active"}}), 401

        # ALSO set Flask session
        from flask import session

        session["user_id"] = user.id
        session["user_email"] = user.email
        session["user_tier"] = getattr(user, "tier", "free")
        session.permanent = True

        # Create tokens
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(hours=1),
            additional_claims={
                "email": user.email,
                "tier": getattr(user, "tier", "free"),
                "is_admin": getattr(user, "is_admin", False),
            },
        )

        refresh_token = create_refresh_token(
            identity=user.id, expires_delta=timedelta(days=30)
        )

        response = jsonify(
            {
                "success": True,
                "message": "Login successful",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "tier": getattr(user, "tier", "free"),
                    "full_name": getattr(user, "full_name", ""),
                },
                "expires_in": 3600,
            }
        )

        return response, 200

    except Exception as e:
        import traceback

        print(f"Login error: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": {
                        "message": f"Login failed: {str(e)}",
                        "code": "INTERNAL_ERROR",
                    }
                }
            ),
            500,
        )


@public_auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per hour, 10 per day")  # Prevent spam registration
@validate_request(RegisterSchema)
def register():
    """Register a new user."""
    try:
        from flask import g

        data = g.validated_data
        print(f"Registration data: {data}")

        # Combine first_name and last_name into full_name
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        if not full_name:
            full_name = data.get("email").split("@")[0]  # Default from email

        # Check if user already exists - use instance method
        existing_user = user_service.get_user_by_email(data["email"])
        if existing_user:
            return (
                jsonify({"error": {"message": "User with this email already exists"}}),
                400,
            )

        # Create user - use instance method
        user = user_service.create_user(
            email=data["email"],
            password=data["password"],
            full_name=full_name,
            tier=data.get("tier", "free"),
            # credits_remaining=10,
        )

        if not user:
            return jsonify({"error": {"message": "Failed to create user"}}), 500

        # Create tokens
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(hours=1),
            additional_claims={
                "email": user.email,
                "tier": getattr(user, "tier", "free"),
            },
        )
        refresh_token = create_refresh_token(
            identity=user.id, expires_delta=timedelta(days=30)
        )

        # If user opted in for newsletter, handle that
        if data.get("newsletter"):
            try:
                email_service = EmailService()
                # Add to newsletter list (implement as needed)
                # email_service.subscribe_to_newsletter(user.email)
                pass
            except Exception as e:
                print(f"Newsletter subscription failed: {e}")

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Registration successful",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "full_name": getattr(user, "full_name", full_name),
                        "tier": getattr(user, "tier", "free"),
                    },
                    "expires_in": 3600,
                }
            ),
            201,
        )

    except Exception as e:
        import traceback

        print(f"Registration error: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": {
                        "message": f"Registration failed: {str(e)}",
                        "code": "INTERNAL_ERROR",
                    }
                }
            ),
            500,
        )


@public_auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")  # Prevent email flooding
@validate_request(ForgotPasswordSchema)
def forgot_password():
    """Send password reset email."""
    try:
        from flask import g

        data = g.validated_data

        user = user_service.get_user_by_email(data["email"])

        if user:
            # Generate reset token
            reset_token = user_service.generate_password_reset_token(user.id)

            # Send reset email
            email_service.send_password_reset_email(user.email, reset_token)

        return (
            jsonify(
                {
                    "success": True,
                    "message": "If an account exists with this email, a password reset link has been sent",
                }
            ),
            200,
        )

    except Exception as e:
        print(f"Forgot password error: {str(e)}")
        return jsonify({"error": {"message": "An error occurred"}}), 500


@public_auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("3 per hour")  # Prevent abuse
@validate_request(ResetPasswordSchema)
def reset_password():
    """Reset password with token."""
    from flask import g

    data = g.validated_data

    try:
        success = user_service.reset_password_with_token(
            data["token"], data["password"]
        )

        if not success:
            raise ValidationError("Invalid or expired reset token", field="token")

        return jsonify({"success": True, "message": "Password reset successfully"}), 200

    except Exception as e:
        logger.error(f"Password reset failed: {str(e)}")
        raise


@public_auth_bp.route("/verify-email", methods=["POST"])
@validate_request(VerifyEmailSchema)
def verify_email():
    """Verify email with token."""
    from flask import g

    data = g.validated_data

    try:
        from services.user_service import (
            verify_email_token,
            get_user_by_id,
            verify_user_email,
        )

        user_id = verify_email_token(data["token"])

        if not user_id:
            raise ValidationError(
                "Invalid or expired verification token", field="token"
            )

        user = get_user_by_id(user_id)

        if not user:
            raise ValidationError("User not found")

        verify_user_email(user_id)

        return jsonify({"success": True, "message": "Email verified successfully"}), 200

    except Exception as e:
        logger.error(f"Email verification failed: {str(e)}")
        raise
