"""
Redis provider with real Redis and mock fallback for development.
"""

import os
import logging
from typing import Any, Dict, Optional, List, Union

logger = logging.getLogger(__name__)

# Determine which provider to use
USE_MOCK = False  #  false to use real Redis if configured and true to use mock

# Check if we should use mock (only when explicitly configured)
if os.getenv("REDIS_PROVIDER") == "mock" or os.getenv("REDIS_URL") == "mock://":
    USE_MOCK = True
    logger.info("✅ Using Mock Redis Provider (explicitly configured)")

# Also check if we're explicitly using memory transport
if os.getenv("REDIS_PROVIDER") == "memory" or os.getenv("REDIS_URL") == "memory://":
    USE_MOCK = True
    logger.info("✅ Using Memory transport (no Redis required)")

# Check if we have a valid Redis URL
redis_url = os.getenv("REDIS_URL", "")
if not redis_url or redis_url in ["mock://", "memory://"]:
    USE_MOCK = True
    logger.info("✅ No valid Redis URL, using mock mode")

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

        logger.info("✅ Using Simple Mock Redis Provider")

else:
    # Use real Redis
    try:
        import redis
        from redis.exceptions import RedisError
        from core.exceptions import ConfigurationError
        import json

        class RedisProvider:
            """Production Redis provider with connection pooling."""

            _instance = None
            _client = None

            def __new__(cls):
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
                return cls._instance

            def _initialize(self):
                """Initialize Redis connection with proper error handling."""
                try:
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

                    # Validate URL
                    if not redis_url or redis_url in ["mock://", "memory://"]:
                        raise ValueError(f"Invalid Redis URL: {redis_url}")

                    self._client = redis.from_url(
                        redis_url,
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_keepalive=True,
                        health_check_interval=30,
                        retry_on_timeout=True,
                    )

                    # Test connection
                    self._client.ping()
                    logger.info(f"✅ Redis connected successfully")

                except Exception as e:
                    logger.error(f"❌ Redis connection failed: {e}")
                    raise ConfigurationError(f"Redis initialization failed: {e}")

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

            def publish(self, channel: str, message: Any) -> int:
                """Publish message to channel."""
                try:
                    if isinstance(message, (dict, list)):
                        message = json.dumps(message)
                    return self._client.publish(channel, message)
                except Exception as e:
                    logger.error(f"Redis publish error to {channel}: {e}")
                    return 0

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

        logger.warning("⚠️  Falling back to Mock Redis Provider")
