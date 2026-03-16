"""Session management endpoints."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    create_access_token,
    get_jwt,
)
from datetime import timedelta

session_bp = Blueprint("session", __name__, url_prefix="/session")


@session_bp.route("/check", methods=["GET"])
@jwt_required(optional=True)
def check_session():
    """Check if user session is valid."""
    user_id = get_jwt_identity()

    if not user_id:
        return jsonify({"authenticated": False}), 200

    # Get additional claims from token
    claims = get_jwt()

    return (
        jsonify(
            {
                "authenticated": True,
                "user": {
                    "id": user_id,
                    "email": claims.get("email"),
                    "tier": claims.get("tier"),
                    "is_admin": claims.get("is_admin", False),
                },
            }
        ),
        200,
    )


@session_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_session():
    """Refresh access token."""
    user_id = get_jwt_identity()

    new_token = create_access_token(identity=user_id, expires_delta=timedelta(hours=1))

    response = jsonify({"success": True})
    response.set_cookie(
        "access_token_cookie",
        value=new_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=3600,
        path="/",
    )

    return response, 200
