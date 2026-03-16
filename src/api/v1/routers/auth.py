"""
Authentication router for API v1.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, url_for
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from datetime import timedelta
import logging

from core.exceptions import ValidationError, UnauthorizedError
from api.dependencies import validate_request
from api.schemas.auth import (
    LoginSchema,
    RegisterSchema,
    ForgotPasswordSchema,
    ResetPasswordSchema,
    VerifyEmailSchema,
    ChangePasswordSchema,
    UserProfileSchema,
    AuthResponseSchema,
)
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

# from services.user_service import (
#     authenticate_user,
#     create_user,
#     get_user_by_email,
#     update_user_password,
#     update_user_profile,
#     verify_email_token,
#     generate_password_reset_token,
#     reset_password_with_token,
# )
# from services.email_service import send_verification_email, send_password_reset_email
from services.user_service import UserService
from services.email_service import EmailService


user_service = UserService()
email_service = EmailService()

router = Blueprint("auth_protected", __name__)
logger = logging.getLogger(__name__)


#     """Register a new user."""
#     data = request.validated_data

#     try:
#         # Check if user already exists
#         existing_user = UserService.get_user_by_email(data["email"])
#         if existing_user:
#             raise ValidationError("User with this email already exists", field="email")

#         # Create user
#         user = UserService.create_user(
#             email=data["email"],
#             password=data["password"],
#             tier=data.get("tier", "free"),
#             full_name=data.get("full_name"),
#         )

#         # Send verification email
#         EmailService.send_verification_email(user.email, user.id)

#         # Create tokens
#         access_token = create_access_token(
#             identity=user.id,
#             expires_delta=timedelta(hours=1),
#             additional_claims={
#                 "email": user.email,
#                 "tier": user.tier.value,
#                 "is_admin": user.is_admin,
#             },
#         )

#         refresh_token = create_refresh_token(
#             identity=user.id, expires_delta=timedelta(days=30)
#         )

#         # Track registration event
#         from services.notification_service import NotificationService

#         notification_service = NotificationService()
#         notification_service.track_event(
#             event_name="user.register",
#             user_id=user.id,
#             properties={"tier": user.tier.value},
#         )

#         # Record user signup metric
#         from app.monitoring.metrics import record_user_signup

#         record_user_signup(user.tier.value)

#         # Return response
#         response_schema = AuthResponseSchema()
#         return (
#             jsonify(
#                 response_schema.dump(
#                     {
#                         "access_token": access_token,
#                         "refresh_token": refresh_token,
#                         "user": {
#                             "id": user.id,
#                             "email": user.email,
#                             "tier": user.tier.value,
#                             "full_name": user.full_name,
#                             "is_admin": user.is_admin,
#                             "email_verified": False,
#                         },
#                         "expires_in": 3600,
#                     }
#                 )
#             ),
#             201,
#         )

#     except Exception as e:
#         logger.error(f"Registration failed: {str(e)}")
#         raise


@router.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    user_id = get_jwt_identity()

    try:
        from services.user_service import get_user_by_id

        user = get_user_by_id(user_id)

        if not user or not user.is_active():
            raise UnauthorizedError("User not found or inactive")

        # Create new access token
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(hours=1),
            additional_claims={
                "email": user.email,
                "tier": user.tier.value,
                "is_admin": user.is_admin,
            },
        )

        return jsonify({"access_token": access_token, "expires_in": 3600}), 200

    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        raise


# @router.route("/logout", methods=["POST"])
# @jwt_required(optional=True)  # Make optional so it works even with invalid tokens
# def logout():
#     """Logout user - clears session and invalidates tokens."""
#     try:
#         # Get user_id if available (don't fail if not)
#         user_id = None
#         try:
#             user_id = get_jwt_identity()
#         except:
#             pass

#         # Clear Flask session
#         from flask import session

#         session.clear()

#         # Create response
#         response = jsonify({"success": True, "message": "Logged out successfully"})

#         # Clear JWT cookies if using cookies
#         response.set_cookie("access_token_cookie", "", expires=0)
#         response.set_cookie("refresh_token_cookie", "", expires=0)

#         # Optionally track logout event (don't fail if tracking fails)
#         try:
#             if user_id:
#                 from services.notification_service import NotificationService

#                 notification_service = NotificationService()
#                 notification_service.track_event(
#                     event_name="user.logout", user_id=user_id
#                 )
#         except:
#             pass  # Don't fail if tracking fails

#         return response, 200

#     except Exception as e:
#         logger.error(f"Logout error: {str(e)}")
#         # Still return success to client - they should be logged out anyway
#         return jsonify({"success": True, "message": "Logged out"}), 200


# @router.route("/forgot-password", methods=["POST"])
# @validate_request(ForgotPasswordSchema)
# def forgot_password():
#     """Send password reset email."""
#     data = request.validated_data

#     try:
#         user = UserService.get_user_by_email(data["email"])

#         if user:
#             # Generate reset token
#             reset_token = UserService.generate_password_reset_token(user.id)

#             # Send reset email
#             EmailService.send_password_reset_email(user.email, reset_token)

#             # Don't reveal whether user exists for security
#             pass

#         return (
#             jsonify(
#                 {
#                     "success": True,
#                     "message": "If an account exists with this email, a password reset link has been sent",
#                 }
#             ),
#             200,
#         )

#     except Exception as e:
#         logger.error(f"Forgot password failed: {str(e)}")
#         raise


# @router.route("/reset-password", methods=["POST"])
# @validate_request(ResetPasswordSchema)
# def reset_password():
#     """Reset password with token."""
#     data = request.validated_data

#     try:
#         success = UserService.reset_password_with_token(data["token"], data["password"])

#         if not success:
#             raise ValidationError("Invalid or expired reset token", field="token")

#         return jsonify({"success": True, "message": "Password reset successfully"}), 200

#     except Exception as e:
#         logger.error(f"Password reset failed: {str(e)}")
#         raise


# @router.route("/verify-email", methods=["POST"])
# @validate_request(VerifyEmailSchema)
# def verify_email():
#     """Verify email with token."""
#     data = request.validated_data

#     try:
#         user_id = UserService.verify_email_token(data["token"])

#         if not user_id:
#             raise ValidationError(
#                 "Invalid or expired verification token", field="token"
#             )

#         from services.user_service import get_user_by_id, verify_user_email

#         user = get_user_by_id(user_id)

#         if not user:
#             raise ValidationError("User not found")

#         verify_user_email(user_id)

#         return jsonify({"success": True, "message": "Email verified successfully"}), 200

#     except Exception as e:
#         logger.error(f"Email verification failed: {str(e)}")
#         raise


@router.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    """Get user profile."""
    user_id = get_jwt_identity()

    try:
        from services.user_service import get_user_by_id

        user = get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        response_schema = UserProfileSchema()
        return (
            jsonify(
                response_schema.dump(
                    {
                        "email": user.email,
                        "full_name": user.full_name,
                        "avatar_url": user.avatar_url,
                        "language": user.language,
                        "timezone": user.timezone,
                        "settings": user.settings,
                    }
                )
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get profile failed: {str(e)}")
        raise


@router.route("/profile", methods=["PUT"])
@jwt_required()
@validate_request(UserProfileSchema)
def update_profile():
    """Update user profile."""
    user_id = get_jwt_identity()
    data = request.validated_data

    try:
        user = UserService.update_user_profile(user_id, data)

        response_schema = UserProfileSchema()
        return (
            jsonify(
                response_schema.dump(
                    {
                        "email": user.email,
                        "full_name": user.full_name,
                        "avatar_url": user.avatar_url,
                        "language": user.language,
                        "timezone": user.timezone,
                        "settings": user.settings,
                    }
                )
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Update profile failed: {str(e)}")
        raise


@router.route("/change-password", methods=["POST"])
@jwt_required()
@validate_request(ChangePasswordSchema)
def change_password():
    """Change user password."""
    user_id = get_jwt_identity()
    data = request.validated_data

    try:
        # Verify current password
        from services.user_service import authenticate_user_by_id

        if not UserService.authenticate_user_by_id(user_id, data["current_password"]):
            raise ValidationError(
                "Current password is incorrect", field="current_password"
            )

        # Update password
        UserService.update_user_password(user_id, data["new_password"])

        # Track password change event
        from services.notification_service import NotificationService

        notification_service = NotificationService()
        notification_service.track_event(
            event_name="user.password_change", user_id=user_id
        )

        return (
            jsonify({"success": True, "message": "Password changed successfully"}),
            200,
        )

    except Exception as e:
        logger.error(f"Change password failed: {str(e)}")
        raise


@router.route("/resend-verification", methods=["POST"])
@jwt_required()
def resend_verification():
    """Resend email verification."""
    user_id = get_jwt_identity()

    try:
        from services.user_service import get_user_by_id

        user = get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        if user.email_verified_at:
            raise ValidationError("Email already verified")

        # Send verification email
        EmailService.send_verification_email(user.email, user.id)

        return jsonify({"success": True, "message": "Verification email sent"}), 200

    except Exception as e:
        logger.error(f"Resend verification failed: {str(e)}")
        raise
