"""Monitoring package initialization."""

from .metrics import init_metrics, record_metric, get_metrics
from .tracing import init_tracing, trace_span
from .alerts import init_alerts, get_alert_manager


def init_monitoring(app):
    """Initialize all monitoring components."""

    # Initialize metrics
    init_metrics(app)

    # Initialize tracing if configured
    if app.config.get("ENABLE_TRACING", False):
        init_tracing(app)

    # Initialize alerts
    alert_manager = init_alerts(app)

    # Store in app context
    app.alert_manager = alert_manager

    # Register health check endpoint
    @app.route("/monitoring/health")
    def monitoring_health():
        from flask import jsonify

        return jsonify(
            {
                "status": "healthy",
                "metrics": True,
                "alerts": alert_manager is not None,
                "tracing": app.config.get("ENABLE_TRACING", False),
            }
        )

    return app


def check_alerts():
    """
    Check alert rules.

    This is a wrapper around AlertManager.check_rules().
    Should be called with metrics data, typically from a background task.
    """
    manager = get_alert_manager()
    if manager:
        # In a real implementation, this would be called with metrics
        # For now, it's a placeholder
        return manager.alert_history
    return []


def send_alert(alert_name: str, data: dict, severity: str = "warning"):
    """
    Send an alert.

    Args:
        alert_name: Name of the alert to trigger
        data: Alert data/payload
        severity: Alert severity (critical, warning, info)
    """
    manager = get_alert_manager()
    if manager:
        manager.trigger_alert(alert_name, data, severity)


# For backward compatibility
__all__ = [
    "init_monitoring",
    "init_metrics",
    "record_metric",
    "get_metrics",
    "init_tracing",
    "trace_span",
    "init_alerts",
    "get_alert_manager",
    "check_alerts",
    "send_alert",
]
