"""
Queue abstraction layer.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Callable
import json
import pickle
import time
import threading
from datetime import datetime
from enum import Enum

class QueuePriority(Enum):
    """Queue priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

class QueueMessage:
    """Message container for queue operations."""
    
    def __init__(self, 
                 data: Any,
                 message_id: Optional[str] = None,
                 priority: QueuePriority = QueuePriority.NORMAL,
                 delay: int = 0,
                 ttl: Optional[int] = None):
        self.id = message_id or self._generate_id()
        self.data = data
        self.priority = priority
        self.delay = delay
        self.ttl = ttl
        self.created_at = datetime.utcnow()
        self.visible_after = self.created_at.timestamp() + delay
        self.expires_at = None
        if ttl:
            self.expires_at = self.created_at.timestamp() + ttl
    
    @staticmethod
    def _generate_id() -> str:
        """Generate unique message ID."""
        import uuid
        return str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            'id': self.id,
            'data': self.data,
            'priority': self.priority.value,
            'delay': self.delay,
            'ttl': self.ttl,
            'created_at': self.created_at.isoformat(),
            'visible_after': self.visible_after,
            'expires_at': self.expires_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueMessage':
        """Create message from dictionary."""
        message = cls(
            data=data['data'],
            message_id=data['id'],
            priority=QueuePriority(data['priority']),
            delay=data.get('delay', 0),
            ttl=data.get('ttl')
        )
        message.created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        message.visible_after = data['visible_after']
        message.expires_at = data.get('expires_at')
        return message
    
    def is_visible(self) -> bool:
        """Check if message is visible (delay has passed)."""
        return time.time() >= self.visible_after
    
    def is_expired(self) -> bool:
        """Check if message is expired."""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

class Queue(ABC):
    """Abstract queue interface."""
    
    @abstractmethod
    def enqueue(self, 
                data: Any,
                queue_name: str = "default",
                priority: QueuePriority = QueuePriority.NORMAL,
                delay: int = 0,
                ttl: Optional[int] = None) -> str:
        """Enqueue a message."""
        pass
    
    @abstractmethod
    def dequeue(self, 
                queue_name: str = "default",
                timeout: int = 0) -> Optional[QueueMessage]:
        """Dequeue a message."""
        pass
    
    @abstractmethod
    def ack(self, 
            message_id: str, 
            queue_name: str = "default") -> bool:
        """Acknowledge message processing."""
        pass
    
    @abstractmethod
    def nack(self, 
             message_id: str,
             queue_name: str = "default",
             delay: int = 0) -> bool:
        """Negative acknowledgement with optional delay."""
        pass
    
    @abstractmethod
    def size(self, queue_name: str = "default") -> int:
        """Get queue size."""
        pass
    
    @abstractmethod
    def purge(self, queue_name: str = "default") -> bool:
        """Purge all messages from queue."""
        pass
    
    @abstractmethod
    def get_stats(self, queue_name: str = "default") -> Dict[str, Any]:
        """Get queue statistics."""
        pass
    
    def enqueue_json(self, 
                    data: Any,
                    queue_name: str = "default",
                    priority: QueuePriority = QueuePriority.NORMAL,
                    delay: int = 0,
                    ttl: Optional[int] = None) -> str:
        """Enqueue JSON-serializable data."""
        try:
            json_data = json.dumps(data)
            return self.enqueue(json_data, queue_name, priority, delay, ttl)
        except (TypeError, ValueError):
            raise ValueError("Data must be JSON serializable")
    
    def enqueue_pickle(self, 
                      data: Any,
                      queue_name: str = "default",
                      priority: QueuePriority = QueuePriority.NORMAL,
                      delay: int = 0,
                      ttl: Optional[int] = None) -> str:
        """Enqueue pickled data."""
        try:
            pickle_data = pickle.dumps(data)
            return self.enqueue(pickle_data, queue_name, priority, delay, ttl)
        except (pickle.PickleError, TypeError):
            raise ValueError("Data must be pickleable")
    
    def dequeue_json(self, 
                    queue_name: str = "default",
                    timeout: int = 0) -> Optional[Any]:
        """Dequeue and parse JSON message."""
        message = self.dequeue(queue_name, timeout)
        if message is None:
            return None
        
        try:
            return json.loads(message.data)
        except (json.JSONDecodeError, TypeError):
            return message.data
    
    def dequeue_pickle(self, 
                      queue_name: str = "default",
                      timeout: int = 0) -> Optional[Any]:
        """Dequeue and parse pickled message."""
        message = self.dequeue(queue_name, timeout)
        if message is None:
            return None
        
        try:
            return pickle.loads(message.data)
        except (pickle.PickleError, TypeError):
            return message.data

