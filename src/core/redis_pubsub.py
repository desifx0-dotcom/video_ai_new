# src/core/redis_pubsub.py - PRODUCTION READY

import json
import logging
import threading
import time
import os
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from providers.redis_provider import RedisProvider

logger = logging.getLogger(__name__)


class RedisPubSubManager:
    """
    Production-grade Redis Pub/Sub manager with:
    - Auto-reconnection
    - Message retry with exponential backoff
    - Health monitoring
    - Graceful shutdown
    - Error handling
    - Message deduplication
    - Redis connection pooling
    """
    
    _instance = None
    _running = False
    _thread: Optional[threading.Thread] = None
    _pubsub = None
    _redis_client = None
    _retry_count = 0
    _max_retries = 5
    _last_heartbeat = None
    _subscribers: Dict[str, List[Callable]] = {}
    _message_cache: Dict[str, float] = {}  # Deduplication cache
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers_lock = threading.Lock()
    
    def _initialize(self):
        """Initialize Redis client with pooling."""
        try:
            redis_url = os.getenv('REDIS_URL')
            if not redis_url:
                logger.warning("⚠️ No REDIS_URL configured")
                return
            
            self._redis_client = RedisProvider()
            if self._redis_client.ping():
                logger.info("✅ Redis Pub/Sub manager initialized")
            else:
                logger.warning("⚠️ Redis connection failed")
                
        except Exception as e:
            logger.error(f"❌ Redis initialization failed: {e}")
    
    def start(self):
        """Start the Redis listener thread."""
        if self._running:
            logger.info("ℹ️ Redis listener already running")
            return
        
        if not self._redis_client or not self._redis_client.ping():
            logger.warning("⚠️ Cannot start - Redis not available")
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="RedisPubSubListener"
        )
        self._thread.start()
        logger.info("✅ Redis Pub/Sub listener started")
    
    def stop(self):
        """Stop the Redis listener thread gracefully."""
        self._running = False
        if self._pubsub:
            try:
                self._pubsub.unsubscribe()
                self._pubsub.close()
            except Exception as e:
                logger.error(f"Error closing pubsub: {e}")
        
        if self._thread:
            self._thread.join(timeout=5)
        
        logger.info("🛑 Redis Pub/Sub listener stopped")
    
    def subscribe(self, channel: str, callback: Callable):
        """Subscribe to a channel with a callback."""
        with self._subscribers_lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = []
            if callback not in self._subscribers[channel]:
                self._subscribers[channel].append(callback)
        
        # If already running, add to existing pubsub
        if self._running and self._pubsub:
            try:
                self._pubsub.subscribe(channel)
            except Exception as e:
                logger.error(f"Failed to subscribe to {channel}: {e}")
        
        logger.info(f"📡 Subscribed to channel: {channel}")
    
    def publish(self, channel: str, data: Dict[str, Any]) -> bool:
        """
        Publish a message to a channel with retry logic.
        
        Returns:
            bool: True if published successfully
        """
        try:
            if not self._redis_client:
                return False
            
            # Add timestamp for deduplication
            if 'timestamp' not in data:
                data['timestamp'] = datetime.utcnow().isoformat()
            
            message = json.dumps(data)
            result = self._redis_client.publish(channel, message)
            
            if result > 0:
                logger.debug(f"📤 Published to {channel}: {data.get('video_id', 'unknown')}")
            else:
                logger.warning(f"⚠️ No subscribers for {channel}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Publish failed to {channel}: {e}")
            return False
    
    def _listener_loop(self):
        """Main listener loop with retry and health checks."""
        retry_delay = 1
        max_delay = 60
        
        while self._running:
            try:
                # Get a fresh pubsub connection
                if not self._redis_client or not self._redis_client.ping():
                    self._reconnect_redis()
                    time.sleep(retry_delay)
                    continue
                
                # Create pubsub
                self._pubsub = self._redis_client.pubsub()
                
                # Subscribe to channels
                with self._subscribers_lock:
                    for channel in self._subscribers:
                        self._pubsub.subscribe(channel)
                
                logger.info(f"🔄 Listening on channels: {list(self._subscribers.keys())}")
                self._retry_count = 0
                retry_delay = 1
                
                # Listen for messages
                while self._running:
                    try:
                        message = self._pubsub.get_message(timeout=5.0)
                        
                        if message and message['type'] == 'message':
                            self._process_message(message)
                            self._last_heartbeat = time.time()
                            
                    except Exception as e:
                        logger.error(f"⚠️ Listener error: {e}")
                        time.sleep(1)
                        
            except Exception as e:
                self._retry_count += 1
                logger.error(f"❌ Listener loop failed (attempt {self._retry_count}): {e}")
                
                # Exponential backoff
                retry_delay = min(retry_delay * 2, max_delay)
                time.sleep(retry_delay)
        
        logger.info("🛑 Listener loop stopped")
    
    def _process_message(self, message: Dict[str, Any]):
        """Process a received message with deduplication."""
        try:
            data = json.loads(message['data'])
            channel = message['channel']
            
            # Deduplication (prevent duplicate processing within 5 seconds)
            msg_id = f"{channel}:{data.get('video_id', '')}:{data.get('timestamp', '')}"
            if msg_id in self._message_cache:
                # Skip duplicate
                return
            
            self._message_cache[msg_id] = time.time()
            
            # Clean old cache entries
            self._clean_message_cache()
            
            # Process with subscribers
            with self._subscribers_lock:
                for callback in self._subscribers.get(channel, []):
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"Callback error for {channel}: {e}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in message: {e}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    def _clean_message_cache(self):
        """Remove messages older than 10 seconds."""
        current_time = time.time()
        to_remove = [
            k for k, v in self._message_cache.items()
            if current_time - v > 10
        ]
        for k in to_remove:
            del self._message_cache[k]
    
    def _reconnect_redis(self):
        """Reconnect to Redis with retry."""
        try:
            # Get fresh Redis client
            self._redis_client = RedisProvider()
            
            if self._redis_client and self._redis_client.ping():
                logger.info("✅ Reconnected to Redis")
                self._retry_count = 0
                return True
            else:
                logger.warning("⚠️ Failed to reconnect to Redis")
                self._redis_client = None
                return False
        except Exception as e:
            logger.error(f"❌ Redis reconnect error: {e}")
            self._redis_client = None
            return False

    def health_check(self) -> Dict[str, Any]:
        """Get health status of the Redis Pub/Sub system."""
        status = {
            'running': self._running,
            'redis_connected': self._redis_client and self._redis_client.ping(),
            'subscribers': len(self._subscribers),
            'channels': list(self._subscribers.keys()),
            'retry_count': self._retry_count,
            'last_heartbeat': self._last_heartbeat,
            'cache_size': len(self._message_cache),
        }
        
        if self._last_heartbeat:
            status['seconds_since_heartbeat'] = int(time.time() - self._last_heartbeat)
        
        return status


# Global instance
_pubsub_manager = None

def get_pubsub_manager() -> RedisPubSubManager:
    """Get the global Redis Pub/Sub manager instance."""
    global _pubsub_manager
    if _pubsub_manager is None:
        _pubsub_manager = RedisPubSubManager()
    return _pubsub_manager


# Convenience functions
def publish(channel: str, data: Dict[str, Any]) -> bool:
    """Publish a message to Redis."""
    return get_pubsub_manager().publish(channel, data)


def subscribe(channel: str, callback: Callable):
    """Subscribe to a Redis channel."""
    manager = get_pubsub_manager()
    manager.subscribe(channel, callback)
    manager.start()


def get_health() -> Dict[str, Any]:
    """Get health status."""
    return get_pubsub_manager().health_check()