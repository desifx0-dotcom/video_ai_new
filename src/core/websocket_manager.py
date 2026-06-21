"""
Production WebSocket Manager with Eventlet + Redis.
"""
from patch_async import ASYNC_MODE
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from collections import defaultdict

import redis
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Production WebSocket Manager with Eventlet + Redis."""
    
    _instance = None
    _initialized = False
    _initializing = False
    _socketio: Optional[SocketIO] = None
    _redis_client: Optional[redis.Redis] = None
    _redis_pubsub: Optional[redis.client.PubSub] = None
    _subscriber_thread: Optional[threading.Thread] = None
    _running: bool = False
    
    # Track connected clients
    _clients: Dict[str, Dict[str, Any]] = {}
    _client_rooms: Dict[str, List[str]] = defaultdict(list)

    # Event handlers
    _handlers: Dict[str, List[Callable]] = defaultdict(list)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_app(self, app: Flask) -> None:
        """Initialize the WebSocket manager with Flask app."""
        
        # Prevent multiple initializations
        if self._initialized:
            logger.info("ℹ️ WebSocketManager already initialized, skipping")
            return
        
        if self._initializing:
            logger.info("ℹ️ WebSocketManager is already being initialized")
            return
        
        self._initializing = True
        logger.info("🔧 Initializing WebSocketManager...")
        
        try:
            redis_url = os.getenv('REDIS_URL')
            
            # ========== SOCKETIO ==========
            self._socketio = SocketIO(
                app,
                cors_allowed_origins="*",
                async_mode=ASYNC_MODE,
                message_queue=redis_url if redis_url else None,
                cors_credentials=True,
                logger=app.debug,
                engineio_logger=app.debug,
                ping_timeout=60,
                ping_interval=25,
                max_http_buffer_size=100 * 1024 * 1024,
            )
            
            # ========== USE REDISPROVIDER ==========
            try:
                # This will use the real Redis (with your IP fix)
                from providers.redis_provider import RedisProvider
                self._redis_client = RedisProvider()
                
                # Test connection
                if self._redis_client.ping():
                    logger.info("✅ Redis connected in WebSocketManager")
                    
                    # Start Redis subscriber using RedisProvider's method
                    self._start_redis_subscriber()
                else:
                    logger.warning("⚠️ Redis ping failed")
                    self._redis_client = None
                    
            except Exception as e:
                logger.error(f"❌ Redis connection failed: {e}")
                self._redis_client = None
            
            # Register event handlers
            self._register_event_handlers()
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ WebSocketManager initialization failed: {e}")
            self._initialized = False
        finally:
            self._initializing = False

    def _start_redis_subscriber(self) -> None:
        """Start Redis subscriber in background thread."""
        if self._subscriber_thread and self._subscriber_thread.is_alive():
            logger.info("ℹ️ Redis subscriber already running")
            return
        
        if not self._redis_client:
            logger.warning("⚠️ Cannot start subscriber: No Redis client")
            return
        
        self._running = True
        self._subscriber_thread = threading.Thread(
            target=self._redis_subscriber_loop,
            daemon=True,
            name="WebSocketManager-RedisSubscriber"
        )
        self._subscriber_thread.start()
        logger.info("✅ Redis subscriber thread started")

    def _redis_subscriber_loop(self):
        """Background thread for Redis pub/sub using RedisProvider."""
        
        if not self._redis_client:
            logger.warning("⚠️ No Redis client, subscriber thread exiting")
            return
        
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        
        while self._running:
            try:
                # Use RedisProvider's pubsub method
                pubsub = self._redis_client.pubsub()
                if not pubsub:
                    logger.error("❌ Failed to create pubsub client")
                    time.sleep(5)
                    continue
                
                # Subscribe to video_updates channel
                pubsub.subscribe('video_updates')
                logger.info("🔄 Redis subscriber listening for messages")
                reconnect_attempts = 0
                
                for message in pubsub.listen():
                    if not self._running:
                        break
                    if message and message.get('type') == 'message':
                        try:
                            data = json.loads(message['data'])
                            self._handle_redis_video_update(data)
                        except json.JSONDecodeError as e:
                            logger.debug(f"Invalid JSON: {e}")
                        except Exception as e:
                            logger.debug(f"Message processing error: {e}")
                            
            except Exception as e:
                reconnect_attempts += 1
                logger.error(f"❌ Redis subscriber error (attempt {reconnect_attempts}/{max_reconnect_attempts}): {e}")
                
                if reconnect_attempts >= max_reconnect_attempts:
                    logger.error(f"⚠️ Max reconnect attempts reached")
                    break
                
                wait_time = min(2 ** reconnect_attempts, 30)
                logger.info(f"⏳ Reconnecting in {wait_time} seconds...")
                time.sleep(wait_time)
        
        logger.info("🛑 Redis subscriber thread exiting")
        self._running = False

    def _handle_redis_video_update(self, data: Dict[str, Any]) -> None:
        """Handle video update from Redis."""
        try:
            video_id = data.get('video_id')
            user_id = data.get('user_id')
            
            if not video_id:
                return
            
            if self._socketio:
                room = f"video:{video_id}"
                self._socketio.emit('video_processing', data, room=room)
                
                if user_id:
                    self._socketio.emit('video_processing', data, room=f"user:{user_id}")
                    
        except Exception as e:
            logger.error(f"Error handling Redis video update: {e}")

    def _register_event_handlers(self) -> None:
        """Register SocketIO event handlers."""
        if not self._socketio:
            return
        
        @self._socketio.on('connect')
        def handle_connect():
            sid = self._get_sid()
            logger.info(f"🔌 Client connected: {sid}")
            self._clients[sid] = {
                'connected_at': datetime.utcnow().isoformat(),
                'rooms': [],
                'user_id': None,
            }
            emit('connected', {'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})
        
        @self._socketio.on('disconnect')
        def handle_disconnect():
            sid = self._get_sid()
            logger.info(f"🔌 Client disconnected: {sid}")
            if sid in self._clients:
                del self._clients[sid]
            if sid in self._client_rooms:
                del self._client_rooms[sid]
        
        @self._socketio.on('subscribe_video')
        def handle_subscribe(data: Dict[str, Any]):
            sid = self._get_sid()
            video_id = data.get('video_id')
            if not video_id:
                emit('error', {'message': 'video_id required'})
                return
            
            room = f"video:{video_id}"
            join_room(room)
            
            if sid in self._client_rooms:
                if room not in self._client_rooms[sid]:
                    self._client_rooms[sid].append(room)
            else:
                self._client_rooms[sid] = [room]
            
            if sid in self._clients:
                if 'rooms' not in self._clients[sid]:
                    self._clients[sid]['rooms'] = []
                if room not in self._clients[sid]['rooms']:
                    self._clients[sid]['rooms'].append(room)
                self._clients[sid]['user_id'] = data.get('user_id')
            
            logger.info(f"📡 Client {sid} subscribed to video: {video_id}")
            emit('subscribed', {'video_id': video_id})
        
        @self._socketio.on('ping')
        def handle_ping(data: Optional[Dict] = None):
            emit('pong', {'timestamp': datetime.utcnow().isoformat(), 'data': data})

    def _get_sid(self) -> str:
        from flask import request
        return request.sid

    # ========== PUBLIC API ==========

    def emit_video_update(
        self,
        video_id: str,
        user_id: str,
        status: str,
        progress: float,
        step: Optional[str] = None,
        message: Optional[str] = None,
        publish_to_redis: bool = True
    ) -> bool:
        if step is None:
            step = status
        
        data = {
            'video_id': video_id,
            'user_id': user_id,
            'status': status,
            'progress': progress,
            'current_step': step,
            'step': step,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        try:
            if self._socketio:
                self._socketio.emit('video_processing', data, room=f"video:{video_id}")
                if user_id:
                    self._socketio.emit('video_processing', data, room=f"user:{user_id}")
            
            if publish_to_redis and self._redis_client:
                # RedisProvider's publish method handles JSON serialization
                self._redis_client.publish('video_updates', data)  # ← data can be dict
                # self._redis_client.publish('video_updates', json.dumps(data))
                logger.debug(f"📤 Published to Redis: {video_id}")
            
            return True
        except Exception as e:
            logger.error(f"Emit video update error: {e}")
            return False

    def emit_video_completed(
        self,
        video_id: str,
        user_id: str,
        result_url: str,
        processing_time: float,
        total_cost: float
    ) -> bool:
        data = {
            'video_id': video_id,
            'user_id': user_id,
            'status': 'completed',
            'result_url': result_url,
            'processing_time': processing_time,
            'total_cost': total_cost,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        try:
            if self._socketio:
                self._socketio.emit('video_completed', data, room=f"video:{video_id}")
                if user_id:
                    self._socketio.emit('video_completed', data, room=f"user:{user_id}")
            
            if self._redis_client:
                self._redis_client.publish('video_updates', json.dumps(data))
            
            logger.info(f"✅ Video completed event sent: {video_id}")
            return True
        except Exception as e:
            logger.error(f"Video completed event error: {e}")
            return False

    def emit_video_failed(
        self,
        video_id: str,
        user_id: str,
        error_message: str,
        retry_count: int = 0,
        can_retry: bool = True
    ) -> bool:
        data = {
            'video_id': video_id,
            'user_id': user_id,
            'status': 'failed',
            'error_message': error_message,
            'retry_count': retry_count,
            'can_retry': can_retry,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        try:
            if self._socketio:
                self._socketio.emit('video_failed', data, room=f"video:{video_id}")
                if user_id:
                    self._socketio.emit('video_failed', data, room=f"user:{user_id}")
            
            if self._redis_client:
                self._redis_client.publish('video_updates', json.dumps(data))
            
            logger.warning(f"❌ Video failed event sent: {video_id}")
            return True
        except Exception as e:
            logger.error(f"Video failed event error: {e}")
            return False
    
    def get_connected_clients_count(self) -> int:
        return len(self._clients)
    
    def get_client_stats(self) -> Dict[str, Any]:
        return {
            'total_clients': len(self._clients),
            'total_rooms': len(self._client_rooms),
            'timestamp': datetime.utcnow().isoformat(),
        }


# Global instance
_ws_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    return _ws_manager


def init_websocket(app: Flask) -> SocketIO:
    manager = get_ws_manager()
    manager.init_app(app)
    return manager._socketio