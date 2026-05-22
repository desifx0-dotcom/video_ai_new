"""Public authentication routes (no JWT required) - Complete production version with credit allocation."""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
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
)
from services.user_service import UserService
from services.email_service import EmailService
from services.credit_service import CreditService
from services.tier_service import TierService
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

public_auth_bp = Blueprint("public_auth", __name__)
logger = logging.getLogger(__name__)

user_service = UserService()
email_service = EmailService()
credit_service = CreditService()
tier_service = TierService()
limiter = Limiter(key_func=get_remote_address)


@public_auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute, 100 per day")
@validate_request(LoginSchema)
def login():
    """Authenticate user and return tokens with session."""
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

        # Set Flask session
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

        return (
            jsonify(
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
                        "credits_remaining": user.credits_remaining,
                        "monthly_limit": user.monthly_video_limit,
                        "videos_processed_this_month": user.videos_processed_this_month,
                    },
                    "expires_in": 3600,
                }
            ),
            200,
        )

    except Exception as e:
        import traceback

        logger.error(f"Login error: {traceback.format_exc()}")
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
@limiter.limit("5 per hour, 10 per day")
@validate_request(RegisterSchema)
def register():
    """Register a new user with initial credits."""
    
    # 🔥 Check if there was a validation error
    if hasattr(g, 'validation_error') and g.validation_error:
        return jsonify({
            "success": False,
            "error": g.validation_error
        }), 400
    
    try:
        data = g.validated_data
        logger.info(f"Registration data: {data}")

        # Combine first_name and last_name into full_name
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        if not full_name:
            full_name = data.get("email").split("@")[0]

        # Check if user already exists
        existing_user = user_service.get_user_by_email(data["email"])
        if existing_user:
            return (
                jsonify({
                    "success": False,
                    "error": {
                        "code": "USER_EXISTS",
                        "message": "User with this email already exists",
                        "field": "email"
                    }
                }),
                400,
            )

        # Get tier from data
        tier = data.get("tier", "free")

        # Get initial credits based on tier
        initial_credits = tier_service.get_credits_per_month(tier)

        # Create user with initial credits
        user = user_service.create_user(
            email=data["email"],
            password=data["password"],
            full_name=full_name,
            tier=tier,
            credits_remaining=initial_credits,
        )

        if not user:
            return jsonify({
                "success": False,
                "error": {
                    "code": "USER_CREATION_FAILED",
                    "message": "Failed to create user"
                }
            }), 500

        # Create tokens
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(hours=1),
            additional_claims={
                "email": user.email,
                "tier": tier,
            },
        )
        refresh_token = create_refresh_token(
            identity=user.id, expires_delta=timedelta(days=30)
        )

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
                        "tier": tier,
                        "credits_remaining": getattr(user, "credits_remaining", initial_credits),
                        "monthly_limit": getattr(user, "monthly_video_limit", 3),
                    },
                    "expires_in": 3600,
                }
            ),
            201,
        )

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Registration error: {error_traceback}")
        return (
            jsonify({
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e)
                }
            }),
            500,
        )


@public_auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")
@validate_request(ForgotPasswordSchema)
def forgot_password():
    """Send password reset email."""
    try:
        data = g.validated_data
        user = user_service.get_user_by_email(data["email"])

        if user:
            reset_token = user_service.generate_password_reset_token(user.id)
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
        logger.error(f"Forgot password error: {str(e)}")
        return jsonify({"error": {"message": "An error occurred"}}), 500


@public_auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("3 per hour")
@validate_request(ResetPasswordSchema)
def reset_password():
    """Reset password with token."""
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
        return jsonify({"error": {"message": str(e)}}), 500


@public_auth_bp.route("/verify-email", methods=["POST"])
@validate_request(VerifyEmailSchema)
def verify_email():
    """Verify email with token."""
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
        return jsonify({"error": {"message": str(e)}}), 500
