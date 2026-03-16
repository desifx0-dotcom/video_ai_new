"""
User schemas for request/response validation.
"""

# from marshmallow import Schema, fields, validate, validates, ValidationError
from datetime import datetime

from marshmallow import (
    Schema,
    fields,
    validate,
    validates,
    validates_schema,
    ValidationError,
)
import re


class UserResponseSchema(Schema):
    """User response schema."""

    id = fields.String()
    email = fields.String()
    tier = fields.String()
    full_name = fields.String()
    avatar_url = fields.String()
    language = fields.String()
    timezone = fields.String()
    credits_remaining = fields.Integer()
    videos_processed_this_month = fields.Integer()
    monthly_video_limit = fields.Integer()
    total_videos_processed = fields.Integer()
    is_admin = fields.Boolean()
    created_at = fields.DateTime()
    last_login = fields.DateTime()
    email_verified = fields.Boolean()
    settings = fields.Dict()


class UserUpdateSchema(Schema):
    """User update request schema."""

    full_name = fields.String(validate=validate.Length(max=255))
    # avatar_url = fields.String(validate=validate.URL(), validate=validate.Length(max=500))
    avatar_url = fields.String(validate=[validate.URL(), validate.Length(max=500)])
    language = fields.String(validate=validate.Length(max=10))
    timezone = fields.String(validate=validate.Length(max=50))
    settings = fields.Dict()


class UserStatsSchema(Schema):
    """User statistics schema."""

    user_id = fields.String()
    tier = fields.String()
    videos_processed_today = fields.Integer()
    videos_processed_this_month = fields.Integer()
    total_videos_processed = fields.Integer()
    total_processing_time = fields.Float()
    average_processing_time = fields.Float()
    total_ai_costs = fields.Float()
    credits_remaining = fields.Integer()
    subscription_status = fields.String()
    subscription_end_date = fields.DateTime()


class UserListSchema(Schema):
    """User list response schema."""

    users = fields.List(fields.Nested(UserResponseSchema))
    total = fields.Integer()
    page = fields.Integer()
    per_page = fields.Integer()
    total_pages = fields.Integer()


class UserSearchSchema(Schema):
    """User search request schema."""

    query = fields.String(required=True, validate=validate.Length(min=1, max=255))
    field = fields.String(
        validate=validate.OneOf(["email", "name", "tier"]), missing="email"
    )


class ChangePasswordSchema(Schema):
    """Change password request schema."""

    current_password = fields.String(required=True, validate=validate.Length(min=1))
    new_password = fields.String(
        required=True, validate=validate.Length(min=8, max=128)
    )
    confirm_password = fields.String(required=True)

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

    @validates_schema
    def validate_passwords_match(self, data, **kwargs):
        """Validate that new password and confirm password match."""
        if data["new_password"] != data["confirm_password"]:
            raise ValidationError(
                "New passwords do not match", field_name="confirm_password"
            )


class UserActivitySchema(Schema):
    """User activity schema."""

    user_id = fields.String()
    last_login = fields.DateTime()
    last_video_processed = fields.DateTime()
    videos_processed_last_7_days = fields.Integer()
    average_session_duration = fields.Float()
    favorite_styles = fields.List(fields.String())
    preferred_languages = fields.List(fields.String())


class UserPreferencesSchema(Schema):
    """User preferences schema."""

    default_quality = fields.String(
        validate=validate.OneOf(["480p", "720p", "1080p", "4k", "4k+hdr"]),
        missing="720p",
    )
    default_style = fields.String(validate=validate.Length(max=50))
    auto_translate = fields.Boolean(missing=False)
    email_notifications = fields.Boolean(missing=True)
    push_notifications = fields.Boolean(missing=True)
    retention_days = fields.Integer(validate=validate.Range(min=1, max=365), missing=7)
    language = fields.String(validate=validate.Length(max=10), missing="en")
    timezone = fields.String(validate=validate.Length(max=50), missing="UTC")


class UserExportSchema(Schema):
    """User data export schema."""

    include = fields.List(
        fields.String(
            validate=validate.OneOf(
                ["profile", "videos", "subscriptions", "transactions", "activity"]
            )
        ),
        missing=["profile", "videos"],
    )
    format = fields.String(validate=validate.OneOf(["json", "csv"]), missing="json")
