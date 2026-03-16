"""
Security utilities for the application.
"""
import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from cryptography.fernet import Fernet
import bcrypt

from .exceptions import UnauthorizedError, ValidationError

class SecurityUtils:
    """Security utility class."""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        # Generate salt and hash password
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def generate_api_key(length: int = 32) -> str:
        """Generate a secure API key."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_secure_token(length: int = 64) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def generate_jwt_token(
        payload: Dict[str, Any],
        secret_key: str,
        expires_in: timedelta = timedelta(hours=1)
    ) -> str:
        """Generate a JWT token."""
        payload = payload.copy()
        payload['exp'] = datetime.utcnow() + expires_in
        payload['iat'] = datetime.utcnow()
        
        return jwt.encode(payload, secret_key, algorithm='HS256')
    
    @staticmethod
    def verify_jwt_token(token: str, secret_key: str) -> Dict[str, Any]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token has expired")
        except jwt.InvalidTokenError:
            raise UnauthorizedError("Invalid token")
    
    @staticmethod
    def encrypt_data(data: str, encryption_key: bytes) -> str:
        """Encrypt data using Fernet symmetric encryption."""
        fernet = Fernet(encryption_key)
        encrypted = fernet.encrypt(data.encode('utf-8'))
        return encrypted.decode('utf-8')
    
    @staticmethod
    def decrypt_data(encrypted_data: str, encryption_key: bytes) -> str:
        """Decrypt data using Fernet symmetric encryption."""
        fernet = Fernet(encryption_key)
        decrypted = fernet.decrypt(encrypted_data.encode('utf-8'))
        return decrypted.decode('utf-8')
    
    @staticmethod
    def generate_encryption_key() -> bytes:
        """Generate a Fernet encryption key."""
        return Fernet.generate_key()
    
    @staticmethod
    def validate_api_key_format(api_key: str) -> bool:
        """Validate API key format."""
        if len(api_key) < 16 or len(api_key) > 128:
            return False
        
        # Check if it contains only allowed characters
        allowed_chars = string.ascii_letters + string.digits + '-_'
        return all(c in allowed_chars for c in api_key)
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize a filename to prevent path traversal attacks."""
        import os
        import re
        
        # Remove directory components
        filename = os.path.basename(filename)
        
        # Remove null bytes
        filename = filename.replace('\x00', '')
        
        # Remove any characters that could be used in path traversal
        filename = re.sub(r'[<>:"|?*\\/]', '_', filename)
        
        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255 - len(ext)] + ext
        
        return filename
    
    @staticmethod
    def validate_file_upload(
        filename: str,
        content_type: str,
        content_length: int,
        max_size: int,
        allowed_extensions: set,
        allowed_mime_types: set
    ) -> None:
        """Validate file upload for security."""
        # Check file size
        if content_length > max_size:
            raise ValidationError(
                f"File size exceeds maximum allowed size of {max_size / (1024 * 1024):.1f} MB",
                field="file"
            )
        
        # Check file extension
        import os
        ext = os.path.splitext(filename)[1].lower().lstrip('.')
        if ext not in allowed_extensions:
            raise ValidationError(
                f"File extension .{ext} not allowed. Allowed extensions: {', '.join(allowed_extensions)}",
                field="file"
            )
        
        # Check MIME type
        if content_type not in allowed_mime_types:
            raise ValidationError(
                f"File type {content_type} not allowed. Allowed types: {', '.join(allowed_mime_types)}",
                field="file"
            )
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Generate a CSRF token."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_csrf_token(token: str, expected_token: str) -> bool:
        """Verify a CSRF token using constant-time comparison."""
        return hmac.compare_digest(token, expected_token)
    
    @staticmethod
    def calculate_hmac(data: str, secret: str) -> str:
        """Calculate HMAC for data verification."""
        return hmac.new(
            secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    @staticmethod
    def verify_hmac(data: str, secret: str, expected_hmac: str) -> bool:
        """Verify HMAC for data integrity."""
        calculated_hmac = SecurityUtils.calculate_hmac(data, secret)
        return hmac.compare_digest(calculated_hmac, expected_hmac)

class RateLimiter:
    """Simple rate limiter implementation."""
    
    def __init__(self, redis_client, prefix: str = "rate_limit"):
        self.redis = redis_client
        self.prefix = prefix
    
    def is_rate_limited(self, key: str, limit: int, window_seconds: int) -> bool:
        """Check if rate limit is exceeded."""
        import time
        
        redis_key = f"{self.prefix}:{key}"
        current_time = int(time.time())
        window_start = current_time - window_seconds
        
        # Remove old entries
        self.redis.zremrangebyscore(redis_key, 0, window_start)
        
        # Count requests in current window
        request_count = self.redis.zcard(redis_key)
        
        if request_count >= limit:
            return True
        
        # Add current request
        self.redis.zadd(redis_key, {str(current_time): current_time})
        self.redis.expire(redis_key, window_seconds)
        
        return False
    
    def get_remaining_requests(self, key: str, limit: int, window_seconds: int) -> int:
        """Get remaining requests in current window."""
        import time
        
        redis_key = f"{self.prefix}:{key}"
        current_time = int(time.time())
        window_start = current_time - window_seconds
        
        # Remove old entries
        self.redis.zremrangebyscore(redis_key, 0, window_start)
        
        # Count requests in current window
        request_count = self.redis.zcard(redis_key)
        
        return max(0, limit - request_count)

# Global security utilities instance
security = SecurityUtils()