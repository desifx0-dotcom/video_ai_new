"""
Custom business exceptions.
"""

class VideoAIException(Exception):
    """Base exception for Video AI Studio."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(VideoAIException):
    """Validation error."""
    def __init__(self, message: str, field: str = None):
        self.field = field
        code = "VALIDATION_ERROR"
        if field:
            code = f"VALIDATION_ERROR_{field.upper()}"
        super().__init__(message, code, 400)

class UnauthorizedError(VideoAIException):
    """Unauthorized access error."""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, "UNAUTHORIZED", 401)

class ForbiddenError(VideoAIException):
    """Forbidden access error."""
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, "FORBIDDEN", 403)

class NotFoundError(VideoAIException):
    """Resource not found error."""
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", "NOT_FOUND", 404)

class RateLimitExceeded(VideoAIException):
    """Rate limit exceeded error."""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "RATE_LIMIT_EXCEEDED", 429)

class TierLimitExceeded(VideoAIException):
    """Tier limit exceeded error."""
    def __init__(self, limit_type: str, current: int, limit: int):
        message = f"{limit_type} limit exceeded: {current}/{limit}"
        super().__init__(message, "TIER_LIMIT_EXCEEDED", 403)

class InsufficientCreditsError(VideoAIException):
    """Insufficient credits error."""
    def __init__(self, current: int, required: int):
        message = f"Insufficient credits: {current}/{required}"
        super().__init__(message, "INSUFFICIENT_CREDITS", 403)

class ProcessingError(VideoAIException):
    """Video processing error."""
    def __init__(self, message: str, step: str = None):
        self.step = step
        code = "PROCESSING_ERROR"
        if step:
            code = f"PROCESSING_ERROR_{step.upper()}"
        super().__init__(message, code, 500)

class ExternalServiceError(VideoAIException):
    """External service error."""
    def __init__(self, service: str, message: str):
        self.service = service
        super().__init__(f"{service} error: {message}", f"EXTERNAL_SERVICE_ERROR_{service.upper()}", 502)

class FileUploadError(VideoAIException):
    """File upload error."""
    def __init__(self, message: str):
        super().__init__(message, "FILE_UPLOAD_ERROR", 400)

class VideoTooLargeError(VideoAIException):
    """Video file too large error."""
    def __init__(self, max_size_mb: int):
        message = f"Video file too large. Maximum size is {max_size_mb}MB"
        super().__init__(message, "VIDEO_TOO_LARGE", 413)

class InvalidVideoFormatError(VideoAIException):
    """Invalid video format error."""
    def __init__(self, allowed_formats: list):
        formats = ", ".join(allowed_formats)
        message = f"Invalid video format. Allowed formats: {formats}"
        super().__init__(message, "INVALID_VIDEO_FORMAT", 400)

class SilentVideoDetected(VideoAIException):
    """Silent video detected (not an error, but a special case)."""
    def __init__(self, message: str = "Silent video detected"):
        super().__init__(message, "SILENT_VIDEO_DETECTED", 200)

class SubscriptionError(VideoAIException):
    """Subscription related error."""
    def __init__(self, message: str):
        super().__init__(message, "SUBSCRIPTION_ERROR", 400)

class PaymentError(VideoAIException):
    """Payment processing error."""
    def __init__(self, message: str):
        super().__init__(message, "PAYMENT_ERROR", 400)

class WebSocketError(VideoAIException):
    """WebSocket related error."""
    def __init__(self, message: str):
        super().__init__(message, "WEBSOCKET_ERROR", 400)

class DatabaseError(VideoAIException):
    """Database error."""
    def __init__(self, message: str):
        super().__init__(message, "DATABASE_ERROR", 500)

class ConfigurationError(VideoAIException):
    """Configuration error."""
    def __init__(self, message: str):
        super().__init__(message, "CONFIGURATION_ERROR", 500)

def handle_exception(error: Exception) -> tuple:
    """
    Handle exceptions and return appropriate HTTP response.
    This should be registered with Flask's error handler.
    """
    if isinstance(error, VideoAIException):
        response = {
            "error": {
                "code": error.code,
                "message": error.message,
                "status_code": error.status_code
            }
        }
        
        # Add field information for validation errors
        if isinstance(error, ValidationError) and error.field:
            response["error"]["field"] = error.field
        
        # Add step information for processing errors
        if isinstance(error, ProcessingError) and error.step:
            response["error"]["step"] = error.step
        
        # Add service information for external service errors
        if isinstance(error, ExternalServiceError):
            response["error"]["service"] = error.service
        
        return response, error.status_code
    
    # Handle unexpected errors
    response = {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "status_code": 500
        }
    }
    
    # In development mode, include the actual error message
    import os
    if os.getenv('FLASK_ENV') == 'development':
        response["error"]["detail"] = str(error)
        import traceback
        response["error"]["traceback"] = traceback.format_exc()
    
    return response, 500