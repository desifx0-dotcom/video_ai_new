"""
Redis provider with real Redis and mock fallback for development.
"""

import os
import json
import logging
import re
import time
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
        import redis as redis_lib
        from redis.exceptions import RedisError
        from core.exceptions import ConfigurationError

        class RedisProvider:
            """Production Redis provider with connection pooling and Pub/Sub."""

            _instance = None
            _client = None
            _pubsub = None
            _initialized = False

            def __new__(cls):
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                return cls._instance

            def __init__(self):
                if not self._initialized:
                    self._initialize()
                    self._initialized = True

            def _initialize(self):
                """Initialize Redis connection with proper error handling."""
                try:
                    # Prevent re-initialization if already initialized and connected
                    if self._client is not None:
                        try:
                            self._client.ping()
                            return  # Already connected
                        except:
                            self._client = None  # Connection lost, re-initialize
                    
                    redis_url = os.getenv("REDIS_URL")
                    if not redis_url or redis_url in ["mock://", "memory://"]:
                        logger.info("📦 No Redis URL configured, using mock mode")
                        self._client = None
                        return

                    if os.getenv("REDIS_MOCK_MODE", "").lower() in ["true", "1", "yes"]:
                        logger.info("📦 Redis mock mode enabled via env var")
                        self._client = None
                        return

                    from urllib.parse import urlparse
                    import re

                    parsed = urlparse(redis_url)
                    hostname = parsed.hostname
                    clean_url = redis_url

                    # Check if hostname is already an IP
                    is_ip = re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', hostname) if hostname else False

                    if not is_ip and hostname:
                        # Try to resolve hostname to IP
                        try:
                            import socket
                            socket.setdefaulttimeout(5)
                            ip = socket.gethostbyname(hostname)
                            clean_url = redis_url.replace(hostname, ip)
                            logger.info(f"✅ Resolved {hostname} -> {ip}")
                        except Exception as e:
                            logger.warning(f"⚠️ DNS resolution failed ({e}), using original URL")
                            clean_url = redis_url

                    # Create Redis client with retry logic
                    retry_count = 0
                    max_retries = 3
                    last_error = None

                    while retry_count < max_retries:
                        try:
                            self._client = redis_lib.from_url(
                                clean_url,
                                decode_responses=True,
                                socket_connect_timeout=10,
                                socket_timeout=10,
                                socket_keepalive=True,
                                health_check_interval=30,
                                retry_on_timeout=True,
                                max_connections=50,
                                retry_on_error=[
                                    redis_lib.exceptions.ConnectionError,
                                    redis_lib.exceptions.TimeoutError
                                ],
                            )
                            
                            # Test connection
                            self._client.ping()
                            logger.info(f"✅ Redis connected successfully")
                            return
                            
                        except Exception as e:
                            last_error = e
                            retry_count += 1
                            logger.warning(f"⚠️ Redis connection attempt {retry_count}/{max_retries} failed: {e}")
                            
                            if retry_count < max_retries:
                                time.sleep(1 * retry_count)
                            else:
                                logger.error(f"❌ Redis connection failed after {max_retries} attempts: {last_error}")
                                self._client = None
                                return

                except Exception as e:
                    logger.error(f"❌ Redis initialization failed: {e}")
                    self._client = None
                    
            # ========== BASIC OPERATIONS ==========

            def set(self, key: str, value: Union[str, Dict, List], expire: Optional[int] = None) -> bool:
                """Set key-value pair."""
                try:
                    if self._client is None:
                        return False
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
                    if self._client is None:
                        return default
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
                    if self._client is None:
                        return False
                    return bool(self._client.delete(key))
                except Exception as e:
                    logger.error(f"Redis delete error for {key}: {e}")
                    return False

            def exists(self, key: str) -> bool:
                """Check if key exists."""
                try:
                    if self._client is None:
                        return False
                    return bool(self._client.exists(key))
                except Exception as e:
                    logger.error(f"Redis exists error for {key}: {e}")
                    return False

            def expire(self, key: str, seconds: int) -> bool:
                """Set expiration."""
                try:
                    if self._client is None:
                        return False
                    return bool(self._client.expire(key, seconds))
                except Exception as e:
                    logger.error(f"Redis expire error for {key}: {e}")
                    return False

            def incr(self, key: str, amount: int = 1) -> int:
                """Increment value."""
                try:
                    if self._client is None:
                        return 0
                    return self._client.incr(key, amount)
                except Exception as e:
                    logger.error(f"Redis incr error for {key}: {e}")
                    return 0

            # ========== HASH OPERATIONS ==========

            def hset(self, key: str, field: str, value: Any) -> bool:
                """Set hash field."""
                try:
                    if self._client is None:
                        return False
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    return bool(self._client.hset(key, field, value))
                except Exception as e:
                    logger.error(f"Redis hset error for {key}.{field}: {e}")
                    return False

            def hget(self, key: str, field: str, default: Any = None) -> Any:
                """Get hash field."""
                try:
                    if self._client is None:
                        return default
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
                    if self._client is None:
                        return {}
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

            # ========== PUB/SUB OPERATIONS ==========

            def publish(self, channel: str, message: Any) -> int:
                """Publish message to Redis channel."""
                try:
                    if self._client is None:
                        return 0
                    if isinstance(message, (dict, list)):
                        message = json.dumps(message)
                    return self._client.publish(channel, message)
                except Exception as e:
                    logger.error(f"Redis publish error to {channel}: {e}")
                    return 0

            def pubsub(self) -> Optional[redis_lib.client.PubSub]:
                """Get a Pub/Sub client."""
                try:
                    if self._client is None:
                        return None
                    return self._client.pubsub(ignore_subscribe_messages=True)
                except Exception as e:
                    logger.error(f"Redis pubsub error: {e}")
                    return None

            def subscribe(self, channel: str, callback: Callable) -> bool:
                """Subscribe to a Redis channel with a callback."""
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
                """Run a Pub/Sub listener loop in the current thread."""
                try:
                    pubsub = self.pubsub()
                    if not pubsub:
                        logger.error("❌ Redis Pub/Sub not available")
                        return
                    
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
                    time.sleep(5)

            # ========== UTILITY OPERATIONS ==========

            def ping(self) -> bool:
                """Ping Redis server with proper reconnection logic."""
                try:
                    # If client exists, try to ping
                    if self._client is not None:
                        try:
                            return self._client.ping()
                        except Exception as e:
                            # Connection lost, reset client
                            logger.warning(f"Redis ping failed, reconnecting: {e}")
                            self._client = None
                    
                    # Try to reconnect
                    if self._client is None:
                        self._initialize()
                        if self._client is not None:
                            try:
                                return self._client.ping()
                            except:
                                return False
                    
                    return False
                except Exception as e:
                    logger.error(f"Redis ping failed: {e}")
                    return False
    
            def flushall(self) -> bool:
                """Flush all databases."""
                try:
                    if self._client is None:
                        return False
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