"""
Simple Redis-based status tracker for tasks.
No database needed - just temporary status storage.
"""

import redis
import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TaskStatusTracker:
    """Simple task status tracker using Redis."""

    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self.redis = redis.from_url(redis_url)
            self.redis.ping()
            logger.info("✅ TaskStatusTracker connected to Redis")
        except Exception as e:
            logger.warning(f"⚠️ Redis not available, using memory fallback: {e}")
            self.redis = None
            self._memory_store = {}

    def set_status(
        self,
        task_id: str,
        status: str,
        progress: int = 0,
        step: str = None,
        error: str = None,
    ):
        """Set task status."""
        data = {
            "status": status,  # pending, processing, completed, failed
            "progress": progress,
            "step": step or status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if error:
            data["error"] = error

        key = f"task:{task_id}"

        if self.redis:
            self.redis.setex(key, 3600, json.dumps(data))  # Expire after 1 hour
        else:
            self._memory_store[key] = data

        logger.info(f"📊 Task {task_id}: {status} - {progress}%")

    def get_status(self, task_id: str):
        """Get task status."""
        key = f"task:{task_id}"

        if self.redis:
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        else:
            if key in self._memory_store:
                return self._memory_store[key]

        return None

    def delete_status(self, task_id: str):
        """Delete task status (cleanup)."""
        key = f"task:{task_id}"
        if self.redis:
            self.redis.delete(key)
        elif key in self._memory_store:
            del self._memory_store[key]


# Singleton instance
status_tracker = TaskStatusTracker()
