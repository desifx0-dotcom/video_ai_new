"""
Email provider abstraction.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from datetime import datetime
import json
from core.exceptions import ExternalServiceError
from core.constants import EmailProvider

logger = logging.getLogger(__name__)


class BaseEmailProvider(ABC):
    """Base email provider interface."""

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send an email."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test email provider connection."""
        pass


class SendGridProvider(BaseEmailProvider):
    """SendGrid email provider."""

    def __init__(self, api_key: Optional[str] = None):
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Content, Attachment

        self.api_key = api_key or os.getenv("SENDGRID_API_KEY")

        if not self.api_key:
            raise ExternalServiceError("SendGrid", "API key not configured")

        self.client = SendGridAPIClient(self.api_key)
        self.Mail = Mail
        self.Content = Content
        self.Attachment = Attachment

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send email using SendGrid."""
        try:
            # Create email
            from_email = from_email or os.getenv(
                "DEFAULT_FROM_EMAIL", "noreply@videoaistudio.com"
            )
            from_name = os.getenv("DEFAULT_FROM_NAME", "Video AI Studio")

            mail = self.Mail(
                from_email=(from_email, from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html_content,
            )

            # Add text content if provided
            if text_content:
                mail.add_content(self.Content("text/plain", text_content))

            # Add reply-to
            if reply_to:
                mail.reply_to = reply_to

            # Add CC
            if cc:
                for email in cc:
                    mail.add_cc(email)

            # Add BCC
            if bcc:
                for email in bcc:
                    mail.add_bcc(email)

            # Add attachments
            if attachments:
                for attachment in attachments:
                    sg_attachment = self.Attachment()

                    if "content" in attachment:
                        sg_attachment.file_content = attachment["content"]
                    elif "path" in attachment:
                        with open(attachment["path"], "rb") as f:
                            sg_attachment.file_content = f.read()

                    sg_attachment.file_type = attachment.get(
                        "type", "application/octet-stream"
                    )
                    sg_attachment.file_name = attachment.get("filename", "attachment")
                    sg_attachment.disposition = attachment.get(
                        "disposition", "attachment"
                    )

                    mail.add_attachment(sg_attachment)

            # Add metadata
            if metadata:
                mail.add_custom_arg("metadata", json.dumps(metadata))

            # Send email
            response = self.client.send(mail)

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "message_id": response.headers.get("X-Message-Id"),
                "provider": "sendgrid",
            }

        except Exception as e:
            logger.error(f"SendGrid email failed: {str(e)}")
            raise ExternalServiceError("SendGrid", str(e))

    def test_connection(self) -> bool:
        """Test SendGrid connection."""
        try:
            # Try to get API key stats
            response = self.client.client.stats.get()
            return response.status_code == 200
        except Exception as e:
            logger.error(f"SendGrid connection test failed: {str(e)}")
            return False


class ResendProvider(BaseEmailProvider):
    """Resend email provider."""

    def __init__(self, api_key: Optional[str] = None):
        import resend

        self.api_key = api_key or os.getenv("RESEND_API_KEY")

        if not self.api_key:
            raise ExternalServiceError("Resend", "API key not configured")

        resend.api_key = self.api_key
        self.resend = resend

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send email using Resend."""
        try:
            from_email = from_email or os.getenv(
                "DEFAULT_FROM_EMAIL", "noreply@videoaistudio.com"
            )

            params = {
                "from": from_email,
                "to": to_email,
                "subject": subject,
                "html": html_content,
            }

            if text_content:
                params["text"] = text_content

            if reply_to:
                params["reply_to"] = reply_to

            if cc:
                params["cc"] = cc

            if bcc:
                params["bcc"] = bcc

            if attachments:
                params["attachments"] = []
                for attachment in attachments:
                    att = {}

                    if "content" in attachment:
                        att["content"] = attachment["content"]
                    elif "path" in attachment:
                        with open(attachment["path"], "rb") as f:
                            att["content"] = f.read().decode("utf-8")

                    att["filename"] = attachment.get("filename", "attachment")
                    params["attachments"].append(att)

            # Send email
            response = self.resend.Emails.send(params)

            return {
                "id": response.get("id"),
                "from": response.get("from"),
                "to": response.get("to"),
                "created_at": response.get("created_at"),
                "provider": "resend",
            }

        except Exception as e:
            logger.error(f"Resend email failed: {str(e)}")
            raise ExternalServiceError("Resend", str(e))

    def test_connection(self) -> bool:
        """Test Resend connection."""
        try:
            # Try to get API key
            response = self.resend.ApiKeys.list()
            return True
        except Exception as e:
            logger.error(f"Resend connection test failed: {str(e)}")
            return False


