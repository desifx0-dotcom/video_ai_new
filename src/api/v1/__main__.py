"""
Main entry point for API v1.
"""

from flask import Blueprint
from .routers import auth, videos, users, billing, webhooks, admin

# Create the main blueprint
api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Register all route blueprints
api_v1.register_blueprint(auth.router)
api_v1.register_blueprint(videos.router)
api_v1.register_blueprint(users.router)
api_v1.register_blueprint(billing.router)
api_v1.register_blueprint(webhooks.webhook_bp)
api_v1.register_blueprint(admin.admin_bp)


def register_api_routes(app):
    """Register all API v1 routes with the main Flask app."""
    app.register_blueprint(api_v1)
    return app


if __name__ == "__main__":
    # This allows running the API standalone for testing
    from flask import Flask

    app = Flask(__name__)
    register_api_routes(app)
    app.run(debug=True)
