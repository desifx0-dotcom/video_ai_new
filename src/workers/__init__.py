"""
Worker processes for video processing.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class BaseWorker(ABC):
    """Base worker class for all video processing workers."""
    
    def __init__(self, worker_id: str, config: Dict[str, Any] = None):
        self.worker_id = worker_id
        self.config = config or {}
        self.is_running = False
        self.current_task = None
        self.stats = {
            'tasks_completed': 0,
            'tasks_failed': 0,
            'total_processing_time': 0,
            'last_task_time': None
        }
    
    @abstractmethod
    def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task."""
        pass
    
    @abstractmethod
    def can_process(self, task_data: Dict[str, Any]) -> bool:
        """Check if worker can process the given task."""
        pass
    
    def start(self):
        """Start the worker."""
        self.is_running = True
        logger.info(f"Worker {self.worker_id} started")
    
    def stop(self):
        """Stop the worker."""
        self.is_running = False
        logger.info(f"Worker {self.worker_id} stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker status."""
        return {
            'worker_id': self.worker_id,
            'is_running': self.is_running,
            'current_task': self.current_task,
            'stats': self.stats
        }
    
    def update_stats(self, success: bool, processing_time: float):
        """Update worker statistics."""
        if success:
            self.stats['tasks_completed'] += 1
        else:
            self.stats['tasks_failed'] += 1
        
        self.stats['total_processing_time'] += processing_time
        self.stats['last_task_time'] = processing_time