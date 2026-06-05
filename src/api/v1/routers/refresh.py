"""
Token refresh endpoint.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, decode_token, 
    get_jwt_identity, jwt_required
)

import logging
from datetime import timedelta , datetime

logger = logging.getLogger(__name__)

refresh_bp = Blueprint('refresh', __name__)


@refresh_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """
    Refresh access token using refresh token.
    
    This endpoint:
    1. Accepts a valid refresh token
    2. Validates it hasn't expired
    3. Issues a new access token
    4. Extends refresh token expiration if within 7 days of expiry
    """
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        return jsonify({
            "error": {
                "code": "INVALID_TOKEN_FORMAT",
                "message": "Authorization header must start with 'Bearer '"
            }
        }), 401
    
    refresh_token = auth_header.replace('Bearer ', '')
    
    try:
        # Decode the refresh token (allow_expired=False ensures we catch expired tokens)
        decoded = decode_token(refresh_token, allow_expired=False)
        user_id = decoded.get('sub')
        
        if not user_id:
            return jsonify({
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "Invalid refresh token: missing user identifier"
                }
            }), 401
        
        # Get user from database
        from services.user_service import UserService
        user_service = UserService()
        user = user_service.get_user_by_id(user_id)
        
        if not user:
            return jsonify({
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "User associated with this token no longer exists"
                }
            }), 404
        
        if not user.is_active():
            return jsonify({
                "error": {
                    "code": "USER_INACTIVE",
                    "message": "Account is no longer active"
                }
            }), 403
        
        # Get user tier for claims
        tier_value = user.tier.value if hasattr(user.tier, 'value') else user.tier
        
        # Create new access token
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(hours=1),
            additional_claims={
                "email": user.email,
                "tier": tier_value,
            }
        )
        
        # Optional: Check if refresh token is expiring soon and issue new one
        refresh_exp = decoded.get('exp', 0)
        current_time = datetime.utcnow().timestamp()
        days_until_expiry = (refresh_exp - current_time) / 86400  # 86400 seconds in a day
        
        response_data = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600  # 1 hour in seconds
        }
        
        # If refresh token is expiring within 7 days, issue a new one
        if days_until_expiry < 7:
            from flask_jwt_extended import create_refresh_token
            new_refresh_token = create_refresh_token(
                identity=user.id,
                expires_delta=timedelta(days=30)
            )
            response_data["refresh_token"] = new_refresh_token
            logger.info(f"Issued new refresh token for user {user_id} (expiring in {days_until_expiry:.1f} days)")
        
        logger.info(f"Successfully refreshed token for user {user_id}")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        error_msg = str(e)
        
        if "Signature verification failed" in error_msg:
            return jsonify({
                "error": {
                    "code": "INVALID_SIGNATURE",
                    "message": "Invalid token signature"
                }
            }), 401
        elif "Token has expired" in error_msg:
            return jsonify({
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": "Refresh token has expired. Please log in again."
                }
            }), 401
        else:
            logger.error(f"Token refresh error: {error_msg}")
            return jsonify({
                "error": {
                    "code": "REFRESH_FAILED",
                    "message": "Failed to refresh token. Please log in again."
                }
            }), 401