"""
Processing status value object with state machine.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set, Optional
from datetime import datetime
from typing import ClassVar


class ProcessingState(str, Enum):
    """Processing states."""

    # Initial states
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    QUEUED = "queued"

    # Processing states
    ANALYZING = "analyzing"
    TRANSCRIBING = "transcribing"
    GENERATING_TITLE = "generating_title"
    GENERATING_THUMBNAILS = "generating_thumbnails"
    APPLYING_STYLES = "applying_styles"
    TRANSLATING = "translating"
    COMPRESSING = "compressing"
    UPLOADING_RESULTS = "uploading_results"

    # Final states
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    # Special states
    RETRYING = "retrying"
    PAUSED = "paused"


@dataclass(frozen=True)
class ProcessingStatus:
    """Processing status value object with state machine."""

    state: ProcessingState
    message: str = ""
    progress: float = 0.0  # 0.0 to 100.0
    timestamp: datetime = None
    metadata: Dict = None

    def __post_init__(self):
        """Initialize timestamp if not provided."""
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.utcnow())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # State transitions
    _VALID_TRANSITIONS: ClassVar[Dict[ProcessingState, Set[ProcessingState]]] = {
        ProcessingState.UPLOADED: {
            ProcessingState.VALIDATED,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
        },
        ProcessingState.VALIDATED: {
            ProcessingState.QUEUED,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
        },
        ProcessingState.QUEUED: {
            ProcessingState.ANALYZING,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.PAUSED,
        },
        ProcessingState.ANALYZING: {
            ProcessingState.TRANSCRIBING,
            ProcessingState.GENERATING_THUMBNAILS,
            ProcessingState.APPLYING_STYLES,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.TRANSCRIBING: {
            ProcessingState.GENERATING_TITLE,
            ProcessingState.TRANSLATING,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.GENERATING_TITLE: {
            ProcessingState.GENERATING_THUMBNAILS,
            ProcessingState.TRANSLATING,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.GENERATING_THUMBNAILS: {
            ProcessingState.APPLYING_STYLES,
            ProcessingState.TRANSLATING,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.APPLYING_STYLES: {
            ProcessingState.COMPRESSING,
            ProcessingState.TRANSLATING,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.TRANSLATING: {
            ProcessingState.COMPRESSING,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.COMPRESSING: {
            ProcessingState.UPLOADING_RESULTS,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.UPLOADING_RESULTS: {
            ProcessingState.COMPLETED,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
            ProcessingState.RETRYING,
        },
        ProcessingState.RETRYING: {
            ProcessingState.QUEUED,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
        },
        ProcessingState.PAUSED: {
            ProcessingState.QUEUED,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
        },
        ProcessingState.FAILED: {ProcessingState.RETRYING, ProcessingState.CANCELLED},
        ProcessingState.CANCELLED: set(),
        ProcessingState.COMPLETED: set(),
    }

    def can_transition_to(self, new_state: ProcessingState) -> bool:
        """Check if transition to new state is valid."""
        return new_state in self._VALID_TRANSITIONS.get(self.state, set())

    def transition_to(
        self,
        new_state: ProcessingState,
        message: str = "",
        progress: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> "ProcessingStatus":
        """Create a new status with transition to new state."""
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Cannot transition from {self.state} to {new_state}. "
                f"Valid transitions: {self._VALID_TRANSITIONS.get(self.state, set())}"
            )

        # Calculate progress if not provided
        if progress is None:
            progress = self._calculate_progress(new_state)

        # Merge metadata
        merged_metadata = self.metadata.copy()
        if metadata:
            merged_metadata.update(metadata)

        return ProcessingStatus(
            state=new_state,
            message=message,
            progress=progress,
            timestamp=datetime.utcnow(),
            metadata=merged_metadata,
        )

    def _calculate_progress(self, new_state: ProcessingState) -> float:
        """Calculate progress percentage for new state."""
        progress_map = {
            ProcessingState.UPLOADED: 5,
            ProcessingState.VALIDATED: 10,
            ProcessingState.QUEUED: 15,
            ProcessingState.ANALYZING: 20,
            ProcessingState.TRANSCRIBING: 30,
            ProcessingState.GENERATING_TITLE: 40,
            ProcessingState.GENERATING_THUMBNAILS: 50,
            ProcessingState.APPLYING_STYLES: 65,
            ProcessingState.TRANSLATING: 75,
            ProcessingState.COMPRESSING: 85,
            ProcessingState.UPLOADING_RESULTS: 95,
            ProcessingState.COMPLETED: 100,
            ProcessingState.FAILED: 0,
            ProcessingState.CANCELLED: 0,
            ProcessingState.RETRYING: self.progress,  # Keep same progress
            ProcessingState.PAUSED: self.progress,  # Keep same progress
        }

        return progress_map.get(new_state, self.progress)

    def is_final_state(self) -> bool:
        """Check if status is in a final state."""
        final_states = {
            ProcessingState.COMPLETED,
            ProcessingState.FAILED,
            ProcessingState.CANCELLED,
        }
        return self.state in final_states

    def is_processing(self) -> bool:
        """Check if status indicates processing is active."""
        processing_states = {
            ProcessingState.ANALYZING,
            ProcessingState.TRANSCRIBING,
            ProcessingState.GENERATING_TITLE,
            ProcessingState.GENERATING_THUMBNAILS,
            ProcessingState.APPLYING_STYLES,
            ProcessingState.TRANSLATING,
            ProcessingState.COMPRESSING,
            ProcessingState.UPLOADING_RESULTS,
        }
        return self.state in processing_states

    def is_error_state(self) -> bool:
        """Check if status indicates an error."""
        return self.state in {ProcessingState.FAILED, ProcessingState.RETRYING}

    def get_estimated_time_remaining(self) -> Optional[float]:
        """Get estimated time remaining in seconds."""
        if self.is_final_state() or self.progress == 0:
            return None

        # Simple linear estimation
        if self.timestamp and self.progress > 0:
            time_elapsed = (datetime.utcnow() - self.timestamp).total_seconds()
            if time_elapsed > 0:
                total_estimated = (time_elapsed / self.progress) * 100
                return max(0, total_estimated - time_elapsed)

        return None

    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "state": self.state.value,
            "message": self.message,
            "progress": self.progress,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "estimated_time_remaining": self.get_estimated_time_remaining(),
            "is_final": self.is_final_state(),
            "is_processing": self.is_processing(),
            "is_error": self.is_error_state(),
            "metadata": self.metadata,
        }
