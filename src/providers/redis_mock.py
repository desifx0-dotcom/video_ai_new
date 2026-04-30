"""Mock Redis provider for development without requiring Redis server."""

import os
import time
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from core.exceptions import ConfigurationError


class MockRedisProvider:
    """In-memory mock Redis provider for development."""

    _instance = None
    _initialized = False
    _data = {}  # In-memory key-value store
    _expiry = {}  # Track expiry times

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialize()

    def _initialize(self):
        """Initialize mock provider."""
        print(
            "✅ Using Mock Redis Provider (development mode - no Redis server needed)"
        )
        self._initialized = True

    def ping(self) -> bool:
        """Mock ping command."""
        return True

    def lpush(self, key: str, value: Any) -> int:
        """Push value to left of list."""
        if key not in self._data:
            self._data[key] = []
        self._data[key].insert(0, value)
        return len(self._data[key])

    def rpush(self, key: str, value: Any) -> int:
        """Push value to right of list."""
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(value)
        return len(self._data[key])

    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        """Get range of list."""
        if key not in self._data or not isinstance(self._data[key], list):
            return []
        return (
            self._data[key][start : end + 1] if end != -1 else self._data[key][start:]
        )

    def lpop(self, key: str) -> Optional[Any]:
        """Pop value from left of list."""
        if (
            key not in self._data
            or not isinstance(self._data[key], list)
            or not self._data[key]
        ):
            return None
        return self._data[key].pop(0)

    def rpop(self, key: str) -> Optional[Any]:
        """Pop value from right of list."""
        if (
            key not in self._data
            or not isinstance(self._data[key], list)
            or not self._data[key]
        ):
            return None
        return self._data[key].pop()

    def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim list to specified range."""
        if key not in self._data or not isinstance(self._data[key], list):
            return False
        self._data[key] = self._data[key][start : end + 1]
        return True

    def llen(self, key: str) -> int:
        """Get length of list."""
        if key not in self._data or not isinstance(self._data[key], list):
            return 0
        return len(self._data[key])

    def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern."""
        # Simple implementation - only supports "*" for now
        return list(self._data.keys())

    def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on key."""
        if key in self._data:
            self._expiry[key] = time.time() + seconds
            return True
        return False

    def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        # Check if expired
        if key in self._expiry:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return None

        return self._data.get(key)

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set key-value pair with optional expiry in seconds."""
        self._data[key] = value
        if ex:
            self._expiry[key] = time.time() + ex
        return True

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                if key in self._expiry:
                    del self._expiry[key]
                deleted += 1
        return deleted

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        if key in self._expiry:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return False
        return key in self._data

    def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on key."""
        if key in self._data:
            self._expiry[key] = time.time() + seconds
            return True
        return False

    def ttl(self, key: str) -> int:
        """Get time to live for key."""
        if key in self._expiry:
            remaining = self._expiry[key] - time.time()
            return max(0, int(remaining))
        return -1  # No expiry

    def incr(self, key: str) -> int:
        """Increment value by 1."""
        current = self.get(key)
        if current is None:
            current = 0
        new_value = int(current) + 1
        self.set(key, new_value)
        return new_value

    def sadd(self, key: str, *members: Any) -> int:
        """Add members to set."""
        if key not in self._data:
            self._data[key] = set()
        elif not isinstance(self._data[key], set):
            self._data[key] = set([self._data[key]])

        original_size = len(self._data[key])
        for member in members:
            self._data[key].add(member)

        return len(self._data[key]) - original_size

    def smembers(self, key: str) -> set:
        """Get all members in set."""
        if key not in self._data:
            return set()
        return self._data.get(key, set())

    def hset(self, key: str, field: str, value: Any) -> int:
        """Set hash field."""
        if key not in self._data:
            self._data[key] = {}
        elif not isinstance(self._data[key], dict):
            self._data[key] = {}

        self._data[key][field] = value
        return 1

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get hash field."""
        if key not in self._data or not isinstance(self._data[key], dict):
            return None
        return self._data[key].get(field)

    def hgetall(self, key: str) -> Dict:
        """Get all hash fields."""
        if key not in self._data or not isinstance(self._data[key], dict):
            return {}
        return self._data[key].copy()

    def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern."""
        # Simple implementation - only supports "*" for now
        return list(self._data.keys())

    def flushall(self) -> bool:
        """Clear all data."""
        self._data.clear()
        self._expiry.clear()
        return True

    def close(self):
        """Close connection."""
        pass


# For backward compatibility with code that imports RedisProvider
RedisProvider = MockRedisProvider
