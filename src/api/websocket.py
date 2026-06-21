"""
WebSocket handling for real-time updates.
Production-ready with Eventlet + Redis for cross-process communication.
"""
from patch_async import ASYNC_MODE
import os
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

# Global socketio instances
_socketio = None
socketio = None
_worker_socketio = None

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

# Connected clients tracking
connected_clients = {}


# ========== INITIALIZATION ==========

def get_socketio() -> Optional[SocketIO]:
    """Get the global socketio instance."""
    return _socketio


def set_socketio_instance(socketio_instance: SocketIO) -> None:
    """Set the global socketio instance (called from main.py)."""
    global _socketio, socketio
    _socketio = socketio_instance
    socketio = socketio_instance
    logger.info("✅ SocketIO instance set globally")


def get_worker_socketio() -> Optional[SocketIO]:
    """Get a SocketIO client that connects via Redis message queue."""
    global _worker_socketio
    if _worker_socketio is None:
        try:
            redis_url = os.getenv('REDIS_URL')
            
            if redis_url:
                # Use gevent for the worker client
                _worker_socketio = SocketIO(
                    message_queue=redis_url,
                    async_mode=ASYNC_MODE
                )
                logger.info(f"✅ Worker SocketIO connected to Redis: {redis_url[:30]}...")
            else:
                logger.warning("⚠️ No Redis URL for worker")
                _worker_socketio = None
                
        except Exception as e:
            logger.error(f"❌ Failed to create worker SocketIO: {e}")
            _worker_socketio = None
    return _worker_socketio


# def init_websocket(app) -> SocketIO:
#     """Initialize WebSocket with the Flask app."""
#     global _socketio, socketio
#     try:
#         redis_url = (
#             app.config.get('SOCKETIO_MESSAGE_QUEUE') or 
#             os.getenv('SOCKETIO_MESSAGE_QUEUE') or 
#             os.getenv('REDIS_URL', 'redis://localhost:6379/0')
#         )
        
#         _socketio = SocketIO(
#             app,
#             cors_allowed_origins="*",
#             async_mode="eventlet",  # Efficient async for WebSocket
#             message_queue=None,
#             logger=True if app.debug else False,
#             engineio_logger=True if app.debug else False,
#             ping_timeout=60,
#             ping_interval=25,
#             max_http_buffer_size=100 * 1024 * 1024,
#         )
#         socketio = _socketio
        
#         # Register handlers
#         register_websocket_handlers(_socketio)
        
#         logger.info(f"✅ WebSocket initialized with Redis: {redis_url}")
#         return _socketio
#     except Exception as e:
#         logger.error(f"❌ Failed to initialize WebSocket: {e}")
#         raise


# ========== EVENT EMITTERS ==========

def _emit_event(event_name: str, data: Dict[str, Any], room: str) -> None:
    """
    Helper to emit event via server instance if available, else via Redis client.
    Handles graceful fallback with proper error logging.
    """
    if not room:
        logger.warning(f"⚠️ No room provided for event {event_name}")
        return
    
    try:
        if _socketio is not None:
            # Main server process - emit directly
            try:
                _socketio.emit(event_name, data, room=room)
                return
            except Exception as e:
                logger.warning(f"Server emit failed, trying Redis client: {e}")
                # Fall through to Redis client
        
        # Worker process or server fallback - use Redis-based client
        client = get_worker_socketio()
        if client is not None:
            client.emit(event_name, data, room=room)
        else:
            logger.warning(f"⚠️ No SocketIO client available for {event_name}")
            
    except Exception as e:
        logger.error(f"❌ _emit_event failed for {event_name} to room {room}: {e}")


