"""
Authentication schemas.
"""

from marshmallow import Schema, fields, validate, validates, ValidationError, pre_load
import re


class LoginSchema(Schema):
    """Login request schema."""

    email = fields.Email(required=True, validate=validate.Length(max=255))
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))
    remember = fields.Boolean(missing=False)


class RegisterSchema(Schema):
    """Registration request schema."""

    email = fields.Email(required=True, validate=validate.Length(max=255))
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))
    full_name = fields.String(
        validate=validate.Length(max=255), missing=""
    )  # ✅ Changed
    tier = fields.String(
        validate=validate.OneOf(["free", "starter", "pro", "plus", "enterprise"]),
        missing="free",
    )
    terms = fields.Boolean(required=True)
    newsletter = fields.Boolean(missing=False)

    @validates("password")
    def validate_password(self, value):
        """Validate password strength."""
        if not re.search(r"[A-Z]", value):
            raise ValidationError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValidationError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", value):
            raise ValidationError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise ValidationError(
                "Password must contain at least one special character"
            )

    @validates("terms")
    def validate_terms(self, value):
        """Validate terms agreement."""
        if not value:
            raise ValidationError("You must agree to the terms of service")


class ForgotPasswordSchema(Schema):
    """Forgot password request schema."""

    email = fields.Email(required=True, validate=validate.Length(max=255))


class ResetPasswordSchema(Schema):
    """Reset password request schema."""

    token = fields.String(required=True)
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))

    @validates("password")
    def validate_password(self, value):
        """Validate password strength."""
        if not re.search(r"[A-Z]", value):
            raise ValidationError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValidationError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", value):
            raise ValidationError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise ValidationError(
                "Password must contain at least one special character"
            )


class VerifyEmailSchema(Schema):
    """Verify email request schema."""

    token = fields.String(required=True)


class AuthResponseSchema(Schema):
    """Authentication response schema."""

    access_token = fields.String()
    refresh_token = fields.String()
    user = fields.Dict()
    expires_in = fields.Integer()


class UserProfileSchema(Schema):
    """User profile schema."""

    email = fields.Email(validate=validate.Length(max=255))
    full_name = fields.String(validate=validate.Length(max=255))
    avatar_url = fields.String(validate=validate.Length(max=500))
    language = fields.String(validate=validate.Length(max=10))
    timezone = fields.String(validate=validate.Length(max=50))
    settings = fields.Dict()


class UserProfileSchema(Schema):
    """User profile schema."""

    email = fields.Email(validate=validate.Length(max=255))
    full_name = fields.String(validate=validate.Length(max=255))
    avatar_url = fields.String(validate=validate.Length(max=500))
    language = fields.String(validate=validate.Length(max=10))
    timezone = fields.String(validate=validate.Length(max=50))
    settings = fields.Dict()


class ChangePasswordSchema(Schema):
    """Change password request schema."""

    current_password = fields.String(required=True)
    new_password = fields.String(
        required=True, validate=validate.Length(min=8, max=128)
    )

    @validates("new_password")
    def validate_new_password(self, value):
        """Validate password strength."""
        if not re.search(r"[A-Z]", value):
            raise ValidationError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValidationError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", value):
            raise ValidationError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise ValidationError(
                "Password must contain at least one special character"
            )
