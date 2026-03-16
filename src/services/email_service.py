"""
Email service with provider abstraction.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from core.exceptions import ConfigurationError, ExternalServiceError
from core.constants import EmailProvider
from providers.email_provider import EmailProvider as EmailProviderImpl

logger = logging.getLogger(__name__)

class EmailService:
    """Email service with provider abstraction."""
    
    def __init__(self):
        self.provider_name = os.getenv('EMAIL_PROVIDER', 'console').lower()
        self.provider = EmailProviderImpl.get_provider(self.provider_name)
        
        # Template directory
        self.template_dir = Path(__file__).parent.parent.parent / 'templates' / 'email'
        
        # Ensure template directory exists
        self.template_dir.mkdir(parents=True, exist_ok=True)
    
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content
            text_content: Plain text content (optional)
            from_email: Sender email address
            reply_to: Reply-to email address
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of attachments
            metadata: Additional metadata
        
        Returns:
            Send result
        """
        try:
            result = self.provider.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                from_email=from_email,
                reply_to=reply_to,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                metadata=metadata
            )
            
            logger.info(f"Email sent to {to_email}: {subject}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            raise ExternalServiceError("Email", str(e))
    
    def send_template_email(
        self,
        template_name: str,
        to_email: str,
        template_data: Dict[str, Any],
        subject: Optional[str] = None,
        from_email: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send email using a template.
        
        Args:
            template_name: Name of the template
            to_email: Recipient email address
            template_data: Data for template rendering
            subject: Email subject (optional, can be in template)
            from_email: Sender email address
            **kwargs: Additional arguments for send_email
        
        Returns:
            Send result
        """
        # Load template
        template = self._load_template(template_name)
        
        # Render template with data
        html_content = self._render_template(template['html'], template_data)
        text_content = self._render_template(template['text'], template_data) if template.get('text') else None
        
        # Use template subject if not provided
        if not subject and template.get('subject'):
            subject = self._render_template(template['subject'], template_data)
        
        # Send email
        return self.send_email(
            to_email=to_email,
            subject=subject or f"Message from {os.getenv('APP_NAME', 'Video AI Studio')}",
            html_content=html_content,
            text_content=text_content,
            from_email=from_email or os.getenv('DEFAULT_FROM_EMAIL', 'noreply@videoaistudio.com'),
            **kwargs
        )
    
    def send_welcome_email(self, user_email: str, user_name: Optional[str] = None) -> Dict[str, Any]:
        """Send welcome email to new user."""
        template_data = {
            'user_email': user_email,
            'user_name': user_name or 'User',
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='welcome',
            to_email=user_email,
            template_data=template_data,
            subject=f"Welcome to {template_data['app_name']}!"
        )
    
    def send_verification_email(self, user_email: str, verification_url: str) -> Dict[str, Any]:
        """Send email verification email."""
        template_data = {
            'user_email': user_email,
            'verification_url': verification_url,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'expiry_hours': 24,
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='verify_email',
            to_email=user_email,
            template_data=template_data,
            subject=f"Verify your email for {template_data['app_name']}"
        )
    
    def send_password_reset_email(self, user_email: str, reset_url: str) -> Dict[str, Any]:
        """Send password reset email."""
        template_data = {
            'user_email': user_email,
            'reset_url': reset_url,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'expiry_hours': 1,
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='password_reset',
            to_email=user_email,
            template_data=template_data,
            subject=f"Reset your password for {template_data['app_name']}"
        )
    
    def send_video_processed_email(
        self,
        user_email: str,
        video_title: str,
        video_url: str,
        thumbnail_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send video processed notification email."""
        template_data = {
            'user_email': user_email,
            'video_title': video_title,
            'video_url': video_url,
            'thumbnail_url': thumbnail_url,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='video_processed',
            to_email=user_email,
            template_data=template_data,
            subject=f"Your video '{video_title}' is ready!"
        )
    
    def send_tier_upgrade_email(
        self,
        user_email: str,
        old_tier: str,
        new_tier: str,
        upgrade_date: str
    ) -> Dict[str, Any]:
        """Send tier upgrade confirmation email."""
        template_data = {
            'user_email': user_email,
            'old_tier': old_tier,
            'new_tier': new_tier,
            'upgrade_date': upgrade_date,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='tier_upgrade',
            to_email=user_email,
            template_data=template_data,
            subject=f"Welcome to {new_tier} tier!"
        )
    
    def send_payment_receipt_email(
        self,
        user_email: str,
        amount: float,
        currency: str,
        description: str,
        transaction_id: str,
        invoice_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send payment receipt email."""
        template_data = {
            'user_email': user_email,
            'amount': amount,
            'currency': currency,
            'description': description,
            'transaction_id': transaction_id,
            'invoice_url': invoice_url,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'current_year': datetime.now().year,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return self.send_template_email(
            template_name='payment_receipt',
            to_email=user_email,
            template_data=template_data,
            subject=f"Payment receipt for {template_data['app_name']}"
        )
    
    def send_credits_low_email(self, user_email: str, current_credits: int, tier: str) -> Dict[str, Any]:
        """Send low credits warning email."""
        template_data = {
            'user_email': user_email,
            'current_credits': current_credits,
            'tier': tier,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'upgrade_url': f"{os.getenv('APP_URL', 'https://app.videoaistudio.com')}/billing/upgrade",
            'credits_url': f"{os.getenv('APP_URL', 'https://app.videoaistudio.com')}/credits",
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='credits_low',
            to_email=user_email,
            template_data=template_data,
            subject=f"Low credits warning for {template_data['app_name']}"
        )
    
    def send_monthly_summary_email(
        self,
        user_email: str,
        user_name: str,
        month: str,
        videos_processed: int,
        total_processing_time: float,
        credits_used: int,
        credits_remaining: int
    ) -> Dict[str, Any]:
        """Send monthly summary email."""
        template_data = {
            'user_email': user_email,
            'user_name': user_name,
            'month': month,
            'videos_processed': videos_processed,
            'total_processing_time': total_processing_time,
            'credits_used': credits_used,
            'credits_remaining': credits_remaining,
            'app_name': os.getenv('APP_NAME', 'Video AI Studio'),
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@videoaistudio.com'),
            'dashboard_url': f"{os.getenv('APP_URL', 'https://app.videoaistudio.com')}/dashboard",
            'current_year': datetime.now().year
        }
        
        return self.send_template_email(
            template_name='monthly_summary',
            to_email=user_email,
            template_data=template_data,
            subject=f"Your {month} summary for {template_data['app_name']}"
        )
    
    def _load_template(self, template_name: str) -> Dict[str, str]:
        """Load email template from file."""
        template_files = {
            'html': self.template_dir / f"{template_name}.html",
            'text': self.template_dir / f"{template_name}.txt",
            'subject': self.template_dir / f"{template_name}.subject.txt"
        }
        
        template = {}
        
        for key, filepath in template_files.items():
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    template[key] = f.read()
            elif key == 'html':
                # Create default HTML template
                template[key] = self._create_default_template(template_name)
            elif key == 'text':
                # Create default text template from HTML
                if 'html' in template:
                    template[key] = self._html_to_text(template['html'])
        
        return template
    
    def _create_default_template(self, template_name: str) -> str:
        """Create default email template."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{template_name.replace('_', ' ').title()}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Video AI Studio</h1>
                <p>AI-Powered Video Processing</p>
            </div>
            <div class="content">
                <h2>{{subject}}</h2>
                <p>Hello {{user_name}},</p>
                <p>This is a notification from Video AI Studio.</p>
                <div style="text-align: center;">
                    <a href="{{action_url}}" class="button">Take Action</a>
                </div>
                <p>If you have any questions, please contact our support team.</p>
                <p>Best regards,<br>The Video AI Studio Team</p>
            </div>
            <div class="footer">
                <p>&copy; {{current_year}} Video AI Studio. All rights reserved.</p>
                <p><a href="{{unsubscribe_url}}">Unsubscribe</a> | <a href="{{preferences_url}}">Email Preferences</a></p>
            </div>
        </body>
        </html>
        """
    
    def _render_template(self, template: str, data: Dict[str, Any]) -> str:
        """Render template with data using simple string replacement."""
        rendered = template
        for key, value in data.items():
            placeholder = f'{{{{{key}}}}}'
            rendered = rendered.replace(placeholder, str(value))
        return rendered
    
    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (simplified)."""
        import re
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html)
        
        # Replace common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        
        # Collapse multiple whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Trim and return
        return text.strip()
    
    def validate_email_address(self, email: str) -> bool:
        """Validate email address format."""
        import re
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))