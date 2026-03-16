"""
Security configuration.
"""
import os
from typing import List

class SecurityConfig:
    """Security configuration settings."""
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', os.getenv('SECRET_KEY', 'default-secret-key'))
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 hour in seconds
    JWT_REFRESH_TOKEN_EXPIRES = 2592000  # 30 days in seconds
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'
    
    # Password hashing
    PASSWORD_HASH_ALGORITHM = 'bcrypt'
    PASSWORD_HASH_ROUNDS = 12
    
    # Rate limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_STRATEGY = 'fixed-window'
    RATE_LIMIT_STORAGE_URI = os.getenv('REDIS_URL', 'memory://')
    
    # CORS
    CORS_ENABLED = True
    CORS_ALLOW_ORIGINS = os.getenv('CORS_ALLOW_ORIGINS', '*').split(',')
    CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH']
    CORS_ALLOW_HEADERS = [
        'Content-Type',
        'Authorization',
        'X-Requested-With',
        'Accept',
        'Origin',
        'X-CSRF-Token'
    ]
    CORS_EXPOSE_HEADERS = [
        'Content-Range',
        'X-Content-Range',
        'X-RateLimit-Limit',
        'X-RateLimit-Remaining',
        'X-RateLimit-Reset'
    ]
    CORS_ALLOW_CREDENTIALS = True
    
    # File upload security
    ALLOWED_EXTENSIONS = {
        'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'mpeg', 'mpg',
        'm4v', '3gp', 'ogv'
    }
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    SCAN_FOR_MALWARE = os.getenv('SCAN_FOR_MALWARE', 'false').lower() == 'true'
    
    # Content Security Policy
    CSP_ENABLED = True
    CSP_DIRECTIVES = {
        'default-src': "'self'",
        'script-src': ["'self'", "'unsafe-inline'", "cdnjs.cloudflare.com"],
        'style-src': ["'self'", "'unsafe-inline'", "cdnjs.cloudflare.com"],
        'img-src': ["'self'", "data:", "blob:", "https:"],
        'font-src': ["'self'", "cdnjs.cloudflare.com"],
        'connect-src': ["'self'", "ws:", "wss:"],
        'frame-ancestors': "'none'",
        'form-action': "'self'",
        'base-uri': "'self'"
    }
    
    # HTTP Security Headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    }
    
    # API Security
    API_KEY_HEADER = 'X-API-Key'
    API_KEY_VALIDATION_ENABLED = True
    
    # Session Security
    SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV', 'development') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # Brute force protection
    LOGIN_ATTEMPTS_LIMIT = 5
    LOGIN_BLOCK_DURATION = 900  # 15 minutes in seconds
    
    # Audit logging
    AUDIT_LOG_ENABLED = True
    AUDIT_LOG_LEVEL = 'INFO'
    
    # Data sanitization
    SANITIZE_USER_INPUT = True
    SANITIZE_HTML = True
    
    # Encryption
    DATA_ENCRYPTION_ENABLED = os.getenv('ENABLE_DATA_ENCRYPTION', 'false').lower() == 'true'
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
    
    @classmethod
    def get_csp_header(cls) -> str:
        """Get Content Security Policy header."""
        if not cls.CSP_ENABLED:
            return ''
        
        directives = []
        for key, value in cls.CSP_DIRECTIVES.items():
            if isinstance(value, list):
                directives.append(f"{key} {' '.join(value)}")
            else:
                directives.append(f"{key} {value}")
        
        return '; '.join(directives)
    
    @classmethod
    def get_security_headers(cls) -> dict:
        """Get all security headers."""
        headers = cls.SECURITY_HEADERS.copy()
        
        if cls.CSP_ENABLED:
            headers['Content-Security-Policy'] = cls.get_csp_header()
        
        return headers