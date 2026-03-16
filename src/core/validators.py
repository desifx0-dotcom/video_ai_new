"""
Input validators for the application.
"""
import re
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import magic
from urllib.parse import urlparse

from .exceptions import ValidationError

class Validators:
    """Collection of input validators."""
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """Validate email address."""
        if not email:
            return False, "Email is required"
        
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(email_regex, email):
            return False, "Invalid email format"
        
        # Additional checks
        if len(email) > 254:
            return False, "Email is too long"
        
        # Check for disposable email domains (basic check)
        disposable_domains = {
            'tempmail.com', 'guerrillamail.com', 'mailinator.com',
            'sharklasers.com', 'grr.la', 'guerrillamail.net'
        }
        
        domain = email.split('@')[1].lower()
        if domain in disposable_domains:
            return False, "Disposable email addresses are not allowed"
        
        return True, ""
    
    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """Validate password strength."""
        if not password:
            return False, "Password is required"
        
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if len(password) > 128:
            return False, "Password is too long"
        
        # Check for at least one uppercase letter
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        # Check for at least one lowercase letter
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        # Check for at least one digit
        if not re.search(r'\d', password):
            return False, "Password must contain at least one digit"
        
        # Check for at least one special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        # Check for common passwords (basic check)
        common_passwords = {
            'password', '123456', '12345678', '123456789', 'qwerty',
            'abc123', 'password1', 'admin', 'welcome', 'monkey'
        }
        
        if password.lower() in common_passwords:
            return False, "Password is too common"
        
        return True, ""
    
    @staticmethod
    def validate_video_file(
        file_path: str,
        max_size_mb: int = 2048,  # 2GB
        allowed_extensions: Optional[List[str]] = None,
        check_mime_type: bool = True
    ) -> Tuple[bool, str]:
        """Validate video file."""
        if allowed_extensions is None:
            allowed_extensions = ['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'mpeg', 'mpg']
        
        # Check if file exists
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        # Check file size
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if file_size > max_size_bytes:
            return False, f"File size exceeds maximum allowed size of {max_size_mb}MB"
        
        if file_size == 0:
            return False, "File is empty"
        
        # Check file extension
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        if ext not in allowed_extensions:
            return False, f"File extension .{ext} not allowed. Allowed extensions: {', '.join(allowed_extensions)}"
        
        # Check MIME type if requested
        if check_mime_type:
            try:
                mime = magic.Magic(mime=True)
                mime_type = mime.from_file(file_path)
                
                allowed_mime_types = [
                    'video/mp4', 'video/x-msvideo', 'video/quicktime',
                    'video/x-matroska', 'video/webm', 'video/x-flv',
                    'video/x-ms-wmv', 'video/mpeg'
                ]
                
                if mime_type not in allowed_mime_types:
                    return False, f"File type {mime_type} not allowed"
            except Exception as e:
                # If we can't determine MIME type, proceed with extension check
                pass
        
        return True, ""
    
    @staticmethod
    def validate_video_duration(duration_seconds: float, max_minutes: int) -> Tuple[bool, str]:
        """Validate video duration."""
        max_seconds = max_minutes * 60
        
        if duration_seconds > max_seconds:
            return False, f"Video duration exceeds maximum allowed duration of {max_minutes} minutes"
        
        if duration_seconds <= 0:
            return False, "Video duration must be positive"
        
        if duration_seconds < 1:
            return False, "Video is too short"
        
        return True, ""
    
    @staticmethod
    def validate_tier(tier: str) -> Tuple[bool, str]:
        """Validate tier name."""
        valid_tiers = ['free', 'starter', 'pro', 'plus', 'enterprise']
        
        if tier.lower() not in valid_tiers:
            return False, f"Invalid tier. Valid tiers are: {', '.join(valid_tiers)}"
        
        return True, ""
    
    @staticmethod
    def validate_language_code(language_code: str) -> Tuple[bool, str]:
        """Validate language code."""
        # Basic validation - should be 2-3 letter code
        if not language_code:
            return False, "Language code is required"
        
        if not re.match(r'^[a-z]{2,3}(-[A-Z]{2,3})?$', language_code):
            return False, "Invalid language code format"
        
        return True, ""
    
    @staticmethod
    def validate_url(url: str, allowed_domains: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Validate URL."""
        if not url:
            return False, "URL is required"
        
        try:
            result = urlparse(url)
            
            if not all([result.scheme, result.netloc]):
                return False, "Invalid URL format"
            
            if result.scheme not in ['http', 'https']:
                return False, "URL must use http or https protocol"
            
            # Check against allowed domains if specified
            if allowed_domains:
                domain = result.netloc.lower()
                if domain not in allowed_domains:
                    return False, f"Domain not allowed: {domain}"
            
            return True, ""
        except Exception:
            return False, "Invalid URL"
    
    @staticmethod
    def validate_hex_color(color: str) -> Tuple[bool, str]:
        """Validate hex color code."""
        if not color:
            return False, "Color is required"
        
        color = color.lstrip('#')
        
        if len(color) not in [3, 6, 8]:
            return False, "Invalid hex color length"
        
        if not re.match(r'^[0-9A-Fa-f]+$', color):
            return False, "Invalid hex color characters"
        
        return True, ""
    
    @staticmethod
    def validate_date_string(date_str: str, format: str = "%Y-%m-%d") -> Tuple[bool, str]:
        """Validate date string."""
        if not date_str:
            return False, "Date is required"
        
        try:
            datetime.strptime(date_str, format)
            return True, ""
        except ValueError:
            return False, f"Invalid date format. Expected format: {format}"
    
    @staticmethod
    def validate_integer(value: Any, min_value: Optional[int] = None, 
                        max_value: Optional[int] = None) -> Tuple[bool, str]:
        """Validate integer value."""
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            return False, "Value must be an integer"
        
        if min_value is not None and int_value < min_value:
            return False, f"Value must be at least {min_value}"
        
        if max_value is not None and int_value > max_value:
            return False, f"Value must be at most {max_value}"
        
        return True, ""
    
    @staticmethod
    def validate_float(value: Any, min_value: Optional[float] = None,
                      max_value: Optional[float] = None) -> Tuple[bool, str]:
        """Validate float value."""
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            return False, "Value must be a number"
        
        if min_value is not None and float_value < min_value:
            return False, f"Value must be at least {min_value}"
        
        if max_value is not None and float_value > max_value:
            return False, f"Value must be at most {max_value}"
        
        return True, ""
    
    @staticmethod
    def validate_string(value: Any, min_length: Optional[int] = None,
                       max_length: Optional[int] = None,
                       allowed_chars: Optional[str] = None) -> Tuple[bool, str]:
        """Validate string value."""
        if not isinstance(value, str):
            return False, "Value must be a string"
        
        if min_length is not None and len(value) < min_length:
            return False, f"String must be at least {min_length} characters long"
        
        if max_length is not None and len(value) > max_length:
            return False, f"String must be at most {max_length} characters long"
        
        if allowed_chars is not None:
            if not all(c in allowed_chars for c in value):
                return False, f"String contains invalid characters. Allowed: {allowed_chars}"
        
        return True, ""
    
    @staticmethod
    def validate_list(value: Any, min_items: Optional[int] = None,
                     max_items: Optional[int] = None,
                     item_validator: Optional[callable] = None) -> Tuple[bool, str]:
        """Validate list value."""
        if not isinstance(value, list):
            return False, "Value must be a list"
        
        if min_items is not None and len(value) < min_items:
            return False, f"List must contain at least {min_items} items"
        
        if max_items is not None and len(value) > max_items:
            return False, f"List must contain at most {max_items} items"
        
        if item_validator is not None:
            for i, item in enumerate(value):
                is_valid, error = item_validator(item)
                if not is_valid:
                    return False, f"Item {i}: {error}"
        
        return True, ""
    
    @staticmethod
    def validate_dict(value: Any, required_keys: Optional[List[str]] = None,
                     key_validators: Optional[Dict[str, callable]] = None) -> Tuple[bool, str]:
        """Validate dictionary value."""
        if not isinstance(value, dict):
            return False, "Value must be a dictionary"
        
        if required_keys is not None:
            for key in required_keys:
                if key not in value:
                    return False, f"Missing required key: {key}"
        
        if key_validators is not None:
            for key, validator in key_validators.items():
                if key in value:
                    is_valid, error = validator(value[key])
                    if not is_valid:
                        return False, f"Key '{key}': {error}"
        
        return True, ""

class ValidationErrorBuilder:
    """Helper for building validation error messages."""
    
    def __init__(self):
        self.errors = {}
    
    def add_error(self, field: str, message: str):
        """Add an error for a field."""
        if field not in self.errors:
            self.errors[field] = []
        self.errors[field].append(message)
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return bool(self.errors)
    
    def raise_if_errors(self):
        """Raise ValidationError if there are any errors."""
        if self.has_errors():
            # Combine all error messages
            messages = []
            for field, errors in self.errors.items():
                for error in errors:
                    messages.append(f"{field}: {error}")
            
            raise ValidationError("; ".join(messages))
    
    def to_dict(self) -> Dict[str, List[str]]:
        """Convert errors to dictionary."""
        return self.errors.copy()

# Global validators instance
validators = Validators()