"""
Priority worker for Pro/Plus/Enterprise tier processing.
"""
import time
import threading
from typing import Dict, Any, List, Optional
import logging
from queue import PriorityQueue
from datetime import datetime

from . import BaseWorker
from .video_worker import VideoWorker
from .style_worker import StyleWorker
from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)

class PriorityWorker(BaseWorker):
    """
    Priority worker that handles high-priority tasks for Pro/Plus/Enterprise tiers.
    Uses multiple sub-workers with priority queue management.
    """
    
    def __init__(self, worker_id: str, config: Dict[str, Any] = None):
        super().__init__(worker_id, config)
        
        # Priority queue for tasks
        self.task_queue = PriorityQueue(maxsize=config.get('max_queue_size', 100))
        
        # Worker pool
        self.worker_pool = []
        self.max_workers = config.get('max_workers', 3)
        
        # Task priorities (higher number = higher priority)
        self.priority_map = {
            Tier.ENTERPRISE: 100,
            Tier.PLUS: 80,
            Tier.PRO: 60,
            Tier.STARTER: 40,
            Tier.FREE: 20
        }
        
        # Task categories
        self.task_categories = {
            'video_processing': VideoWorker,
            'style_processing': StyleWorker,
            'priority_processing': self.__class__
        }
        
        # Statistics
        self.queue_stats = {
            'tasks_queued': 0,
            'tasks_processed': 0,
            'average_wait_time': 0,
            'max_wait_time': 0
        }
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Initialize worker pool
        self._init_worker_pool()
        
        # Start queue processor
        self.processor_thread = threading.Thread(
            target=self._process_queue,
            daemon=True
        )
        self.processor_thread.start()
        
        logger.info(f"Priority Worker {worker_id} initialized with {self.max_workers} workers")
    
    def _init_worker_pool(self):
        """Initialize the worker pool."""
        for i in range(self.max_workers):
            worker_id = f"{self.worker_id}_sub_{i}"
            
            # Create appropriate worker based on configuration
            worker_type = self.config.get('worker_type', 'video_worker')
            
            if worker_type == 'style_worker':
                worker = StyleWorker(worker_id, self.config.get('worker_config', {}))
            else:
                worker = VideoWorker(worker_id, self.config.get('worker_config', {}))
            
            worker.start()
            self.worker_pool.append(worker)
    
    def can_process(self, task_data: Dict[str, Any]) -> bool:
        """Check if worker can process the given task."""
        # Priority worker can process any task by delegating to appropriate sub-worker
        task_type = task_data.get('task_type', 'video_processing')
        
        if task_type in self.task_categories:
            # Check if any sub-worker can process this
            for worker in self.worker_pool:
                if hasattr(worker, 'can_process') and worker.can_process(task_data):
                    return True
        
        return False
    
    def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a task with priority handling.
        
        Note: This method adds the task to the priority queue and returns immediately.
        Actual processing happens asynchronously in the queue processor.
        """
        start_time = time.time()
        task_id = task_data.get('task_id', 'unknown')
        
        # Calculate priority
        priority = self._calculate_priority(task_data)
        
        # Create task wrapper
        task_wrapper = {
            'priority': priority,
            'task_id': task_id,
            'task_data': task_data,
            'queued_at': datetime.utcnow(),
            'client_callback': task_data.get('callback_url')
        }
        
        # Add to priority queue
        try:
            self.task_queue.put((-priority, task_wrapper))  # Negative for max-heap behavior
            
            with self.lock:
                self.queue_stats['tasks_queued'] += 1
            
            logger.info(f"Task {task_id} queued with priority {priority}")
            
            # Return immediate acknowledgment
            return {
                'status': 'queued',
                'task_id': task_id,
                'priority': priority,
                'position_in_queue': self.task_queue.qsize(),
                'estimated_wait_time': self._estimate_wait_time()
            }
            
        except Exception as e:
            logger.error(f"Failed to queue task {task_id}: {e}")
            raise ProcessingError(f"Failed to queue task: {e}")
    
    def _calculate_priority(self, task_data: Dict[str, Any]) -> int:
        """Calculate task priority based on various factors."""
        base_priority = 0
        
        # Tier-based priority
        tier = task_data.get('tier', 'free')
        base_priority += self.priority_map.get(tier, 20)
        
        # Task type priority
        task_type = task_data.get('task_type', 'normal')
        type_priority = {
            'urgent': 50,
            'priority': 30,
            'normal': 10,
            'batch': 5
        }
        base_priority += type_priority.get(task_type, 10)
        
        # Customer priority (if specified)
        customer_priority = task_data.get('customer_priority', 0)
        base_priority += customer_priority
        
        # Age priority (older tasks get higher priority)
        created_at = task_data.get('created_at')
        if created_at:
            try:
                if isinstance(created_at, str):
                    from datetime import datetime
                    task_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    age_hours = (datetime.utcnow() - task_time).total_seconds() / 3600
                    base_priority += min(50, int(age_hours * 2))  # Max 50 bonus for age
            except:
                pass
        
        # SLA priority (tasks with tight deadlines)
        deadline = task_data.get('deadline')
        if deadline:
            try:
                if isinstance(deadline, str):
                    from datetime import datetime
                    deadline_time = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                    hours_until_deadline = (deadline_time - datetime.utcnow()).total_seconds() / 3600
                    if hours_until_deadline < 1:
                        base_priority += 100  # Critical
                    elif hours_until_deadline < 6:
                        base_priority += 60   # High
                    elif hours_until_deadline < 24:
                        base_priority += 30   # Medium
            except:
                pass
        
        # Video length priority (shorter videos get slightly higher priority)
        video_length = task_data.get('video_length', 0)
        if video_length > 0:
            # Shorter videos (< 5 min) get higher priority
            if video_length < 300:  # 5 minutes
                base_priority += 10
            elif video_length > 1800:  # 30 minutes
                base_priority -= 5
        
        return max(1, min(1000, base_priority))  # Clamp to 1-1000 range
    
    def _estimate_wait_time(self) -> float:
        """Estimate wait time in seconds."""
        queue_size = self.task_queue.qsize()
        active_workers = sum(1 for w in self.worker_pool if w.current_task)
        
        if active_workers == 0:
            return 0
        
        # Average processing time per worker
        avg_processing_time = 0
        for worker in self.worker_pool:
            if worker.stats['tasks_completed'] > 0:
                avg_processing_time += (
                    worker.stats['total_processing_time'] / 
                    worker.stats['tasks_completed']
                )
        
        if avg_processing_time == 0:
            avg_processing_time = 60  # Default 60 seconds
        
        # Estimated wait time
        estimated = (queue_size / active_workers) * avg_processing_time
        
        return max(0, estimated)
    
    def _process_queue(self):
        """Continuously process tasks from the priority queue."""
        logger.info("Priority queue processor started")
        
        while self.is_running:
            try:
                # Get next task from queue
                priority, task_wrapper = self.task_queue.get(timeout=1)
                task_id = task_wrapper['task_id']
                task_data = task_wrapper['task_data']
                queued_at = task_wrapper['queued_at']
                
                logger.info(f"Processing queued task {task_id} with priority {-priority}")
                
                # Find available worker
                worker = self._get_available_worker(task_data)
                
                if worker:
                    # Calculate wait time
                    wait_time = (datetime.utcnow() - queued_at).total_seconds()
                    
                    with self.lock:
                        self.queue_stats['tasks_processed'] += 1
                        self.queue_stats['average_wait_time'] = (
                            (self.queue_stats['average_wait_time'] * 
                             (self.queue_stats['tasks_processed'] - 1) + wait_time) /
                            self.queue_stats['tasks_processed']
                        )
                        self.queue_stats['max_wait_time'] = max(
                            self.queue_stats['max_wait_time'],
                            wait_time
                        )
                    
                    # Process with selected worker
                    try:
                        result = worker.process(task_data)
                        result['wait_time'] = wait_time
                        result['queued_at'] = queued_at.isoformat()
                        
                        # Send callback if specified
                        if task_wrapper.get('client_callback'):
                            self._send_callback(
                                task_wrapper['client_callback'],
                                result
                            )
                        
                        logger.info(f"Task {task_id} completed after {wait_time:.1f}s wait")
                        
                    except Exception as e:
                        logger.error(f"Worker failed to process task {task_id}: {e}")
                        
                        # Retry logic
                        retry_count = task_data.get('retry_count', 0)
                        if retry_count < 3:
                            task_data['retry_count'] = retry_count + 1
                            # Requeue with higher priority
                            task_data['priority_boost'] = 50 * (retry_count + 1)
                            self.process(task_data)
                            logger.info(f"Task {task_id} requeued for retry {retry_count + 1}")
                
                else:
                    logger.warning(f"No available worker for task {task_id}, re-queueing")
                    # Requeue with slightly higher priority
                    task_data['priority_boost'] = task_data.get('priority_boost', 0) + 10
                    self.process(task_data)
                    time.sleep(1)  # Prevent tight loop
                
                # Mark task as done
                self.task_queue.task_done()
                
            except Exception as e:
                # Timeout is expected when queue is empty
                if "empty" not in str(e).lower():
                    logger.error(f"Error in queue processor: {e}")
                time.sleep(0.1)
    
    def _get_available_worker(self, task_data: Dict[str, Any]) -> Optional[BaseWorker]:
        """Get an available worker that can process the task."""
        task_type = task_data.get('task_type', 'video_processing')
        
        for worker in self.worker_pool:
            # Check if worker is available and can process
            if (not worker.current_task and 
                hasattr(worker, 'can_process') and 
                worker.can_process(task_data)):
                return worker
        
        return None
    
    def _send_callback(self, callback_url: str, result: Dict[str, Any]):
        """Send callback to client."""
        try:
            import requests
            requests.post(
                callback_url,
                json=result,
                timeout=5
            )
            logger.debug(f"Callback sent to {callback_url}")
        except Exception as e:
            logger.warning(f"Failed to send callback to {callback_url}: {e}")
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed worker status."""
        base_status = super().get_status()
        
        # Collect sub-worker statuses
        sub_worker_statuses = []
        for worker in self.worker_pool:
            if hasattr(worker, 'get_detailed_status'):
                sub_worker_statuses.append(worker.get_detailed_status())
            else:
                sub_worker_statuses.append(worker.get_status())
        
        base_status.update({
            'queue_size': self.task_queue.qsize(),
            'queue_stats': self.queue_stats.copy(),
            'estimated_wait_time': self._estimate_wait_time(),
            'sub_workers': sub_worker_statuses,
            'priority_map': self.priority_map,
            'max_workers': self.max_workers,
            'active_workers': sum(1 for w in self.worker_pool if w.current_task),
            'worker_pool_health': self._check_worker_pool_health()
        })
        
        return base_status
    
    def _check_worker_pool_health(self) -> Dict[str, Any]:
        """Check health of worker pool."""
        healthy_workers = 0
        total_tasks = 0
        total_success = 0
        
        for worker in self.worker_pool:
            if worker.is_running:
                healthy_workers += 1
            
            total_tasks += (worker.stats['tasks_completed'] + 
                           worker.stats['tasks_failed'])
            total_success += worker.stats['tasks_completed']
        
        success_rate = (total_success / total_tasks * 100) if total_tasks > 0 else 0
        
        return {
            'healthy_workers': healthy_workers,
            'total_workers': len(self.worker_pool),
            'worker_health_percentage': (healthy_workers / len(self.worker_pool) * 100),
            'overall_success_rate': success_rate
        }
    
    def scale_workers(self, new_count: int):
        """Scale the worker pool up or down."""
        new_count = max(1, min(new_count, 10))  # Limit to 1-10 workers
        
        if new_count == len(self.worker_pool):
            return
        
        logger.info(f"Scaling worker pool from {len(self.worker_pool)} to {new_count}")
        
        with self.lock:
            if new_count > len(self.worker_pool):
                # Scale up
                for i in range(len(self.worker_pool), new_count):
                    worker_id = f"{self.worker_id}_sub_{i}"
                    worker_type = self.config.get('worker_type', 'video_worker')
                    
                    if worker_type == 'style_worker':
                        worker = StyleWorker(worker_id, self.config.get('worker_config', {}))
                    else:
                        worker = VideoWorker(worker_id, self.config.get('worker_config', {}))
                    
                    worker.start()
                    self.worker_pool.append(worker)
                    
                    logger.debug(f"Added worker {worker_id}")
            
            else:
                # Scale down
                workers_to_remove = self.worker_pool[new_count:]
                self.worker_pool = self.worker_pool[:new_count]
                
                for worker in workers_to_remove:
                    worker.stop()
                    logger.debug(f"Removed worker {worker.worker_id}")
            
            self.max_workers = new_count
    
    def stop(self):
        """Stop the priority worker and all sub-workers."""
        super().stop()
        
        # Stop all sub-workers
        for worker in self.worker_pool:
            worker.stop()
        
        # Clear queue
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except:
                pass
        
        logger.info(f"Priority Worker {self.worker_id} stopped")