class ConsoleEmailProvider(BaseEmailProvider):
    """Console email provider for development."""

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Print email to console (for development)."""
        print("\n" + "=" * 80)
        print("EMAIL TO CONSOLE (Development Only)")
        print("=" * 80)
        print(f"From: {from_email or 'noreply@videoaistudio.com'}")
        print(f"To: {to_email}")
        if cc:
            print(f"CC: {', '.join(cc)}")
        if bcc:
            print(f"BCC: {', '.join(bcc)}")
        print(f"Subject: {subject}")
        print("-" * 80)

        if text_content:
            print("TEXT CONTENT:")
            print(text_content)
            print("-" * 80)

        print("HTML CONTENT (preview):")
        # Extract text from HTML for preview
        import re

        text_preview = re.sub(r"<[^>]+>", "", html_content)
        print(text_preview[:200] + "..." if len(text_preview) > 200 else text_preview)

        if attachments:
            print(f"\nAttachments: {len(attachments)} file(s)")

        if metadata:
            print(f"\nMetadata: {metadata}")

        print("=" * 80 + "\n")

        return {
            "status": "printed_to_console",
            "provider": "console",
            "development": True,
        }

    def test_connection(self) -> bool:
        """Console provider always works."""
        return True


class MockEmailProvider(BaseEmailProvider):
    """Mock email provider for testing."""

    def __init__(self):
        self.sent_emails = []

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store email in memory (for testing)."""
        email_data = {
            "to_email": to_email,
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content,
            "from_email": from_email,
            "reply_to": reply_to,
            "cc": cc,
            "bcc": bcc,
            "attachments": attachments,
            "metadata": metadata,
            "sent_at": datetime.utcnow().isoformat(),
        }

        self.sent_emails.append(email_data)

        return {
            "status": "stored_in_memory",
            "provider": "mock",
            "email_count": len(self.sent_emails),
        }

    def get_sent_emails(self) -> List[Dict[str, Any]]:
        """Get all sent emails."""
        return self.sent_emails.copy()

    def clear_sent_emails(self):
        """Clear all sent emails."""
        self.sent_emails.clear()

    def test_connection(self) -> bool:
        """Mock provider always works."""
        return True


class EmailProvider:
    """Email provider factory."""

    @staticmethod
    def get_provider(provider_name: Optional[str] = None) -> BaseEmailProvider:
        """
        Get email provider by name.

        Args:
            provider_name: Provider name (sendgrid, resend, console, mock)

        Returns:
            Email provider instance
        """
        provider_name = provider_name or os.getenv("EMAIL_PROVIDER", "console").lower()

        providers = {
            "sendgrid": SendGridProvider,
            "resend": ResendProvider,
            "console": ConsoleEmailProvider,
            "mock": MockEmailProvider,
        }

        provider_class = providers.get(provider_name)

        if not provider_class:
            raise ExternalServiceError(
                "Email", f"Unsupported email provider: {provider_name}"
            )

        try:
            return provider_class()
        except Exception as e:
            logger.error(
                f"Failed to initialize email provider {provider_name}: {str(e)}"
            )
            # Fallback to console provider
            return ConsoleEmailProvider()

    @staticmethod
    def get_available_providers() -> List[Dict[str, str]]:
        """Get list of available email providers."""
        return [
            {"name": "sendgrid", "display_name": "SendGrid", "type": "production"},
            {"name": "resend", "display_name": "Resend", "type": "production"},
            {
                "name": "console",
                "display_name": "Console (Development)",
                "type": "development",
            },
            {"name": "mock", "display_name": "Mock (Testing)", "type": "testing"},
        ]
