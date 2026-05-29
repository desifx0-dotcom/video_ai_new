"""
WebSocket handling for real-time updates.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from flask_jwt_extended import decode_token

from core.exceptions import UnauthorizedError
from services.video_service import VideoService
from services.user_service import UserService
from providers.redis_provider import RedisProvider

logger = logging.getLogger(__name__)

# Initialize services
video_service = VideoService()
user_service = UserService()
redis = RedisProvider()

# WebSocket event names
WS_EVENTS = {
    "CONNECT": "connect",
    "DISCONNECT": "disconnect",
    "VIDEO_UPLOADED": "video_uploaded",
    "VIDEO_PROCESSING": "video_processing",
    "VIDEO_COMPLETED": "video_completed",
    "VIDEO_FAILED": "video_failed",
    "PROGRESS_UPDATE": "progress_update",
    "TIER_UPGRADED": "tier_upgraded",
    "CREDITS_UPDATED": "credits_updated",
    "SYSTEM_ALERT": "system_alert",
    "PING": "ping",
    "PONG": "pong",
}

# Global socketio instances
_socketio = None
socketio = None  # This will be set by set_socketio_instance

# Connected clients
connected_clients = {}


def get_socketio():
    """Get the global socketio instance."""
    return _socketio


def set_socketio_instance(socketio_instance):
    """Set the global socketio instance (called from main.py)."""
    global _socketio, socketio
    _socketio = socketio_instance
    socketio = socketio_instance
    logger.info("SocketIO instance set globally")


def init_websocket(app):
    """Initialize WebSocket with the Flask app."""
    global _socketio, socketio
    _socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        message_queue=app.config.get("REDIS_URL", "redis://localhost:6379/0"),
        logger=True,
        engineio_logger=True,
    )
    socketio = _socketio
    
    # Register handlers
    register_websocket_handlers(_socketio)
    
    logger.info("WebSocket initialized")
    return _socketio


def send_video_update(
    video_id: str,
    user_id: str,
    status: str,
    progress: float,
    step: Optional[str] = None,
    message: Optional[str] = None,
):
    """Send video processing update via WebSocket."""
    if _socketio is None:
        logger.debug(f"WebSocket not initialized, skipping update for {video_id}")
        return

    try:
        data = {
            "video_id": video_id,
            "user_id": user_id,
            "status": status,
            "progress": progress,
            "current_step": step,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["VIDEO_PROCESSING"], data, room=f"video:{video_id}")
        _socketio.emit(WS_EVENTS["VIDEO_PROCESSING"], data, room=f"user:{user_id}")

        logger.debug(f"Video update sent: {video_id} - {status} ({progress}%)")

    except Exception as e:
        logger.warning(f"Send video update error: {e}")


def send_video_completed(
    video_id: str,
    user_id: str,
    result_url: str,
    processing_time: float,
    total_cost: float,
):
    """Send video completed notification via WebSocket."""
    if _socketio is None:
        logger.debug(f"WebSocket not initialized, skipping completion for {video_id}")
        return

    try:
        data = {
            "video_id": video_id,
            "user_id": user_id,
            "status": "completed",
            "result_url": result_url,
            "processing_time": processing_time,
            "total_cost": total_cost,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["VIDEO_COMPLETED"], data, room=f"video:{video_id}")
        _socketio.emit(WS_EVENTS["VIDEO_COMPLETED"], data, room=f"user:{user_id}")

        logger.info(f"Video completed notification sent: {video_id}")

    except Exception as e:
        logger.error(f"Send video completed error: {e}")


def send_video_failed(
    video_id: str, user_id: str, error_message: str, retry_count: int, can_retry: bool
):
    """Send video failed notification via WebSocket."""
    if _socketio is None:
        logger.debug(f"WebSocket not initialized, skipping failure for {video_id}")
        return

    try:
        data = {
            "video_id": video_id,
            "user_id": user_id,
            "status": "failed",
            "error_message": error_message,
            "retry_count": retry_count,
            "can_retry": can_retry,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["VIDEO_FAILED"], data, room=f"video:{video_id}")
        _socketio.emit(WS_EVENTS["VIDEO_FAILED"], data, room=f"user:{user_id}")

        logger.warning(f"Video failed notification sent: {video_id}")

    except Exception as e:
        logger.error(f"Send video failed error: {e}")


def send_tier_upgraded(
    user_id: str,
    old_tier: str,
    new_tier: str,
    upgrade_price: float,
    new_limits: Dict[str, Any],
):
    """Send tier upgrade notification via WebSocket."""
    if _socketio is None:
        return

    try:
        data = {
            "user_id": user_id,
            "old_tier": old_tier,
            "new_tier": new_tier,
            "upgrade_price": upgrade_price,
            "new_limits": new_limits,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["TIER_UPGRADED"], data, room=f"user:{user_id}")

        logger.info(f"Tier upgrade notification sent: {user_id} ({old_tier} -> {new_tier})")

    except Exception as e:
        logger.error(f"Send tier upgraded error: {e}")


def send_credits_updated(
    user_id: str,
    old_credits: int,
    new_credits: int,
    reason: str,
    video_id: Optional[str] = None,
):
    """Send credits update notification via WebSocket."""
    if _socketio is None:
        return

    try:
        data = {
            "user_id": user_id,
            "old_credits": old_credits,
            "new_credits": new_credits,
            "change": new_credits - old_credits,
            "reason": reason,
            "video_id": video_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["CREDITS_UPDATED"], data, room=f"user:{user_id}")

        logger.debug(f"Credits update notification sent: {user_id}")

    except Exception as e:
        logger.error(f"Send credits updated error: {e}")


def send_system_alert(
    message: str,
    alert_type: str = "info",
    severity: str = "info",
    metadata: Optional[Dict[str, Any]] = None,
):
    """Send system alert to admin users."""
    if _socketio is None:
        return

    try:
        data = {
            "message": message,
            "type": alert_type,
            "severity": severity,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["SYSTEM_ALERT"], data, room="admin")

        logger.info(f"System alert sent: {message}")

    except Exception as e:
        logger.error(f"Send system alert error: {e}")


def send_progress_update(
    video_id: str,
    progress: float,
    step: str,
    estimated_time_remaining: Optional[float] = None,
):
    """Send progress update for video processing."""
    if _socketio is None:
        return

    try:
        data = {
            "video_id": video_id,
            "progress": progress,
            "step": step,
            "estimated_time_remaining": estimated_time_remaining,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _socketio.emit(WS_EVENTS["PROGRESS_UPDATE"], data, room=f"video:{video_id}")

        logger.debug(f"Progress update sent: {video_id} - {step} ({progress}%)")

    except Exception as e:
        logger.warning(f"Send progress update error: {e}")


def register_websocket_handlers(socketio_instance: SocketIO):
    """Register all WebSocket event handlers."""
    
    @socketio_instance.on("connect")
    def handle_connect():
        """Handle WebSocket connection."""
        try:
            token = request.args.get("token")
            if not token:
                logger.warning("WebSocket connection attempt without token")
                disconnect()
                return False

            try:
                decoded = decode_token(token)
                user_id = decoded["sub"]

                user = user_service.get_user_by_id(user_id)
                if not user or not user.is_active():
                    logger.warning(f"Invalid user attempting WebSocket: {user_id}")
                    disconnect()
                    return False

                connected_clients[request.sid] = {
                    "user_id": user_id,
                    "tier": user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
                    "connected_at": datetime.utcnow().isoformat(),
                }

                join_room(f"user:{user_id}")
                join_room(f"tier:{user.tier.value if hasattr(user.tier, 'value') else str(user.tier)}")

                if getattr(user, 'is_admin', False):
                    join_room("admin")

                logger.info(f"WebSocket connected: {user_id}")

                emit(
                    WS_EVENTS["CONNECT"],
                    {
                        "status": "connected",
                        "user_id": user_id,
                        "tier": user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

                return True

            except Exception as e:
                logger.error(f"Token verification failed: {e}")
                disconnect()
                return False

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            disconnect()
            return False

    @socketio_instance.on("disconnect")
    def handle_disconnect():
        """Handle WebSocket disconnection."""
        if request.sid in connected_clients:
            user_info = connected_clients.pop(request.sid)
            logger.info(f"WebSocket disconnected: {user_info.get('user_id')}")

    @socketio_instance.on("subscribe_video")
    def handle_subscribe_video(data: Dict[str, Any]):
        """Subscribe to video processing updates."""
        try:
            user_info = connected_clients.get(request.sid)
            if not user_info:
                raise UnauthorizedError("Not authenticated")

            video_id = data.get("video_id")
            if not video_id:
                return {"error": "video_id is required"}

            video = video_service.get_video(video_id, user_info["user_id"])
            if not video:
                return {"error": "Video not found or access denied"}

            join_room(f"video:{video_id}")

            emit(
                WS_EVENTS["VIDEO_PROCESSING"],
                {
                    "video_id": video_id,
                    "status": getattr(video, 'status', "unknown"),
                    "progress": video.get_progress() if hasattr(video, 'get_progress') else 0,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=request.sid,
            )

            return {"status": "subscribed", "video_id": video_id}

        except Exception as e:
            logger.error(f"Subscribe video error: {e}")
            return {"error": str(e)}

    @socketio_instance.on("unsubscribe_video")
    def handle_unsubscribe_video(data: Dict[str, Any]):
        """Unsubscribe from video processing updates."""
        try:
            video_id = data.get("video_id")
            if video_id:
                leave_room(f"video:{video_id}")
            return {"status": "unsubscribed"}
        except Exception as e:
            return {"error": str(e)}

    @socketio_instance.on("get_video_status")
    def handle_get_video_status(data: Dict[str, Any]):
        """Get current video status."""
        try:
            user_info = connected_clients.get(request.sid)
            if not user_info:
                raise UnauthorizedError("Not authenticated")

            video_id = data.get("video_id")
            if not video_id:
                return {"error": "video_id is required"}

            status = video_service.get_processing_status(video_id, user_info["user_id"])
            if not status:
                return {"error": "Video not found or access denied"}

            return {
                "status": "success",
                "video_id": video_id,
                "video_status": status.get("status"),
                "progress": status.get("progress", 0),
            }

        except Exception as e:
            logger.error(f"Get video status error: {e}")
            return {"error": str(e)}

    @socketio_instance.on("ping")
    def handle_ping(data: Dict[str, Any] = None):
        """Handle ping for connection testing."""
        emit(
            WS_EVENTS["PONG"],
            {"timestamp": datetime.utcnow().isoformat(), "data": data or {}},
        )

    @socketio_instance.on("admin_broadcast")
    def handle_admin_broadcast(data: Dict[str, Any]):
        """Admin broadcast message to all users."""
        try:
            user_info = connected_clients.get(request.sid)
            if not user_info:
                raise UnauthorizedError("Not authenticated")

            user = user_service.get_user_by_id(user_info["user_id"])
            if not user or not getattr(user, 'is_admin', False):
                raise UnauthorizedError("Admin access required")

            message = data.get("message", "")
            target = data.get("target", "all")

            if not message:
                return {"error": "Message is required"}

            emit(
                WS_EVENTS["SYSTEM_ALERT"],
                {
                    "message": message,
                    "type": "admin_broadcast",
                    "timestamp": datetime.utcnow().isoformat(),
                    "from_admin": user.id,
                },
                room=None if target == "all" else target,
            )

            logger.info(f"Admin broadcast from {user.id}: {message}")

            return {"status": "broadcasted", "target": target}

        except Exception as e:
            logger.error(f"Admin broadcast error: {e}")
            return {"error": str(e)}


def get_connected_clients_stats() -> Dict[str, Any]:
    """Get statistics about connected WebSocket clients."""
    try:
        tiers = {}
        for client_info in connected_clients.values():
            tier = client_info.get("tier", "unknown")
            tiers[tier] = tiers.get(tier, 0) + 1

        unique_users = len(set(info.get("user_id") for info in connected_clients.values()))

        return {
            "total_clients": len(connected_clients),
            "unique_users": unique_users,
            "by_tier": tiers,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Get connected clients stats error: {e}")
        return {}


def disconnect_user(user_id: str):
    """Disconnect a specific user from WebSocket."""
    try:
        sids_to_disconnect = []
        for sid, info in connected_clients.items():
            if info.get("user_id") == user_id:
                sids_to_disconnect.append(sid)

        for sid in sids_to_disconnect:
            disconnect(sid)

        logger.info(f"Disconnected user {user_id} from WebSocket")

    except Exception as e:
        logger.error(f"Disconnect user error: {e}")