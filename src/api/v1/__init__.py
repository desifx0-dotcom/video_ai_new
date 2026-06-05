"""API v1 routes and endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

# Import routers
from .routers import auth, videos, users, billing, webhooks, admin
from .routers.auth_public import public_auth_bp  # NEW - import public auth
from .routers.refresh import refresh_bp

# Create v1 blueprint
api_v1_bp = Blueprint("api_v1_bp", __name__, url_prefix="/api/v1")

# Register routers
# PUBLIC routes (no JWT required) - REGISTER THESE FIRST
api_v1_bp.register_blueprint(public_auth_bp, url_prefix="/auth")  # NEW - public auth

# PROTECTED routes (JWT required via middleware)
api_v1_bp.register_blueprint(auth.router, url_prefix="/auth/protected")  # Changed URL
api_v1_bp.register_blueprint(videos.router, url_prefix="/videos")
api_v1_bp.register_blueprint(users.router, url_prefix="/users")
api_v1_bp.register_blueprint(billing.router, url_prefix="/billing")
api_v1_bp.register_blueprint(webhooks.webhook_bp, url_prefix="/webhooks")
api_v1_bp.register_blueprint(admin.admin_bp, url_prefix="/admin")
api_v1_bp.register_blueprint(refresh_bp, url_prefix="/auth")

@api_v1_bp.route("/")
def index():
    """API v1 index."""
    return jsonify(
        {
            "version": "1.0.0",
            "status": "active",
            "endpoints": {
                "auth": "/api/v1/auth",
                "videos": "/api/v1/videos",
                "users": "/api/v1/users",
                "billing": "/api/v1/billing",
                "admin": "/api/v1/admin",
                "webhooks": "/api/v1/webhooks",
            },
            "documentation": "https://docs.videoaistudio.com/api/v1",
        }
    )


@api_v1_bp.route("/status")
@jwt_required()
def status():
    """API v1 status endpoint."""
    from services.user_service import get_user_by_id

    user_id = get_jwt_identity()
    user = get_user_by_id(user_id)

    from providers.redis_provider import RedisProvider

    redis = RedisProvider()

    return jsonify(
        {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "user": {
                "id": user.id,
                "email": user.email,
                "tier": user.tier,
                "credits_remaining": user.credits_remaining,
            },
            "services": {
                "redis": "connected" if redis.ping() else "disconnected",
                "database": "connected",
                "queue": "active",
            },
        }
    )


@api_v1_bp.route("/health")
def health():
    """Health check endpoint."""
    from providers.redis_provider import RedisProvider

    services = {}

    # Check Redis
    try:
        redis = RedisProvider()
        redis.ping()
        services["redis"] = "healthy"
    except Exception as e:
        services["redis"] = f"unhealthy: {str(e)}"

    # Check database
    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()
        db.ping()
        services["database"] = "healthy"
    except Exception as e:
        services["database"] = f"unhealthy: {str(e)}"

    # Determine overall status
    all_healthy = all("healthy" in status for status in services.values())

    return jsonify(
        {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "services": services,
            "version": "1.0.0",
        }
    )


@api_v1_bp.route("/metrics")
@jwt_required()
def metrics():
    """Application metrics endpoint."""
    from flask import g
    from app.monitoring.metrics import generate_latest

    # Only allow admin users
    if not g.current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403

    return generate_latest(), 200, {"Content-Type": "text/plain"}


@api_v1_bp.route("/docs")
def docs():
    """API documentation endpoint."""
    return jsonify(
        {
            "documentation": "https://docs.videoaistudio.com/api/v1",
            "swagger": "/api/v1/swagger.json",
            "openapi": "/api/v1/openapi.json",
        }
    )


@api_v1_bp.route("/swagger.json")
def swagger():
    """Swagger/OpenAPI specification."""
    # This would generate OpenAPI spec dynamically
    # For now, return a placeholder
    return jsonify(
        {
            "openapi": "3.0.0",
            "info": {
                "title": "Video AI Studio API",
                "version": "1.0.0",
                "description": "AI-powered video processing API",
            },
            "servers": [{"url": "/api/v1", "description": "Current API"}],
        }
    )
