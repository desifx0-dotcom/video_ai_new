"""Alert management and notification system."""

import os
import json
import smtplib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from core.logging import logger
from core.exceptions import ConfigurationError


class AlertManager:
    """Alert management system."""

    def __init__(self, app=None):
        self.alerts = []
        self.alert_handlers = {}
        self.alert_history = []
        self.app = app

        # Load alert configuration
        self.config = self._load_config()

        # Initialize alert handlers
        self._init_handlers()

    def _load_config(self) -> Dict[str, Any]:
        """Load alert configuration."""
        config_file = Path(__file__).parent.parent.parent / "config" / "alerts.json"

        default_config = {
            "enabled": True,
            "channels": ["log", "console"],
            "rules": [
                {
                    "name": "high_error_rate",
                    "condition": "error_rate > 0.1",
                    "threshold": 0.1,
                    "window": "5m",
                    "channels": ["email", "slack"],
                },
                {
                    "name": "slow_processing",
                    "condition": "processing_time > 300",
                    "threshold": 300,
                    "window": "5m",
                    "channels": ["email"],
                },
            ],
        }

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    return {**default_config, **config}
            except Exception as e:
                logger.error(f"Failed to load alert config: {e}")

        return default_config

    def _init_handlers(self):
        """Initialize alert handlers."""
        self.alert_handlers = {
            "log": self._handle_log_alert,
            "console": self._handle_console_alert,
            "email": self._handle_email_alert,
            "slack": self._handle_slack_alert,
            "webhook": self._handle_webhook_alert,
        }

    def register_alert(self, alert: Dict[str, Any]):
        """Register a new alert."""
        self.alerts.append(alert)
        logger.info(f"Registered alert: {alert.get('name')}")

    def trigger_alert(
        self, alert_name: str, data: Dict[str, Any], severity: str = "warning"
    ):
        """Trigger an alert."""
        alert = self._find_alert(alert_name)
        if not alert:
            logger.warning(f"Alert '{alert_name}' not found")
            return

        # Create alert instance
        alert_instance = {
            "name": alert_name,
            "severity": severity,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "message": alert.get("message", f"Alert triggered: {alert_name}"),
        }

        # Add to history
        self.alert_history.append(alert_instance)

        # Trim history
        self._trim_history()

        # Notify through channels
        channels = alert.get("channels", self.config.get("channels", ["log"]))
        for channel in channels:
            handler = self.alert_handlers.get(channel)
            if handler:
                try:
                    handler(alert_instance)
                except Exception as e:
                    logger.error(f"Alert handler '{channel}' failed: {e}")

    def _find_alert(self, alert_name: str) -> Optional[Dict[str, Any]]:
        """Find alert by name."""
        for alert in self.alerts:
            if alert.get("name") == alert_name:
                return alert

        # Check rules
        for rule in self.config.get("rules", []):
            if rule.get("name") == alert_name:
                return rule

        return None

    def _handle_log_alert(self, alert: Dict[str, Any]):
        """Handle alert by logging it."""
        log_level = getattr(logger, alert.get("severity", "warning"))
        log_level(
            f"ALERT [{alert['severity'].upper()}]: {alert['message']} - Data: {alert['data']}"
        )

    def _handle_console_alert(self, alert: Dict[str, Any]):
        """Handle alert by printing to console."""
        print(f"\n🔔 ALERT [{alert['severity'].upper()}]: {alert['message']}")
        print(f"   Data: {alert['data']}")
        print(f"   Time: {alert['timestamp']}\n")

    def _handle_email_alert(self, alert: Dict[str, Any]):
        """Handle alert by sending email."""
        try:
            # Import here to avoid circular imports
            from services.email_service import EmailService

            # Get email configuration
            email_config = self.config.get("email", {})
            if not email_config.get("enabled"):
                logger.debug("Email alerts disabled")
                return

            # Create email content
            subject = f"[{alert['severity'].upper()}] Alert: {alert['name']}"

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .alert {{ border: 1px solid #ddd; padding: 20px; border-radius: 5px; }}
                    .critical {{ background: #fee; border-color: #f99; }}
                    .warning {{ background: #ffe; border-color: #ff9; }}
                    .info {{ background: #eef; border-color: #99f; }}
                    .header {{ font-size: 20px; font-weight: bold; margin-bottom: 10px; }}
                    .data {{ background: #f5f5f5; padding: 10px; border-radius: 3px; font-family: monospace; }}
                </style>
            </head>
            <body>
                <div class="alert {alert['severity']}">
                    <div class="header">Alert: {alert['name']}</div>
                    <p><strong>Severity:</strong> {alert['severity'].upper()}</p>
                    <p><strong>Message:</strong> {alert['message']}</p>
                    <p><strong>Time:</strong> {alert['timestamp']}</p>
                    <div class="data">
                        <pre>{json.dumps(alert['data'], indent=2)}</pre>
                    </div>
                </div>
            </body>
            </html>
            """

            # Send email
            email_service = EmailService()
            email_service.send_email(
                to_email=email_config.get("recipient", "admin@videoaistudio.com"),
                subject=subject,
                html_content=html_content,
            )

            logger.info(f"Alert email sent for {alert['name']}")

        except ImportError as e:
            logger.error(f"Email service not available: {e}")
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")

    def _handle_slack_alert(self, alert: Dict[str, Any]):
        """Handle alert by sending to Slack."""
        try:
            import requests

            slack_config = self.config.get("slack", {})
            if not slack_config.get("enabled") or not slack_config.get("webhook_url"):
                logger.debug("Slack alerts disabled")
                return

            # Determine color based on severity
            colors = {"critical": "#ff0000", "warning": "#ff9900", "info": "#36a64f"}

            # Create Slack message
            payload = {
                "attachments": [
                    {
                        "color": colors.get(alert["severity"], "#ff9900"),
                        "title": f"[{alert['severity'].upper()}] Alert: {alert['name']}",
                        "text": alert["message"],
                        "fields": [
                            {
                                "title": "Timestamp",
                                "value": alert["timestamp"],
                                "short": True,
                            },
                            {
                                "title": "Data",
                                "value": f"```{json.dumps(alert['data'], indent=2)}```",
                                "short": False,
                            },
                        ],
                        "footer": "Video AI Studio Monitoring",
                        "ts": datetime.utcnow().timestamp(),
                    }
                ]
            }

            # Send to Slack
            response = requests.post(
                slack_config["webhook_url"], json=payload, timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Slack alert sent for {alert['name']}")
            else:
                logger.error(f"Failed to send Slack alert: {response.status_code}")

        except ImportError:
            logger.error("Requests library not available for Slack alerts")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    def _handle_webhook_alert(self, alert: Dict[str, Any]):
        """Handle alert by calling a webhook."""
        try:
            import requests

            webhook_config = self.config.get("webhook", {})
            if not webhook_config.get("enabled") or not webhook_config.get("url"):
                logger.debug("Webhook alerts disabled")
                return

            # Send webhook
            response = requests.post(
                webhook_config["url"],
                json={
                    "alert": alert,
                    "timestamp": alert["timestamp"],
                    "severity": alert["severity"],
                    "name": alert["name"],
                    "message": alert["message"],
                    "data": alert["data"],
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.status_code in [200, 201, 202]:
                logger.info(f"Webhook alert sent for {alert['name']}")
            else:
                logger.error(
                    f"Webhook returned {response.status_code}: {response.text}"
                )

        except ImportError:
            logger.error("Requests library not available for webhook alerts")
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")

    def _trim_history(self, max_history: int = 1000):
        """Trim alert history to avoid memory issues."""
        if len(self.alert_history) > max_history:
            self.alert_history = self.alert_history[-max_history:]

    def check_rules(self, metrics: Dict[str, Any]):
        """Check alert rules against metrics."""
        for rule in self.config.get("rules", []):
            if self._evaluate_rule(rule, metrics):
                self.trigger_alert(
                    rule["name"], {"metrics": metrics, "rule": rule}, severity="warning"
                )

    def _evaluate_rule(self, rule: Dict[str, Any], metrics: Dict[str, Any]) -> bool:
        """Evaluate a rule condition."""
        try:
            # Simple evaluation - can be enhanced with actual expression evaluation
            condition = rule.get("condition", "")

            # Extract metric name and threshold
            if "error_rate" in condition and "error_rate" in metrics:
                threshold = rule.get("threshold", 0.1)
                return metrics["error_rate"] > threshold

            elif "processing_time" in condition and "processing_time" in metrics:
                threshold = rule.get("threshold", 300)
                return metrics["processing_time"] > threshold

            return False

        except Exception as e:
            logger.error(f"Failed to evaluate rule {rule.get('name')}: {e}")
            return False

    def get_alerts(
        self, since: Optional[datetime] = None, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get alert history."""
        alerts = self.alert_history

        if since:
            alerts = [
                a for a in alerts if datetime.fromisoformat(a["timestamp"]) >= since
            ]

        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        return alerts

    def clear_alerts(self):
        """Clear alert history."""
        self.alert_history.clear()
        logger.info("Alert history cleared")


# Initialize alert manager (singleton)
_alert_manager = None


def get_alert_manager() -> AlertManager:
    """Get the alert manager singleton."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def init_alerts(app):
    """Initialize alerts with Flask app."""
    global _alert_manager

    # Create alert manager
    alert_manager = get_alert_manager()
    alert_manager.app = app

    # Register basic alerts
    register_basic_alerts(alert_manager)

    logger.info("Alerts initialized")
    return alert_manager


def register_basic_alerts(alert_manager):
    """Register basic alerts."""

    # System health alert
    alert_manager.register_alert(
        {
            "name": "system_health",
            "message": "System health check failed",
            "severity": "critical",
            "channels": ["log", "email"],
        }
    )

    # Database connection alert
    alert_manager.register_alert(
        {
            "name": "database_connection",
            "message": "Database connection issue detected",
            "severity": "critical",
            "channels": ["log", "email"],
        }
    )

    # API rate limit alert
    alert_manager.register_alert(
        {
            "name": "api_rate_limit",
            "message": "API rate limit approaching threshold",
            "severity": "warning",
            "channels": ["log", "console"],
        }
    )

    # Video processing alert
    alert_manager.register_alert(
        {
            "name": "video_processing",
            "message": "Video processing errors detected",
            "severity": "warning",
            "channels": ["log", "email"],
        }
    )

    # Storage space alert
    alert_manager.register_alert(
        {
            "name": "storage_space",
            "message": "Storage space running low",
            "severity": "warning",
            "channels": ["log", "email"],
        }
    )
