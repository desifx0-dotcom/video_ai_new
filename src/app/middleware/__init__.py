"""
Middleware package.
"""
from .auth import jwt_required, get_current_user
from .logging import log_request, log_response
from .rate_limit import tier_based_rate_limit
from .cors import setup_cors
from .compression import setup_compression

def register_middleware(app):
    """Register all middleware."""
    
    # Request/Response logging
    app.before_request(log_request)
    app.after_request(log_response)
    
    # CORS
    setup_cors(app)
    
    # Compression
    setup_compression(app)
    
    return app