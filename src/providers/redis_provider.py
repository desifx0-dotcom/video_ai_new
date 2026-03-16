"""Redis provider with automatic mock fallback for development."""

import os
import logging
from typing import Any, Dict, Optional, List, Union

# Configure logger
logger = logging.getLogger(__name__)

# Determine which provider to use
USE_MOCK = True  # Default to safe mode

# Check if we should use real Redis (only in production with clear intent)
if os.getenv("FLASK_ENV") == "production" and os.getenv("REDIS_PROVIDER") == "real":
    USE_MOCK = False

if USE_MOCK:
    # Use mock Redis
    from .redis_mock import MockRedisProvider

    class RedisProvider(MockRedisProvider):
        """Redis provider using mock implementation for development."""

        pass

    logger.info("✅ Using Mock Redis Provider (development mode)")

else:
    # Use real Redis in production
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
                    logger.info(f"✅ Redis connected: {redis_url}")

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
        from .redis_mock import MockRedisProvider

        RedisProvider = MockRedisProvider
        logger.warning("⚠️  Falling back to Mock Redis Provider")
