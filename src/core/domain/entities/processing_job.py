"""
Processing job entity for background processing.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

class JobStatus(str, Enum):
    """Processing job status."""
    PENDING = "pending"
    STARTED = "started"
    RETRY = "retry"
    FAILURE = "failure"
    SUCCESS = "success"
    REVOKED = "revoked"

class JobType(str, Enum):
    """Type of processing job."""
    VIDEO_PROCESSING = "video_processing"
    TRANSCRIPTION = "transcription"
    TITLE_GENERATION = "title_generation"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    STYLE_APPLICATION = "style_application"
    TRANSLATION = "translation"
    CLEANUP = "cleanup"
    NOTIFICATION = "notification"

@dataclass
class ProcessingJob:
    """Processing job entity."""
    
    id: str
    video_id: str
    user_id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    
    # Task information
    task_id: Optional[str] = None  # Celery task ID
    worker: Optional[str] = None  # Worker that processed the job
    queue: str = "default"
    
    # Progress tracking
    current_step: Optional[str] = None
    progress: float = 0.0  # 0 to 100
    total_steps: int = 1
    
    # Error handling
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # Timing
    eta: Optional[datetime] = None
    expires: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None  # in seconds
    
    # Result
    result: Optional[Dict[str, Any]] = None
    result_url: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher number = higher priority
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def start(self, task_id: str, worker: str):
        """Start the job."""
        self.task_id = task_id
        self.worker = worker
        self.status = JobStatus.STARTED
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def update_progress(self, step: str, progress: float):
        """Update job progress."""
        self.current_step = step
        self.progress = progress
        self.updated_at = datetime.utcnow()
    
    def complete(self, result: Optional[Dict[str, Any]] = None, result_url: Optional[str] = None):
        """Complete the job successfully."""
        self.status = JobStatus.SUCCESS
        self.completed_at = datetime.utcnow()
        self.result = result
        self.result_url = result_url
        
        if self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        
        self.updated_at = datetime.utcnow()
    
    def fail(self, error_message: str, error_traceback: Optional[str] = None):
        """Mark job as failed."""
        self.status = JobStatus.FAILURE
        self.error_message = error_message
        self.error_traceback = error_traceback
        self.completed_at = datetime.utcnow()
        
        if self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        
        self.updated_at = datetime.utcnow()
    
    def retry(self, error_message: Optional[str] = None):
        """Mark job for retry."""
        self.status = JobStatus.RETRY
        self.retry_count += 1
        
        if error_message:
            self.error_message = error_message
        
        self.updated_at = datetime.utcnow()
    
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.retry_count < self.max_retries
    
    def is_completed(self) -> bool:
        """Check if job is completed."""
        return self.status in [JobStatus.SUCCESS, JobStatus.FAILURE, JobStatus.REVOKED]
    
    def is_successful(self) -> bool:
        """Check if job completed successfully."""
        return self.status == JobStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "user_id": self.user_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "task_id": self.task_id,
            "worker": self.worker,
            "queue": self.queue,
            "current_step": self.current_step,
            "progress": self.progress,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "result_url": self.result_url,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_time": self.execution_time
        }