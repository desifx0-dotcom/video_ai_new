"""
Cache abstraction layer.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, Union, Dict, List
import json
import pickle
from datetime import datetime, timedelta

class Cache(ABC):
    """Abstract cache interface."""
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
    
    @abstractmethod
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration for key."""
        pass
    
    @abstractmethod
    def ttl(self, key: str) -> Optional[int]:
        """Get time to live for key."""
        pass
    
    @abstractmethod
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment value."""
        pass
    
    @abstractmethod
    def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement value."""
        pass
    
    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cache."""
        pass
    
    def get_json(self, key: str, default: Any = None) -> Any:
        """Get JSON value from cache."""
        value = self.get(key)
        if value is None:
            return default
        
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    
    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set JSON value in cache."""
        try:
            json_value = json.dumps(value)
            return self.set(key, json_value, ttl)
        except (TypeError, ValueError):
            return False
    
    def get_pickle(self, key: str, default: Any = None) -> Any:
        """Get pickled value from cache."""
        value = self.get(key)
        if value is None:
            return default
        
        try:
            return pickle.loads(value)
        except (pickle.PickleError, TypeError):
            return default
    
    def set_pickle(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set pickled value in cache."""
        try:
            pickle_value = pickle.dumps(value)
            return self.set(key, pickle_value, ttl)
        except (pickle.PickleError, TypeError):
            return False
    
    def get_or_set(self, key: str, default: Any, ttl: Optional[int] = None) -> Any:
        """Get value or set default if not exists."""
        value = self.get(key)
        if value is None:
            self.set(key, default, ttl)
            return default
        return value
    
    def memoize(self, ttl: Optional[int] = None):
        """Decorator for caching function results."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"memoize:{':'.join(key_parts)}"
                
                # Try to get from cache
                cached = self.get(cache_key)
                if cached is not None:
                    return cached
                
                # Call function and cache result
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result
            return wrapper
        return decorator

class RedisCache(Cache):
    """Redis-based cache implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        import redis
        
        config = config or {}
        self.client = redis.Redis(
            host=config.get('host', 'localhost'),
            port=config.get('port', 6379),
            db=config.get('db', 0),
            password=config.get('password'),
            decode_responses=config.get('decode_responses', True),
            socket_timeout=config.get('socket_timeout', 5),
            socket_connect_timeout=config.get('socket_connect_timeout', 5),
            retry_on_timeout=config.get('retry_on_timeout', True)
        )
        
        # Test connection
        try:
            self.client.ping()
        except redis.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from Redis."""
        try:
            value = self.client.get(key)
            return value if value is not None else default
        except Exception as e:
            # Log error and return default
            import logging
            logging.error(f"Redis get error for key {key}: {e}")
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis."""
        try:
            if ttl is not None:
                return bool(self.client.setex(key, ttl, value))
            else:
                return bool(self.client.set(key, value))
        except Exception as e:
            import logging
            logging.error(f"Redis set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from Redis."""
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            import logging
            logging.error(f"Redis delete error for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            import logging
            logging.error(f"Redis exists error for key {key}: {e}")
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration for key."""
        try:
            return bool(self.client.expire(key, ttl))
        except Exception as e:
            import logging
            logging.error(f"Redis expire error for key {key}: {e}")
            return False
    
    def ttl(self, key: str) -> Optional[int]:
        """Get time to live for key."""
        try:
            ttl = self.client.ttl(key)
            return ttl if ttl >= 0 else None
        except Exception as e:
            import logging
            logging.error(f"Redis ttl error for key {key}: {e}")
            return None
    
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment value."""
        try:
            return self.client.incrby(key, amount)
        except Exception as e:
            import logging
            logging.error(f"Redis increment error for key {key}: {e}")
            return 0
    
    def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement value."""
        try:
            return self.client.decrby(key, amount)
        except Exception as e:
            import logging
            logging.error(f"Redis decrement error for key {key}: {e}")
            return 0
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        try:
            return self.client.keys(pattern)
        except Exception as e:
            import logging
            logging.error(f"Redis keys error for pattern {pattern}: {e}")
            return []
    
    def clear(self) -> bool:
        """Clear all cache."""
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            import logging
            logging.error(f"Redis clear error: {e}")
            return False
    
    def hget(self, key: str, field: str, default: Any = None) -> Any:
        """Get hash field value."""
        try:
            value = self.client.hget(key, field)
            return value if value is not None else default
        except Exception as e:
            import logging
            logging.error(f"Redis hget error for key {key}, field {field}: {e}")
            return default
    
    def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field value."""
        try:
            return bool(self.client.hset(key, field, value))
        except Exception as e:
            import logging
            logging.error(f"Redis hset error for key {key}, field {field}: {e}")
            return False
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields and values."""
        try:
            return self.client.hgetall(key)
        except Exception as e:
            import logging
            logging.error(f"Redis hgetall error for key {key}: {e}")
            return {}
    
    def sadd(self, key: str, *members: Any) -> int:
        """Add members to set."""
        try:
            return self.client.sadd(key, *members)
        except Exception as e:
            import logging
            logging.error(f"Redis sadd error for key {key}: {e}")
            return 0
    
    def smembers(self, key: str) -> set:
        """Get all set members."""
        try:
            return set(self.client.smembers(key))
        except Exception as e:
            import logging
            logging.error(f"Redis smembers error for key {key}: {e}")
            return set()
    
    def zadd(self, key: str, mapping: Dict[Any, float]) -> int:
        """Add members to sorted set with scores."""
        try:
            return self.client.zadd(key, mapping)
        except Exception as e:
            import logging
            logging.error(f"Redis zadd error for key {key}: {e}")
            return 0
    
    def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> List:
        """Get range from sorted set."""
        try:
            return self.client.zrange(key, start, end, withscores=withscores)
        except Exception as e:
            import logging
            logging.error(f"Redis zrange error for key {key}: {e}")
            return []
    
    def pipeline(self):
        """Get pipeline for batch operations."""
        return self.client.pipeline()

class MemoryCache(Cache):
    """In-memory cache implementation."""
    
    def __init__(self):
        self._cache = {}
        self._expirations = {}
        import threading
        self._lock = threading.RLock()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from memory cache."""
        with self._lock:
            # Check expiration
            if key in self._expirations:
                if datetime.utcnow() > self._expirations[key]:
                    del self._cache[key]
                    del self._expirations[key]
                    return default
            
            return self._cache.get(key, default)
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in memory cache."""
        with self._lock:
            self._cache[key] = value
            
            if ttl is not None:
                self._expirations[key] = datetime.utcnow() + timedelta(seconds=ttl)
            elif key in self._expirations:
                del self._expirations[key]
            
            return True
    
    def delete(self, key: str) -> bool:
        """Delete value from memory cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            
            if key in self._expirations:
                del self._expirations[key]
            
            return True
    
    def exists(self, key: str) -> bool:
        """Check if key exists in memory cache."""
        with self._lock:
            # Check expiration
            if key in self._expirations:
                if datetime.utcnow() > self._expirations[key]:
                    del self._cache[key]
                    del self._expirations[key]
                    return False
            
            return key in self._cache
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration for key."""
        with self._lock:
            if key not in self._cache:
                return False
            
            self._expirations[key] = datetime.utcnow() + timedelta(seconds=ttl)
            return True
    
    def ttl(self, key: str) -> Optional[int]:
        """Get time to live for key."""
        with self._lock:
            if key not in self._expirations:
                return None
            
            expiration = self._expirations[key]
            now = datetime.utcnow()
            
            if now > expiration:
                del self._cache[key]
                del self._expirations[key]
                return None
            
            return int((expiration - now).total_seconds())
    
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment value."""
        with self._lock:
            current = self.get(key, 0)
            if not isinstance(current, (int, float)):
                current = 0
            
            new_value = current + amount
            self.set(key, new_value)
            
            # Preserve TTL if exists
            if key in self._expirations:
                self._expirations[key] = self._expirations[key]
            
            return new_value
    
    def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement value."""
        return self.increment(key, -amount)
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        import fnmatch
        
        with self._lock:
            # Clean expired keys first
            self._clean_expired()
            
            if pattern == "*":
                return list(self._cache.keys())
            
            return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
    
    def clear(self) -> bool:
        """Clear all cache."""
        with self._lock:
            self._cache.clear()
            self._expirations.clear()
            return True
    
    def _clean_expired(self):
        """Clean expired keys."""
        now = datetime.utcnow()
        expired_keys = [
            k for k, exp in self._expirations.items()
            if now > exp
        ]
        
        for key in expired_keys:
            if key in self._cache:
                del self._cache[key]
            del self._expirations[key]
    
    def get_size(self) -> int:
        """Get number of items in cache."""
        with self._lock:
            self._clean_expired()
            return len(self._cache)
    
    def get_memory_usage(self) -> int:
        """Get estimated memory usage in bytes."""
        import sys
        
        with self._lock:
            total = 0
            for key, value in self._cache.items():
                total += sys.getsizeof(key) + sys.getsizeof(value)
            
            for key, expiration in self._expirations.items():
                total += sys.getsizeof(key) + sys.getsizeof(expiration)
            
            return total