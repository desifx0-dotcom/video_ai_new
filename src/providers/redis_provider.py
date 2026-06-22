"""
Redis provider with real Redis and mock fallback for development.
"""

import os
import json
import logging
from typing import Any, Dict, Optional, List, Union, Callable

logger = logging.getLogger(__name__)

# Determine which provider to use
USE_MOCK = False

# Check if we should use mock (only when explicitly configured)
if os.getenv("REDIS_PROVIDER") in ["mock", "memory"] or os.getenv("REDIS_URL") in ["mock://", "memory://"]:
    USE_MOCK = True
    logger.info("✅ Using Mock Redis Provider (explicitly configured)")

# Check if we have a valid Redis URL
redis_url = os.getenv("REDIS_URL", "")
if not redis_url or redis_url in ["mock://", "memory://"]:
    USE_MOCK = True
    logger.info("✅ No valid Redis URL, using mock mode")

# Also check for mock mode via environment
if os.getenv("REDIS_MOCK_MODE", "").lower() in ["true", "1", "yes"]:
    USE_MOCK = True
    logger.info("✅ Redis mock mode enabled via REDIS_MOCK_MODE")

if USE_MOCK:
    # Use mock Redis
    try:
        from .redis_mock import MockRedisProvider

        class RedisProvider(MockRedisProvider):
            """Redis provider using mock implementation for development."""

            pass

        logger.info("✅ Using Mock Redis Provider (development mode)")
    except ImportError:
        # Create a simple mock if redis_mock doesn't exist
        class RedisProvider:
            """Simple mock Redis provider."""

            _data = {}

            def ping(self):
                return True

            def set(self, key, value, ex=None):
                self._data[key] = value
                return True

            def get(self, key, default=None):
                return self._data.get(key, default)

            def delete(self, key):
                if key in self._data:
                    del self._data[key]
                    return 1
                return 0

            def exists(self, key):
                return key in self._data

            def publish(self, channel, message):
                return 0

            def pubsub(self):
                return None

        logger.info("✅ Using Simple Mock Redis Provider")

