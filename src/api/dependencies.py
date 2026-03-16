"""
FastAPI-style dependencies for Flask routes.
"""

from functools import wraps
from flask import request, g
from typing import Optional, Callable, Any, Dict

from core.exceptions import UnauthorizedError, ValidationError, ForbiddenError
from services.user_service import UserService
from services.tier_service import TierService


def get_current_user():
    """Dependency to get current authenticated user."""
    from flask_jwt_extended import get_jwt_identity

    user_id = get_jwt_identity()
    if not user_id:
        raise UnauthorizedError("Authentication required")

    user = UserService(user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user


def require_tier(min_tier: str):
    """Dependency to require minimum tier level."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()

            tier_service = TierService()
            user_tier_value = tier_service.get_tier_value(user.tier)
            required_tier_value = tier_service.get_tier_value(min_tier)

            if user_tier_value < required_tier_value:
                raise ForbiddenError(
                    f"{min_tier.capitalize()} tier or higher required. "
                    f"Current tier: {user.tier}"
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_request(schema_class):
    """Dependency to validate request data against a schema."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get request data based on method
            if request.method in ["POST", "PUT", "PATCH"]:
                if request.is_json:
                    data = request.get_json()
                elif request.form:
                    data = request.form.to_dict()
                else:
                    data = {}
            else:
                data = request.args.to_dict()

            try:
                # Validate data against schema
                validated_data = schema_class().load(data)

                # Store validated data in request context
                g.validated_data = validated_data

                return func(*args, **kwargs)

            except ValidationError as e:
                raise ValidationError(str(e))

        return wrapper

    return decorator


def paginate(default_per_page: int = 20, max_per_page: int = 100):
    """Dependency to handle pagination parameters."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", default_per_page, type=int)

            # Validate pagination parameters
            if page < 1:
                raise ValidationError("Page must be at least 1", field="page")

            if per_page < 1:
                raise ValidationError("Per page must be at least 1", field="per_page")

            if per_page > max_per_page:
                raise ValidationError(
                    f"Per page cannot exceed {max_per_page}", field="per_page"
                )

            # Store pagination in request context
            g.pagination = {
                "page": page,
                "per_page": per_page,
                "offset": (page - 1) * per_page,
            }

            return func(*args, **kwargs)

        return wrapper

    return decorator


def rate_limit(limit: str = "100 per hour"):
    """Dependency to apply rate limiting."""
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)

    def decorator(func):
        @wraps(func)
        @limiter.limit(limit)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def cache_response(ttl: int = 300, key_prefix: str = "cache"):
    """Dependency to cache response."""
    from providers.redis_provider import RedisProvider

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            redis = RedisProvider()

            # Generate cache key
            cache_key = f"{key_prefix}:{request.path}"
            if request.args:
                import hashlib

                args_hash = hashlib.md5(
                    str(sorted(request.args.items())).encode()
                ).hexdigest()
                cache_key += f":{args_hash}"

            # Try to get from cache
            cached_response = redis.get(cache_key)
            if cached_response:
                return cached_response

            # Execute function
            response = func(*args, **kwargs)

            # Cache response
            redis.setex(cache_key, ttl, response)

            return response

        return wrapper

    return decorator


def track_analytics(event_name: str, properties: Optional[Dict[str, Any]] = None):
    """Dependency to track analytics events."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from services.notification_service import NotificationService

            # Execute function
            response = func(*args, **kwargs)

            try:
                # Get current user if available
                user_id = None
                from flask import g

                if hasattr(g, "current_user"):
                    user_id = g.current_user.id

                # Track event
                notification_service = NotificationService()
                notification_service.track_event(
                    event_name=event_name, user_id=user_id, properties=properties or {}
                )

            except Exception as e:
                # Don't fail the request if analytics tracking fails
                import logging

                logging.error(f"Failed to track analytics: {e}")

            return response

        return wrapper

    return decorator


def require_permission(permission: str):
    """Dependency to require specific permission."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()

            # Check if user has permission
            if not user.is_admin and permission not in user.permissions:
                raise ForbiddenError(f"Permission '{permission}' required")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def handle_file_upload(
    max_size_mb: int = 2048, allowed_extensions: Optional[list] = None
):
    """Dependency to handle file uploads."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from werkzeug.utils import secure_filename
            from core.exceptions import FileUploadError

            if "file" not in request.files:
                raise ValidationError("No file provided", field="file")

            file = request.files["file"]

            if file.filename == "":
                raise ValidationError("No file selected", field="file")

            # Check file size
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)  # Reset to beginning

            max_size_bytes = max_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                raise ValidationError(
                    f"File size exceeds maximum allowed size of {max_size_mb}MB",
                    field="file",
                )

            # Check file extension
            if allowed_extensions:
                import os

                ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
                if ext not in allowed_extensions:
                    raise ValidationError(
                        f"File extension .{ext} not allowed. "
                        f"Allowed extensions: {', '.join(allowed_extensions)}",
                        field="file",
                    )

            # Secure filename
            filename = secure_filename(file.filename)

            # Store file in request context
            g.uploaded_file = {
                "file": file,
                "filename": filename,
                "size": file_size,
                "content_type": file.content_type,
            }

            return func(*args, **kwargs)

        return wrapper

    return decorator


def background_task(task_func: Callable, *task_args, **task_kwargs):
    """Dependency to run function as background task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from tasks.celery_app import celery

            # Execute main function
            response = func(*args, **kwargs)

            # Schedule background task
            task_func.delay(*task_args, **task_kwargs)

            return response

        return wrapper

    return decorator
