"""
API layer for Video AI Studio.
"""

from flask import Blueprint, jsonify
from app.middleware.auth import jwt_required
from .v1 import api_v1_bp
from datetime import datetime

# Create main API blueprint
api = Blueprint("api", __name__, url_prefix="/api")

# Register versioned blueprints
api.register_blueprint(api_v1_bp)


@api.route("/")
def api_index():
    """API index endpoint."""
    return jsonify(
        {
            "name": "Video AI Studio API",
            "version": "1.0.0",
            "documentation": "/api/docs",
            "endpoints": {
                "v1": "/api/v1",
                "auth": "/api/v1/auth",
                "videos": "/api/v1/videos",
                "users": "/api/v1/users",
                "billing": "/api/v1/billing",
                "admin": "/api/v1/admin",
            },
        }
    )


@api.route("/status")
@jwt_required
def api_status():
    """API status endpoint (requires authentication)."""
    from flask import g

    return jsonify(
        {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "user": {
                "id": g.current_user.id,
                "email": g.current_user.email,
                "tier": g.current_user.tier,
            },
        }
    )


def register_api_routes(app):
    """Register all API routes with Flask app."""
    app.register_blueprint(api)

    # Register error handlers
    from core.exceptions import handle_exception

    app.register_error_handler(Exception, handle_exception)

    return app