def send_video_update(
    video_id: str,
    user_id: str,
    status: str,
    progress: float,
    step: Optional[str] = None,
    message: Optional[str] = None,
    publish_to_redis: bool = True  #false for direct emit , skip redis
) -> bool:
    """
    Send video processing update via WebSocket.
    Works in both server and worker processes.
    
    Returns:
        bool: True if successfully emitted, False otherwise
    """
    try:
        if step is None:
            step = status
        
        logger.debug(f"📤 send_video_update: step={step}, progress={progress}, status={status}")
        
        data = {
            "video_id": video_id,
            "user_id": user_id,
            "status": status,
            "progress": progress,
            "current_step": step,
            "step": step,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(f"📤 EMITTING DATA: current_step={data['current_step']}, step={data['step']}, progress={data['progress']}")
    
        # Emit to video room (for all subscribers)
        _emit_event(WS_EVENTS["VIDEO_PROCESSING"], data, room=f"video:{video_id}")

        # Also emit to user room for personal updates
        if user_id:
            _emit_event(WS_EVENTS["VIDEO_PROCESSING"], data, room=f"user:{user_id}")
        
        logger.info(f"✅ Emitted video_processing: {video_id} - {step} ({progress}%)")
        return True

    except Exception as e:
        logger.error(f"❌ send_video_update failed for {video_id}: {e}", exc_info=True)
        return False


def send_video_completed(
    video_id: str,
    user_id: str,
    result_url: str,
    processing_time: float,
    total_cost: float,
) -> bool:
    """Send video completed notification via WebSocket."""
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

        logger.info(f"🔔 Sending video_completed event for {video_id}")

        _emit_event(WS_EVENTS["VIDEO_COMPLETED"], data, room=f"video:{video_id}")
        if user_id:
            _emit_event(WS_EVENTS["VIDEO_COMPLETED"], data, room=f"user:{user_id}")
        
        logger.info(f"✅ video_completed event SENT for {video_id}")
        return True

    except Exception as e:
        logger.error(f"❌ send_video_completed failed for {video_id}: {e}", exc_info=True)
        return False


def send_video_failed(
    video_id: str,
    user_id: str,
    error_message: str,
    retry_count: int,
    can_retry: bool
) -> bool:
    """Send video failed notification via WebSocket."""
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

        logger.warning(f"🔔 Sending video_failed event for {video_id}: {error_message}")

        _emit_event(WS_EVENTS["VIDEO_FAILED"], data, room=f"video:{video_id}")
        if user_id:
            _emit_event(WS_EVENTS["VIDEO_FAILED"], data, room=f"user:{user_id}")
        
        logger.warning(f"✅ video_failed event SENT for {video_id}")
        return True

    except Exception as e:
        logger.error(f"❌ send_video_failed failed for {video_id}: {e}", exc_info=True)
        return False


def send_tier_upgraded(
    user_id: str,
    old_tier: str,
    new_tier: str,
    upgrade_price: float,
    new_limits: Dict[str, Any],
) -> bool:
    """Send tier upgrade notification via WebSocket."""
    try:
        data = {
            "user_id": user_id,
            "old_tier": old_tier,
            "new_tier": new_tier,
            "upgrade_price": upgrade_price,
            "new_limits": new_limits,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(f"🔔 Sending tier_upgraded event for {user_id} ({old_tier} -> {new_tier})")

        _emit_event(WS_EVENTS["TIER_UPGRADED"], data, room=f"user:{user_id}")
        
        logger.info(f"✅ tier_upgraded event SENT for {user_id}")
        return True

    except Exception as e:
        logger.error(f"❌ send_tier_upgraded failed for {user_id}: {e}", exc_info=True)
        return False


def send_credits_updated(
    user_id: str,
    old_credits: int,
    new_credits: int,
    reason: str,
    video_id: Optional[str] = None,
) -> bool:
    """Send credits update notification via WebSocket."""
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

        logger.debug(f"🔔 Sending credits_updated event for {user_id}")

        _emit_event(WS_EVENTS["CREDITS_UPDATED"], data, room=f"user:{user_id}")
        
        logger.debug(f"✅ credits_updated event SENT for {user_id}")
        return True

    except Exception as e:
        logger.error(f"❌ send_credits_updated failed for {user_id}: {e}", exc_info=True)
        return False
    

def send_system_alert(
    message: str,
    alert_type: str = "info",
    severity: str = "info",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send system alert to admin users."""
    try:
        data = {
            "message": message,
            "type": alert_type,
            "severity": severity,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(f"🔔 Sending system_alert: {message}")

        _emit_event(WS_EVENTS["SYSTEM_ALERT"], data, room="admin")
        
        logger.info(f"✅ system_alert event SENT")
        return True

    except Exception as e:
        logger.error(f"❌ send_system_alert failed: {e}", exc_info=True)
        return False


def send_progress_update(
    video_id: str,
    progress: float,
    step: str,
    estimated_time_remaining: Optional[float] = None,
) -> bool:
    """Send progress update for video processing."""
    try:
        data = {
            "video_id": video_id,
            "progress": progress,
            "step": step,
            "estimated_time_remaining": estimated_time_remaining,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.debug(f"🔔 Sending progress_update for {video_id}: {step} ({progress}%)")

        _emit_event(WS_EVENTS["PROGRESS_UPDATE"], data, room=f"video:{video_id}")
        
        logger.debug(f"✅ progress_update event SENT for {video_id}")
        return True

    except Exception as e:
        logger.error(f"❌ send_progress_update failed for {video_id}: {e}", exc_info=True)
        return False


# ========== WEBSOCKET EVENT HANDLERS ==========

def register_websocket_handlers(socketio_instance: SocketIO) -> None:
    """Register all WebSocket event handlers."""
    
    @socketio_instance.on("connect")
    def handle_connect():
        """Handle WebSocket connection with production-grade token extraction."""
        try:
            token = None
            
            # Try query parameter (most common for WebSocket)
            token = request.args.get("token")
            
            # Try Authorization header
            if not token:
                auth_header = request.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    token = auth_header[7:]
            
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
                
                # Store connection info
                connected_clients[request.sid] = {
                    "user_id": user_id,
                    "tier": user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
                    "connected_at": datetime.utcnow().isoformat(),
                }
                
                # Join user rooms
                join_room(f"user:{user_id}")
                join_room(f"tier:{user.tier.value if hasattr(user.tier, 'value') else str(user.tier)}")
                
                if getattr(user, 'is_admin', False):
                    join_room("admin")
                
                logger.info(f"WebSocket connected: {user_id}")
                
                emit(WS_EVENTS["CONNECT"], {
                    "status": "connected",
                    "user_id": user_id,
                    "tier": user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
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
    @socketio_instance.on("subscribe_video")
    def handle_subscribe_video(data: Dict[str, Any]):
        """Subscribe to video processing updates."""
        try:
            logger.info(f"🔍 SUBSCRIBE_VIDEO CALLED with data: {data}")
            
            user_info = connected_clients.get(request.sid)
            logger.info(f"🔍 user_info: {user_info}")
            
            if not user_info:
                logger.info("🔍 user_info is None, trying token re-auth...")
                token = request.args.get("token")
                if token:
                    try:
                        decoded = decode_token(token)
                        user_id = decoded["sub"]
                        user = user_service.get_user_by_id(user_id)
                        if user and user.is_active():
                            user_info = {
                                "user_id": user_id,
                                "tier": user.tier.value if hasattr(user.tier, 'value') else str(user.tier),
                            }
                            connected_clients[request.sid] = user_info
                            join_room(f"user:{user_id}")
                            logger.info(f"✅ Re-authenticated user {user_id} on reconnect")
                    except Exception as e:
                        logger.error(f"Token re-auth failed: {e}")
                
                if not user_info:
                    logger.warning("⚠️ No user_info after re-auth attempt")
                    emit("error", {"message": "Not authenticated"})
                    return

            video_id = data.get("video_id")
            logger.info(f"🔍 video_id: {video_id}")
            
            if not video_id:
                logger.warning("⚠️ No video_id in subscription")
                emit("error", {"message": "video_id is required"})
                return

            # Verify video belongs to user
            logger.info(f"🔍 Getting video: {video_id} for user: {user_info['user_id']}")
            video = video_service.get_video(video_id, user_info["user_id"])
            logger.info(f"🔍 video found: {video is not None}")
            
            if not video:
                logger.warning(f"⚠️ Video {video_id} not found or access denied")
                emit("error", {"message": "Video not found or access denied"})
                return
            
            # Check if client is already in the room
            room = f"video:{video_id}"
            rooms = _socketio.rooms(request.sid)
            logger.info(f"🔍 Current rooms for client: {rooms}")

            if room not in rooms:
                join_room(room)
                logger.info(f"📡 Client joined room: {room}")
            else:
                logger.info(f"📡 Client already in room: {room}")

            # Only send initial status once
            logger.info("🔍 Checking Redis for status_sent_key...")
            try:
                status_sent_key = f"status_sent:{request.sid}:{video_id}"
                redis_status = redis.get(status_sent_key)
                logger.info(f"🔍 Redis status_sent_key: {redis_status}")
                
                if not redis_status:
                    logger.info("🔍 No status sent yet, sending initial status...")
                    status = video_service.get_processing_status(video_id, user_info["user_id"])
                    logger.info(f"🔍 Processing status: {status}")
                    
                    if status:
                        current_status = status.get("status")
                        current_progress = status.get("progress", 0)
                        current_step = status.get("current_step")
                        
                        logger.info(f"🔍 Current status: {current_status}, progress: {current_progress}, step: {current_step}")
                        
                        # Infer step from progress if missing
                        if not current_step:
                            if current_progress < 10:
                                current_step = "queued"
                            elif current_progress < 25:
                                current_step = "analyzing"
                            elif current_progress < 40:
                                current_step = "transcribing"
                            elif current_progress < 55:
                                current_step = "generating_metadata"
                            elif current_progress < 70:
                                current_step = "generating_thumbnails"
                            elif current_progress < 90:
                                current_step = "applying_filters"
                            else:
                                current_step = "finalizing"
                        
                        logger.info(f"📤 Sending initial status: {current_status} ({current_progress}%) step={current_step}")
                        
                        emit(WS_EVENTS["VIDEO_PROCESSING"], {
                            "video_id": video_id,
                            "user_id": user_info["user_id"],
                            "status": current_status or "processing",
                            "progress": current_progress,
                            "current_step": current_step,
                            "timestamp": datetime.utcnow().isoformat(),
                        }, room=request.sid)
                        
                        # Mark as sent (expire after 5 minutes)
                        redis.setex(status_sent_key, 300, "1")
                        logger.info("✅ Status sent and marked in Redis")
                    else:
                        logger.warning("⚠️ No status returned from video_service.get_processing_status")
                else:
                    logger.info("✅ Status already sent, skipping")
            except Exception as e:
                logger.error(f"❌ Error in status handling: {e}", exc_info=True)
                # Fallback: try to send status without Redis
                try:
                    status = video_service.get_processing_status(video_id, user_info["user_id"])
                    if status:
                        current_status = status.get("status")
                        current_progress = status.get("progress", 0)
                        current_step = status.get("current_step", "queued")
                        
                        emit(WS_EVENTS["VIDEO_PROCESSING"], {
                            "video_id": video_id,
                            "user_id": user_info["user_id"],
                            "status": current_status or "processing",
                            "progress": current_progress,
                            "current_step": current_step,
                            "timestamp": datetime.utcnow().isoformat(),
                        }, room=request.sid)
                        logger.info("✅ Status sent as fallback")
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback status send also failed: {fallback_error}")
            
            emit('subscribed', {'video_id': video_id, 'room': f"video:{video_id}"}, room=request.sid)
            logger.info(f"✅ Subscription complete for {video_id}")
            
            return {"status": "subscribed", "video_id": video_id}

        except Exception as e:
            logger.error(f"❌ Subscribe video error: {e}", exc_info=True)
            # DON'T emit error - just log it and return
            # The frontend doesn't need to know about internal errors
            return {"error": str(e)}

    @socketio_instance.on("unsubscribe_video")
    def handle_unsubscribe_video(data: Dict[str, Any]):
        """Unsubscribe from video processing updates."""
        try:
            video_id = data.get("video_id")
            if video_id:
                leave_room(f"video:{video_id}")
            emit("unsubscribed", {"video_id": video_id})
        except Exception as e:
            emit("error", {"message": str(e)})

    @socketio_instance.on("get_video_status")
    def handle_get_video_status(data: Dict[str, Any]):
        """Get current video status."""
        try:
            user_info = connected_clients.get(request.sid)
            if not user_info:
                emit("error", {"message": "Not authenticated"})
                return

            video_id = data.get("video_id")
            if not video_id:
                emit("error", {"message": "video_id is required"})
                return

            status = video_service.get_processing_status(video_id, user_info["user_id"])
            if not status:
                emit("error", {"message": "Video not found or access denied"})
                return

            emit("video_status", {
                "video_id": video_id,
                "status": status.get("status"),
                "progress": status.get("progress", 0),
                "current_step": status.get("current_step"),
            })

        except Exception as e:
            logger.error(f"Get video status error: {e}")
            emit("error", {"message": str(e)})

    @socketio_instance.on("ping")
    def handle_ping(data: Dict[str, Any] = None):
        """Handle ping for connection testing."""
        emit(WS_EVENTS["PONG"], {
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {}
        })

    @socketio_instance.on("admin_broadcast")
    def handle_admin_broadcast(data: Dict[str, Any]):
        """Admin broadcast message to all users."""
        try:
            user_info = connected_clients.get(request.sid)
            if not user_info:
                emit("error", {"message": "Not authenticated"})
                return

            user = user_service.get_user_by_id(user_info["user_id"])
            if not user or not getattr(user, 'is_admin', False):
                emit("error", {"message": "Admin access required"})
                return

            message = data.get("message", "")
            target = data.get("target", "all")

            if not message:
                emit("error", {"message": "Message is required"})
                return

            emit(WS_EVENTS["SYSTEM_ALERT"], {
                "message": message,
                "type": "admin_broadcast",
                "timestamp": datetime.utcnow().isoformat(),
                "from_admin": user.id,
            }, room=None if target == "all" else target)

            logger.info(f"Admin broadcast from {user.id}: {message}")
            emit("broadcast_sent", {"status": "sent", "target": target})

        except Exception as e:
            logger.error(f"Admin broadcast error: {e}")
            emit("error", {"message": str(e)})


# ========== STATISTICS AND MANAGEMENT ==========

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


def disconnect_user(user_id: str) -> int:
    """
    Disconnect a specific user from WebSocket.
    
    Returns:
        int: Number of connections disconnected
    """
    try:
        sids_to_disconnect = []
        for sid, info in connected_clients.items():
            if info.get("user_id") == user_id:
                sids_to_disconnect.append(sid)

        for sid in sids_to_disconnect:
            disconnect(sid)

        logger.info(f"Disconnected {len(sids_to_disconnect)} connections for user {user_id}")
        return len(sids_to_disconnect)

    except Exception as e:
        logger.error(f"Disconnect user error: {e}")
        return 0
    
