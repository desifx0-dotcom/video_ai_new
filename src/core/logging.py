"""
Structured logging setup.
"""

import logging
import sys
import json
from datetime import datetime
from pythonjsonlogger import jsonlogger
from typing import Dict, Any, Optional
import uuid
import os
import socket


class StructuredJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ):
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record["timestamp"] = datetime.utcnow().isoformat()

        # Add log level
        log_record["level"] = record.levelname

        # Add module and function
        log_record["module"] = record.module
        log_record["function"] = record.funcName

        # Add process and thread information
        log_record["process"] = record.process
        log_record["thread"] = record.threadName

        # Remove default fields we don't need
        log_record.pop("message", None)
        log_record.pop("asctime", None)

        # Rename 'msg' to 'message'
        if "msg" in log_record:
            log_record["message"] = log_record.pop("msg")

            # Service identification
        log_record["service"] = "video-ai-studio"
        log_record["environment"] = os.getenv("FLASK_ENV", "production")
        log_record["version"] = "1.0.0"  # Get from __version__ file
        log_record["hostname"] = socket.gethostname()

        # Request context (if available in Flask)
        try:
            from flask import request, g, has_request_context

            if has_request_context():
                log_record["request_id"] = request.headers.get("X-Request-ID", "")
                log_record["user_id"] = getattr(g, "user_id", None)
                log_record["path"] = request.path
                log_record["method"] = request.method
                log_record["ip"] = request.remote_addr
                log_record["user_agent"] = (
                    request.user_agent.string[:100] if request.user_agent else None
                )

                # Add correlation ID for request tracing
                if not hasattr(g, "correlation_id"):
                    g.correlation_id = str(uuid.uuid4())
                log_record["correlation_id"] = g.correlation_id

        except (RuntimeError, ImportError):
            # Outside request context
            pass

        # Performance metrics (if available in record)
        if hasattr(record, "duration_ms"):
            log_record["duration_ms"] = record.duration_ms

        # Business context (if available in record)
        if hasattr(record, "user_tier"):
            log_record["user_tier"] = record.user_tier
        if hasattr(record, "video_id"):
            log_record["video_id"] = record.video_id
        if hasattr(record, "credits_used"):
            log_record["credits_used"] = record.credits_used

        # Error details for exceptions
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Remove default fields we don't need
        log_record.pop("message", None)
        log_record.pop("asctime", None)
        log_record.pop("exc_info", None)
        log_record.pop("stack_info", None)

        # Rename 'msg' to 'message' for clarity
        if "msg" in log_record:
            log_record["message"] = log_record.pop("msg")

        # Ensure no None values (some logging systems don't like them)
        for key, value in list(log_record.items()):
            if value is None:
                log_record[key] = ""


def setup_logging(
    level: str = "INFO", log_file: Optional[str] = None, json_format: bool = True
) -> None:
    """
    Set up structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file to write logs to
        json_format: Whether to use JSON formatting
    """
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)

    if json_format:
        # JSON formatter for structured logging
        formatter = StructuredJsonFormatter(
            "%(timestamp)s %(level)s %(module)s %(function)s %(message)s"
        )
        console_handler.setFormatter(formatter)
    else:
        # Simple formatter for development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    # Add file handler if log_file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))

        if json_format:
            file_handler.setFormatter(formatter)
        else:
            file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    # Configure third-party loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("schedule").setLevel(logging.WARNING)

    # Capture warnings
    logging.captureWarnings(True)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_id: Optional[str] = None,
    tier: Optional[str] = None,
    **extra_fields,
) -> None:
    """Log an HTTP request."""
    log_data = {
        "type": "http_request",
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "user_id": user_id,
        "tier": tier,
        **extra_fields,
    }
    logger.info(f"{method} {path} {status_code} {duration_ms:.2f}ms", extra=log_data)


def log_video_processing(
    logger: logging.Logger,
    video_id: str,
    user_id: str,
    tier: str,
    video_type: str,
    duration_seconds: float,
    processing_time_seconds: float,
    total_cost: float,
    status: str = "completed",
    **extra_fields,
) -> None:
    """Log video processing event."""
    log_data = {
        "type": "video_processing",
        "video_id": video_id,
        "user_id": user_id,
        "tier": tier,
        "video_type": video_type,
        "duration_seconds": duration_seconds,
        "processing_time_seconds": processing_time_seconds,
        "total_cost": total_cost,
        "status": status,
        **extra_fields,
    }
    logger.info(f"Video processed: {video_id} ({status})", extra=log_data)


def log_tier_upgrade(
    logger: logging.Logger,
    user_id: str,
    from_tier: str,
    to_tier: str,
    upgrade_price: float,
    **extra_fields,
) -> None:
    """Log tier upgrade event."""
    log_data = {
        "type": "tier_upgrade",
        "user_id": user_id,
        "from_tier": from_tier,
        "to_tier": to_tier,
        "upgrade_price": upgrade_price,
        **extra_fields,
    }
    logger.info(f"Tier upgrade: {user_id} {from_tier}→{to_tier}", extra=log_data)


def log_external_service_call(
    logger: logging.Logger,
    service: str,
    endpoint: str,
    duration_ms: float,
    success: bool,
    error_message: Optional[str] = None,
    **extra_fields,
) -> None:
    """Log external service call."""
    log_data = {
        "type": "external_service",
        "service": service,
        "endpoint": endpoint,
        "duration_ms": duration_ms,
        "success": success,
        "error_message": error_message,
        **extra_fields,
    }

    level = logging.INFO if success else logging.ERROR
    logger.log(level, f"{service} call to {endpoint}", extra=log_data)


def log_system_metric(
    logger: logging.Logger,
    metric_name: str,
    value: float,
    unit: str = "",
    **extra_fields,
) -> None:
    """Log system metric."""
    log_data = {
        "type": "system_metric",
        "metric_name": metric_name,
        "value": value,
        "unit": unit,
        **extra_fields,
    }
    logger.info(f"Metric: {metric_name}={value}{unit}", extra=log_data)


# Default logger instance
logger = get_logger(__name__)