class RedisQueue(Queue):
    """Redis-based queue implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        import redis
        
        config = config or {}
        self.client = redis.Redis(
            host=config.get('host', 'localhost'),
            port=config.get('port', 6379),
            db=config.get('db', 0),
            password=config.get('password'),
            decode_responses=False,  # Keep bytes for pickle support
            socket_timeout=config.get('socket_timeout', 5),
            socket_connect_timeout=config.get('socket_connect_timeout', 5),
            retry_on_timeout=config.get('retry_on_timeout', True)
        )
        
        # Queue configuration
        self.max_retries = config.get('max_retries', 3)
        self.visibility_timeout = config.get('visibility_timeout', 300)  # 5 minutes
        
        # Test connection
        try:
            self.client.ping()
        except redis.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")
    
    def enqueue(self, 
                data: Any,
                queue_name: str = "default",
                priority: QueuePriority = QueuePriority.NORMAL,
                delay: int = 0,
                ttl: Optional[int] = None) -> str:
        """Enqueue a message to Redis."""
        import pickle
        
        try:
            # Create message
            message = QueueMessage(data, priority=priority, delay=delay, ttl=ttl)
            
            # Serialize message
            message_data = pickle.dumps(message.to_dict())
            
            # Determine queue based on priority
            priority_queue = self._get_priority_queue(queue_name, priority)
            
            if delay > 0:
                # Use sorted set for delayed messages
                score = time.time() + delay
                self.client.zadd(f"{queue_name}:delayed", {message.id: score})
                # Store message data
                self.client.setex(f"{queue_name}:message:{message.id}", 
                                 ttl or 86400,  # Default 24 hours
                                 message_data)
            else:
                # Add to priority queue
                self.client.lpush(priority_queue, message_data)
                
                # Set TTL if specified
                if ttl:
                    self.client.expire(priority_queue, ttl)
            
            # Move delayed messages to queue if ready
            self._process_delayed_messages(queue_name)
            
            return message.id
            
        except Exception as e:
            import logging
            logging.error(f"Redis enqueue error: {e}")
            raise
    
    def dequeue(self, 
                queue_name: str = "default",
                timeout: int = 0) -> Optional[QueueMessage]:
        """Dequeue a message from Redis."""
        import pickle
        
        try:
            # Process delayed messages first
            self._process_delayed_messages(queue_name)
            
            # Try each priority queue from highest to lowest
            for priority in reversed(list(QueuePriority)):
                priority_queue = self._get_priority_queue(queue_name, priority)
                
                # Try to get message (non-blocking)
                message_data = self.client.rpop(priority_queue)
                
                if message_data:
                    try:
                        message_dict = pickle.loads(message_data)
                        message = QueueMessage.from_dict(message_dict)
                        
                        # Add to processing set with visibility timeout
                        processing_key = f"{queue_name}:processing:{message.id}"
                        self.client.setex(processing_key, 
                                         self.visibility_timeout,
                                         message_data)
                        
                        return message
                    except (pickle.PickleError, KeyError) as e:
                        import logging
                        logging.error(f"Failed to parse message: {e}")
                        continue
            
            # If no messages and timeout > 0, block and wait
            if timeout > 0:
                # Use BRPOP for blocking pop (Redis only supports one queue at a time)
                # For simplicity, we'll poll
                start_time = time.time()
                while time.time() - start_time < timeout:
                    message = self.dequeue(queue_name, timeout=0)
                    if message:
                        return message
                    time.sleep(0.1)
            
            return None
            
        except Exception as e:
            import logging
            logging.error(f"Redis dequeue error: {e}")
            return None
    
    def ack(self, 
            message_id: str, 
            queue_name: str = "default") -> bool:
        """Acknowledge message processing."""
        try:
            # Remove from processing set
            processing_key = f"{queue_name}:processing:{message_id}"
            self.client.delete(processing_key)
            
            # Remove message data
            message_key = f"{queue_name}:message:{message_id}"
            self.client.delete(message_key)
            
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Redis ack error: {e}")
            return False
    
    def nack(self, 
             message_id: str,
             queue_name: str = "default",
             delay: int = 0) -> bool:
        """Negative acknowledgement with optional delay."""
        try:
            processing_key = f"{queue_name}:processing:{message_id}"
            message_data = self.client.get(processing_key)
            
            if not message_data:
                return False
            
            # Parse message
            import pickle
            message_dict = pickle.loads(message_data)
            message = QueueMessage.from_dict(message_dict)
            
            # Increment retry count
            retry_count = message_dict.get('retry_count', 0) + 1
            message_dict['retry_count'] = retry_count
            
            if retry_count > self.max_retries:
                # Move to dead letter queue
                dead_queue = f"{queue_name}:dead"
                self.client.lpush(dead_queue, pickle.dumps(message_dict))
                self.client.delete(processing_key)
                return True
            
            # Requeue with delay
            if delay > 0:
                # Add to delayed queue
                score = time.time() + delay
                self.client.zadd(f"{queue_name}:delayed", {message_id: score})
                self.client.setex(f"{queue_name}:message:{message_id}",
                                 86400,  # 24 hours
                                 pickle.dumps(message_dict))
            else:
                # Requeue based on priority
                priority_queue = self._get_priority_queue(queue_name, message.priority)
                self.client.lpush(priority_queue, pickle.dumps(message_dict))
            
            # Remove from processing
            self.client.delete(processing_key)
            
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Redis nack error: {e}")
            return False
    
    def size(self, queue_name: str = "default") -> int:
        """Get total queue size."""
        try:
            total = 0
            
            # Count messages in priority queues
            for priority in QueuePriority:
                priority_queue = self._get_priority_queue(queue_name, priority)
                total += self.client.llen(priority_queue)
            
            # Count delayed messages
            delayed_key = f"{queue_name}:delayed"
            total += self.client.zcard(delayed_key)
            
            return total
            
        except Exception as e:
            import logging
            logging.error(f"Redis size error: {e}")
            return 0
    
    def purge(self, queue_name: str = "default") -> bool:
        """Purge all messages from queue."""
        try:
            # Delete all queue-related keys
            pattern = f"{queue_name}:*"
            keys = self.client.keys(pattern)
            
            if keys:
                self.client.delete(*keys)
            
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Redis purge error: {e}")
            return False
    
    def get_stats(self, queue_name: str = "default") -> Dict[str, Any]:
        """Get queue statistics."""
        try:
            stats = {
                'total_messages': 0,
                'by_priority': {},
                'delayed_messages': 0,
                'processing_messages': 0,
                'dead_messages': 0
            }
            
            # Count by priority
            for priority in QueuePriority:
                queue_name_full = self._get_priority_queue(queue_name, priority)
                count = self.client.llen(queue_name_full)
                stats['by_priority'][priority.name] = count
                stats['total_messages'] += count
            
            # Delayed messages
            delayed_key = f"{queue_name}:delayed"
            stats['delayed_messages'] = self.client.zcard(delayed_key)
            stats['total_messages'] += stats['delayed_messages']
            
            # Processing messages
            pattern = f"{queue_name}:processing:*"
            processing_keys = self.client.keys(pattern)
            stats['processing_messages'] = len(processing_keys)
            
            # Dead messages
            dead_key = f"{queue_name}:dead"
            stats['dead_messages'] = self.client.llen(dead_key)
            
            return stats
            
        except Exception as e:
            import logging
            logging.error(f"Redis stats error: {e}")
            return {}
    
    def _get_priority_queue(self, 
                           queue_name: str, 
                           priority: QueuePriority) -> str:
        """Get queue name for specific priority."""
        return f"{queue_name}:{priority.name.lower()}"
    
    def _process_delayed_messages(self, queue_name: str):
        """Move delayed messages to appropriate queues when ready."""
        import pickle
        
        try:
            delayed_key = f"{queue_name}:delayed"
            current_time = time.time()
            
            # Get ready messages
            ready_messages = self.client.zrangebyscore(
                delayed_key, 0, current_time
            )
            
            if not ready_messages:
                return
            
            for message_id_bytes in ready_messages:
                message_id = message_id_bytes.decode('utf-8')
                
                # Get message data
                message_key = f"{queue_name}:message:{message_id}"
                message_data = self.client.get(message_key)
                
                if not message_data:
                    # Clean up orphaned delayed entry
                    self.client.zrem(delayed_key, message_id_bytes)
                    continue
                
                try:
                    message_dict = pickle.loads(message_data)
                    message = QueueMessage.from_dict(message_dict)
                    
                    # Add to appropriate priority queue
                    priority_queue = self._get_priority_queue(queue_name, message.priority)
                    self.client.lpush(priority_queue, message_data)
                    
                    # Clean up
                    self.client.zrem(delayed_key, message_id_bytes)
                    self.client.delete(message_key)
                    
                except (pickle.PickleError, KeyError) as e:
                    import logging
                    logging.error(f"Failed to process delayed message {message_id}: {e}")
                    # Clean up corrupted message
                    self.client.zrem(delayed_key, message_id_bytes)
                    self.client.delete(message_key)
            
        except Exception as e:
            import logging
            logging.error(f"Error processing delayed messages: {e}")

class MemoryQueue(Queue):
    """In-memory queue implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        self._queues = {}
        self._delayed_messages = {}
        self._processing_messages = {}
        self._dead_messages = {}
        self.max_retries = config.get('max_retries', 3)
        self.visibility_timeout = config.get('visibility_timeout', 300)
        
        import threading
        self._lock = threading.RLock()
        
        # Start delayed message processor
        self._processor_thread = threading.Thread(
            target=self._process_delayed_messages_loop,
            daemon=True
        )
        self._processor_thread.start()
    
    def enqueue(self, 
                data: Any,
                queue_name: str = "default",
                priority: QueuePriority = QueuePriority.NORMAL,
                delay: int = 0,
                ttl: Optional[int] = None) -> str:
        """Enqueue a message to memory queue."""
        with self._lock:
            # Create message
            message = QueueMessage(data, priority=priority, delay=delay, ttl=ttl)
            
            if queue_name not in self._queues:
                self._queues[queue_name] = {p: [] for p in QueuePriority}
            
            if delay > 0:
                # Add to delayed messages
                if queue_name not in self._delayed_messages:
                    self._delayed_messages[queue_name] = []
                self._delayed_messages[queue_name].append(message)
            else:
                # Add to priority queue
                self._queues[queue_name][priority].append(message)
            
            return message.id
    
    def dequeue(self, 
                queue_name: str = "default",
                timeout: int = 0) -> Optional[QueueMessage]:
        """Dequeue a message from memory queue."""
        start_time = time.time()
        
        while True:
            with self._lock:
                # Check if queue exists
                if queue_name not in self._queues:
                    if timeout == 0:
                        return None
                    continue
                
                # Try each priority queue from highest to lowest
                for priority in reversed(list(QueuePriority)):
                    queue = self._queues[queue_name][priority]
                    
                    if queue:
                        # Get next message
                        message = queue.pop(0)
                        
                        # Add to processing with timeout
                        processing_key = f"{queue_name}:{message.id}"
                        self._processing_messages[processing_key] = {
                            'message': message,
                            'expires_at': time.time() + self.visibility_timeout
                        }
                        
                        return message
                
                # Check timeout
                if timeout == 0:
                    return None
                
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return None
            
            # Wait before retrying
            time.sleep(0.1)
    
    def ack(self, 
            message_id: str, 
            queue_name: str = "default") -> bool:
        """Acknowledge message processing."""
        with self._lock:
            processing_key = f"{queue_name}:{message_id}"
            if processing_key in self._processing_messages:
                del self._processing_messages[processing_key]
                return True
            return False
    
    def nack(self, 
             message_id: str,
             queue_name: str = "default",
             delay: int = 0) -> bool:
        """Negative acknowledgement with optional delay."""
        with self._lock:
            processing_key = f"{queue_name}:{message_id}"
            
            if processing_key not in self._processing_messages:
                return False
            
            message_data = self._processing_messages[processing_key]
            message = message_data['message']
            
            # Get retry count from message data
            if not hasattr(message, 'retry_count'):
                message.retry_count = 0
            
            message.retry_count += 1
            
            if message.retry_count > self.max_retries:
                # Move to dead messages
                if queue_name not in self._dead_messages:
                    self._dead_messages[queue_name] = []
                self._dead_messages[queue_name].append(message)
                del self._processing_messages[processing_key]
                return True
            
            # Requeue with delay
            if delay > 0:
                # Add back to delayed
                if queue_name not in self._delayed_messages:
                    self._delayed_messages[queue_name] = []
                message.delay = delay
                message.visible_after = time.time() + delay
                self._delayed_messages[queue_name].append(message)
            else:
                # Requeue based on priority
                if queue_name not in self._queues:
                    self._queues[queue_name] = {p: [] for p in QueuePriority}
                self._queues[queue_name][message.priority].append(message)
            
            # Remove from processing
            del self._processing_messages[processing_key]
            
            return True
    
    def size(self, queue_name: str = "default") -> int:
        """Get total queue size."""
        with self._lock:
            total = 0
            
            if queue_name in self._queues:
                for priority in QueuePriority:
                    total += len(self._queues[queue_name][priority])
            
            if queue_name in self._delayed_messages:
                total += len(self._delayed_messages[queue_name])
            
            return total
    
    def purge(self, queue_name: str = "default") -> bool:
        """Purge all messages from queue."""
        with self._lock:
            if queue_name in self._queues:
                del self._queues[queue_name]
            
            if queue_name in self._delayed_messages:
                del self._delayed_messages[queue_name]
            
            # Also clean up processing messages for this queue
            to_delete = []
            for key in self._processing_messages.keys():
                if key.startswith(f"{queue_name}:"):
                    to_delete.append(key)
            
            for key in to_delete:
                del self._processing_messages[key]
            
            return True
    
    def get_stats(self, queue_name: str = "default") -> Dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            stats = {
                'total_messages': 0,
                'by_priority': {},
                'delayed_messages': 0,
                'processing_messages': 0,
                'dead_messages': 0
            }
            
            # Count by priority
            if queue_name in self._queues:
                for priority in QueuePriority:
                    count = len(self._queues[queue_name][priority])
                    stats['by_priority'][priority.name] = count
                    stats['total_messages'] += count
            
            # Delayed messages
            if queue_name in self._delayed_messages:
                stats['delayed_messages'] = len(self._delayed_messages[queue_name])
                stats['total_messages'] += stats['delayed_messages']
            
            # Processing messages
            processing_count = 0
            for key in self._processing_messages.keys():
                if key.startswith(f"{queue_name}:"):
                    processing_count += 1
            stats['processing_messages'] = processing_count
            
            # Dead messages
            if queue_name in self._dead_messages:
                stats['dead_messages'] = len(self._dead_messages[queue_name])
            
            return stats
    
    def _process_delayed_messages_loop(self):
        """Continuously process delayed messages."""
        while True:
            try:
                self._process_delayed_messages()
            except Exception as e:
                import logging
                logging.error(f"Error in delayed message processor: {e}")
            
            time.sleep(1)  # Check every second
    
    def _process_delayed_messages(self):
        """Move delayed messages to appropriate queues when ready."""
        with self._lock:
            current_time = time.time()
            
            for queue_name, messages in list(self._delayed_messages.items()):
                ready_messages = []
                remaining_messages = []
                
                for message in messages:
                    if message.is_visible():
                        ready_messages.append(message)
                    else:
                        remaining_messages.append(message)
                
                if ready_messages:
                    # Initialize queue if needed
                    if queue_name not in self._queues:
                        self._queues[queue_name] = {p: [] for p in QueuePriority}
                    
                    # Add ready messages to appropriate queues
                    for message in ready_messages:
                        self._queues[queue_name][message.priority].append(message)
                    
                    # Update delayed messages
                    self._delayed_messages[queue_name] = remaining_messages
                
                # Remove empty delayed queues
                if not remaining_messages:
                    del self._delayed_messages[queue_name]