else:
    # Use real Redis
    try:
        import redis
        from redis.exceptions import RedisError
        from core.exceptions import ConfigurationError

        class RedisProvider:
            """Production Redis provider with connection pooling and Pub/Sub."""

            _instance = None
            _client = None
            _pubsub = None

            def __new__(cls):
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
                return cls._instance

            def _initialize(self):
                """Initialize Redis connection with proper error handling."""
                try:
                    redis_url = os.getenv("REDIS_URL")

                    # Check if we should use mock mode
                    if not redis_url or redis_url in ["mock://", "memory://"]:
                        logger.info("📦 No Redis URL configured, using mock mode")
                        self._client = None
                        return

                    if os.getenv("REDIS_MOCK_MODE", "").lower() in ["true", "1", "yes"]:
                        logger.info("📦 Redis mock mode enabled via env var")
                        self._client = None
                        return

                    # Use a DNS resolver that bypasses eventlet
                    import socket
                    import redis as redis_lib
                    
                    # Parse the URL to extract host
                    from urllib.parse import urlparse
                    parsed = urlparse(redis_url)

                    ip = parsed.hostname

                    # If it's the problematic hostname, replace with IP directly
                    if 'redis-15622.crce206.ap-south-1-1.ec2.cloud.redislabs.com' in parsed.hostname:
                        ip = '13.233.229.93'
                        # Reconstruct URL with IP
                        clean_url = f"{parsed.scheme}://{parsed.username}:{parsed.password}@{ip}:{parsed.port}"
                        logger.info(f"✅ Using IP instead of hostname: {ip}")
                    else:
                        clean_url = redis_url.replace('rediss://', 'redis://')
                    
                    # Create Redis client with IP
                    self._client = redis_lib.from_url(
                        clean_url,
                        decode_responses=True,
                        socket_connect_timeout=10,
                        socket_timeout=10,
                        socket_keepalive=True,
                        health_check_interval=30,
                        retry_on_timeout=True,
                        max_connections=50,
                        retry_on_error=[redis_lib.exceptions.ConnectionError, redis_lib.exceptions.TimeoutError],
                    )
                    
                    # Test connection
                    self._client.ping()
                    logger.info(f"✅ Redis connected successfully via IP: {ip}")

                except Exception as e:
                    logger.error(f"❌ Redis connection failed: {e}")
                    self._client = None
                    
            # ========== BASIC OPERATIONS ==========

            def set(
                self,
                key: str,
                value: Union[str, Dict, List],
                expire: Optional[int] = None,
            ) -> bool:
                """Set key-value pair."""
                try:
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    if expire:
                        self._client.setex(key, expire, value)
                    else:
                        self._client.set(key, value)
                    return True
                except Exception as e:
                    logger.error(f"Redis set error for {key}: {e}")
                    return False

            def get(self, key: str, default: Any = None) -> Any:
                """Get value by key."""
                try:
                    value = self._client.get(key)
                    if value is None:
                        return default
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                except Exception as e:
                    logger.error(f"Redis get error for {key}: {e}")
                    return default

            def delete(self, key: str) -> bool:
                """Delete key."""
                try:
                    return bool(self._client.delete(key))
                except Exception as e:
                    logger.error(f"Redis delete error for {key}: {e}")
                    return False

            def exists(self, key: str) -> bool:
                """Check if key exists."""
                try:
                    return bool(self._client.exists(key))
                except Exception as e:
                    logger.error(f"Redis exists error for {key}: {e}")
                    return False

            def expire(self, key: str, seconds: int) -> bool:
                """Set expiration."""
                try:
                    return bool(self._client.expire(key, seconds))
                except Exception as e:
                    logger.error(f"Redis expire error for {key}: {e}")
                    return False

            def incr(self, key: str, amount: int = 1) -> int:
                """Increment value."""
                try:
                    return self._client.incr(key, amount)
                except Exception as e:
                    logger.error(f"Redis incr error for {key}: {e}")
                    return 0

            # ========== HASH OPERATIONS ==========

            def hset(self, key: str, field: str, value: Any) -> bool:
                """Set hash field."""
                try:
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    return bool(self._client.hset(key, field, value))
                except Exception as e:
                    logger.error(f"Redis hset error for {key}.{field}: {e}")
                    return False

            def hget(self, key: str, field: str, default: Any = None) -> Any:
                """Get hash field."""
                try:
                    value = self._client.hget(key, field)
                    if value is None:
                        return default
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                except Exception as e:
                    logger.error(f"Redis hget error for {key}.{field}: {e}")
                    return default

            def hgetall(self, key: str) -> Dict[str, Any]:
                """Get all hash fields."""
                try:
                    data = self._client.hgetall(key)
                    result = {}
                    for field, value in data.items():
                        try:
                            result[field] = json.loads(value)
                        except json.JSONDecodeError:
                            result[field] = value
                    return result
                except Exception as e:
                    logger.error(f"Redis hgetall error for {key}: {e}")
                    return {}

            # ========== PUB/SUB OPERATIONS (NEW) ==========

            def publish(self, channel: str, message: Any) -> int:
                """
                Publish message to Redis channel.
                
                Args:
                    channel: Channel name
                    message: Message to publish (dict/list will be JSON serialized)
                
                Returns:
                    Number of subscribers that received the message
                """
                try:
                    if isinstance(message, (dict, list)):
                        message = json.dumps(message)
                    return self._client.publish(channel, message)
                except Exception as e:
                    logger.error(f"Redis publish error to {channel}: {e}")
                    return 0

            def pubsub(self) -> Optional[redis.client.PubSub]:
                """
                Get a Pub/Sub client.
                Returns None if Redis is not available.
                """
                try:
                    if self._client:
                        return self._client.pubsub(
                            ignore_subscribe_messages=True
                        )
                    return None
                except Exception as e:
                    logger.error(f"Redis pubsub error: {e}")
                    return None

            def subscribe(self, channel: str, callback: Callable) -> bool:
                """
                Subscribe to a Redis channel with a callback.
                
                Args:
                    channel: Channel name to subscribe to
                    callback: Function to call when message is received
                
                Returns:
                    True if subscribed successfully
                """
                try:
                    pubsub = self.pubsub()
                    if pubsub:
                        pubsub.subscribe(**{channel: callback})
                        logger.info(f"✅ Subscribed to Redis channel: {channel}")
                        return True
                    return False
                except Exception as e:
                    logger.error(f"Redis subscribe error for {channel}: {e}")
                    return False

            def unsubscribe(self, channel: str) -> bool:
                """Unsubscribe from a Redis channel."""
                try:
                    pubsub = self.pubsub()
                    if pubsub:
                        pubsub.unsubscribe(channel)
                        logger.info(f"✅ Unsubscribed from Redis channel: {channel}")
                        return True
                    return False
                except Exception as e:
                    logger.error(f"Redis unsubscribe error for {channel}: {e}")
                    return False

            def run_pubsub_loop(self, callback: Callable, channels: List[str]):
                """
                Run a Pub/Sub listener loop in the current thread.
                
                Args:
                    callback: Function to call for each message (receives message dict)
                    channels: List of channels to subscribe to
                """
                try:
                    pubsub = self.pubsub()
                    if not pubsub:
                        logger.error("❌ Redis Pub/Sub not available")
                        return
                    
                    # Subscribe to channels
                    for channel in channels:
                        pubsub.subscribe(channel)
                        logger.info(f"✅ Subscribed to channel: {channel}")
                    
                    logger.info(f"🔄 Running Redis Pub/Sub listener loop (channels: {channels})...")
                    
                    for message in pubsub.listen():
                        if message['type'] == 'message':
                            try:
                                callback(message)
                            except Exception as e:
                                logger.error(f"Pub/Sub callback error: {e}")
                                
                except Exception as e:
                    logger.error(f"Redis Pub/Sub loop error: {e}")
                    import time
                    time.sleep(5)  # Wait before retry if needed

            # ========== UTILITY OPERATIONS ==========

            def ping(self) -> bool:
                """Ping Redis server."""
                try:
                    return self._client.ping()
                except Exception as e:
                    logger.error(f"Redis ping failed: {e}")
                    return False

            def flushall(self) -> bool:
                """Flush all databases."""
                try:
                    self._client.flushall()
                    return True
                except Exception as e:
                    logger.error(f"Redis flushall error: {e}")
                    return False

            def close(self):
                """Close connection."""
                try:
                    if self._client:
                        self._client.close()
                except Exception as e:
                    logger.error(f"Redis close error: {e}")

        logger.info("✅ Using Production Redis Provider")

    except ImportError as e:
        logger.error(f"Redis module not installed: {e}")

        # Fallback to mock if import fails
        class RedisProvider:
            """Fallback mock Redis provider."""

            _data = {}

            def ping(self):
                return True

            def set(self, key, value, ex=None):
                self._data[key] = value
                return True

            def get(self, key, default=None):
                return self._data.get(key, default)

            def delete(self, key):
                if key in self._data:
                    del self._data[key]
                    return 1
                return 0

            def exists(self, key):
                return key in self._data

            def publish(self, channel, message):
                return 0

            def pubsub(self):
                return None

            def subscribe(self, channel, callback):
                return False

            def run_pubsub_loop(self, callback, channels):
                pass

        logger.warning("⚠️ Falling back to Mock Redis Provider")