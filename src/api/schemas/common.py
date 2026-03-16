"""
Common schemas used across multiple endpoints.
"""

from marshmallow import (
    Schema,
    fields,
    validate,
    validates,
    validates_schema,
    ValidationError,
)
from datetime import datetime
from typing import Optional, List, Dict, Any
















class PaginationSchema(Schema):
    """Pagination parameters schema."""

    page = fields.Integer(missing=1, validate=validate.Range(min=1))
    per_page = fields.Integer(missing=20, validate=validate.Range(min=1, max=100))
    sort_by = fields.String(missing="created_at")
    sort_order = fields.String(validate=validate.OneOf(["asc", "desc"]), missing="desc")


class FilterSchema(Schema):
    """Filter parameters schema."""

    field = fields.String(required=True)
    operator = fields.String(
        validate=validate.OneOf(
            ["eq", "neq", "gt", "gte", "lt", "lte", "like", "in", "nin"]
        ),
        missing="eq",
    )
    value = fields.Raw(required=True)


class SearchSchema(Schema):
    """Search parameters schema."""

    query = fields.String(validate=validate.Length(min=1, max=255))
    search_fields = fields.List(fields.String())  # ⬅️ FIXED: Changed variable name
    fuzzy = fields.Boolean(missing=False)


class DateRangeSchema(Schema):
    """Date range schema."""

    start_date = fields.DateTime()
    end_date = fields.DateTime()
    timezone = fields.String(missing="UTC")

    @validates_schema
    def validate_dates(self, data, **kwargs):
        """Validate that start_date is before end_date."""
        if "start_date" in data and "end_date" in data:
            if data["start_date"] > data["end_date"]:
                raise ValidationError("start_date must be before end_date")


class StatsSchema(Schema):
    """Statistics request schema."""

    metric = fields.String(
        required=True,
        validate=validate.OneOf(
            [
                "videos_processed",
                "ai_costs",
                "user_growth",
                "revenue",
                "processing_time",
                "error_rate",
                "queue_length",
            ]
        ),
    )
    interval = fields.String(
        validate=validate.OneOf(["hour", "day", "week", "month", "year"]), missing="day"
    )
    group_by = fields.String(
        validate=validate.OneOf(["tier", "video_type", "status", "user"]),
        missing="tier",
    )
    date_range = fields.Nested(DateRangeSchema)


class ExportRequestSchema(Schema):
    """Export request schema."""

    format = fields.String(
        validate=validate.OneOf(["json", "csv", "pdf", "excel"]), missing="json"
    )
    filters = fields.List(fields.Nested(FilterSchema))
    columns = fields.List(fields.String())
    include_headers = fields.Boolean(missing=True)


class WebhookSchema(Schema):
    """Webhook configuration schema."""

    url = fields.Url(required=True)
    events = fields.List(
        fields.String(
            validate=validate.OneOf(
                [
                    "video.processed",
                    "video.failed",
                    "user.created",
                    "subscription.updated",
                    "payment.received",
                ]
            )
        ),
        required=True,
    )
    secret = fields.String(validate=validate.Length(min=16, max=255))
    active = fields.Boolean(missing=True)


class NotificationSchema(Schema):
    """Notification schema."""

    id = fields.String()
    user_id = fields.String()
    type = fields.String(
        validate=validate.OneOf(["info", "warning", "error", "success"])
    )
    title = fields.String(validate=validate.Length(max=255))
    message = fields.String(validate=validate.Length(max=1000))
    read = fields.Boolean()
    created_at = fields.DateTime()
    metadata = fields.Dict()


class ErrorResponseSchema(Schema):
    """Error response schema."""

    error = fields.Dict()


class SuccessResponseSchema(Schema):
    """Success response schema."""

    success = fields.Boolean()
    message = fields.String()
    data = fields.Raw()


class HealthCheckSchema(Schema):
    """Health check response schema."""

    status = fields.String()
    timestamp = fields.DateTime()
    services = fields.Dict()
    version = fields.String()


class SystemInfoSchema(Schema):
    """System information schema."""

    version = fields.String()
    environment = fields.String()
    uptime = fields.Float()
    memory_usage = fields.Float()
    cpu_usage = fields.Float()
    database_status = fields.String()
    redis_status = fields.String()
    queue_length = fields.Integer()
    active_users = fields.Integer()
    videos_processing = fields.Integer()


class RateLimitSchema(Schema):
    """Rate limit information schema."""

    limit = fields.Integer()
    remaining = fields.Integer()
    reset = fields.Integer()


class ValidationErrorSchema(Schema):
    """Validation error schema."""

    field = fields.String()
    message = fields.String()
    code = fields.String()
