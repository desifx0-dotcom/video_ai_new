"""
API v1 routers package - Complete production version.
"""

from flask import Blueprint
from .auth_public import public_auth_bp
from .auth import router as auth_router
from .videos import router as videos_router
from .users import router as users_router
from .billing import router as billing_router
from .webhooks import webhook_bp as webhooks_router
from .admin import admin_bp as admin_router

# Create main API blueprint
api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Register all routers
api_v1_bp.register_blueprint(public_auth_bp, url_prefix="/auth")
api_v1_bp.register_blueprint(auth_router, url_prefix="/auth/protected")
api_v1_bp.register_blueprint(videos_router, url_prefix="/videos")
api_v1_bp.register_blueprint(users_router, url_prefix="/users")
api_v1_bp.register_blueprint(billing_router, url_prefix="/billing")
api_v1_bp.register_blueprint(webhooks_router, url_prefix="/webhooks")
api_v1_bp.register_blueprint(admin_router, url_prefix="/admin")

# Export the blueprint
__all__ = ["api_v1_bp"]
