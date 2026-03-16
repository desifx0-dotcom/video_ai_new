"""
Unit tests for Video model.
"""
import pytest
from datetime import datetime, timedelta

from src.core.domain.entities.video import Video, VideoStatus, VideoType

class TestVideoModel:
    """Test Video model."""
    
    def test_video_creation(self):
        """Test video creation with default values."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,  # 1MB
            duration=60.0,
            mime_type="video/mp4"
        )
        
        assert video.id == "test-video-123"
        assert video.user_id == "user-123"
        assert video.original_filename == "test.mp4"
        assert video.file_size == 1024 * 1024
        assert video.duration == 60.0
        assert video.mime_type == "video/mp4"
        assert video.status == VideoStatus.UPLOADED
        assert video.video_type == VideoType.UNKNOWN
        assert video.output_quality == "720p"
        assert video.output_format == "mp4"
        assert video.priority == 0
        assert video.retry_count == 0
        assert video.max_retries == 3
        assert video.is_deleted is False
        assert isinstance(video.created_at, datetime)
        assert isinstance(video.updated_at, datetime)
    
    def test_update_status(self):
        """Test updating video status."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4"
        )
        
        initial_updated_at = video.updated_at
        
        # Update to PROCESSING
        video.update_status(VideoStatus.PROCESSING, "Starting processing")
        
        assert video.status == VideoStatus.PROCESSING
        assert video.processing_started is not None
        assert video.error_message == "Starting processing"
        assert video.updated_at > initial_updated_at
        
        # Update to COMPLETED
        video.update_status(VideoStatus.COMPLETED, "Processing complete")
        
        assert video.status == VideoStatus.COMPLETED
        assert video.processing_completed is not None
        assert video.processing_time is not None
        assert video.error_message == "Processing complete"
    
    def test_add_ai_cost(self):
        """Test adding AI processing cost."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4"
        )
        
        initial_updated_at = video.updated_at
        
        # Add transcription cost
        video.add_ai_cost("transcription", 0.01)
        
        assert video.ai_costs["transcription"] == 0.01
        assert video.total_cost == 0.01
        assert video.updated_at > initial_updated_at
        
        # Add thumbnail cost
        video.add_ai_cost("thumbnail_generation", 0.02)
        
        assert video.ai_costs["thumbnail_generation"] == 0.02
        assert video.total_cost == 0.03  # 0.01 + 0.02
        
        # Add to existing cost
        video.add_ai_cost("transcription", 0.005)
        
        assert video.ai_costs["transcription"] == 0.015
        assert video.total_cost == 0.035
    
    def test_can_retry(self):
        """Test checking if video can be retried."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4",
            retry_count=0
        )
        
        # Not completed, within retry limit
        assert video.can_retry() is True
        
        # At retry limit
        video.retry_count = 3
        assert video.can_retry() is False
        
        # Completed video shouldn't retry
        video.status = VideoStatus.COMPLETED
        video.retry_count = 0
        assert video.can_retry() is False
    
    def test_schedule_deletion(self):
        """Test scheduling video for deletion."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4"
        )
        
        initial_updated_at = video.updated_at
        
        # Schedule for deletion in 7 days
        video.schedule_deletion(7)
        
        assert video.scheduled_for_deletion is not None
        assert video.scheduled_for_deletion > datetime.utcnow()
        assert video.scheduled_for_deletion <= datetime.utcnow() + timedelta(days=7)
        assert video.updated_at > initial_updated_at
    
    def test_should_be_deleted(self):
        """Test checking if video should be deleted."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4"
        )
        
        # Not scheduled for deletion
        assert video.should_be_deleted() is False
        
        # Scheduled for future deletion
        video.scheduled_for_deletion = datetime.utcnow() + timedelta(days=1)
        assert video.should_be_deleted() is False
        
        # Scheduled for past deletion
        video.scheduled_for_deletion = datetime.utcnow() - timedelta(days=1)
        assert video.should_be_deleted() is True
    
    def test_get_progress(self):
        """Test getting processing progress percentage."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4"
        )
        
        # UPLOADED: 5%
        video.status = VideoStatus.UPLOADED
        assert video.get_progress() == 5
        
        # QUEUED: 10%
        video.status = VideoStatus.QUEUED
        assert video.get_progress() == 10
        
        # PROCESSING: 15%
        video.status = VideoStatus.PROCESSING
        assert video.get_progress() == 15
        
        # TRANSCRIBING: 40%
        video.status = VideoStatus.TRANSCRIBING
        assert video.get_progress() == 40
        
        # COMPLETED: 100%
        video.status = VideoStatus.COMPLETED
        assert video.get_progress() == 100
        
        # FAILED: 0%
        video.status = VideoStatus.FAILED
        assert video.get_progress() == 0
        
        # CANCELLED: 0%
        video.status = VideoStatus.CANCELLED
        assert video.get_progress() == 0
        
        # Unknown status: 0%
        video.status = "UNKNOWN_STATUS"
        assert video.get_progress() == 0
    
    def test_to_dict(self):
        """Test converting video to dictionary."""
        video = Video(
            id="test-video-123",
            user_id="user-123",
            original_filename="test.mp4",
            file_size=1024 * 1024,
            duration=60.0,
            mime_type="video/mp4",
            status=VideoStatus.COMPLETED,
            video_type=VideoType.SPEECH,
            title="Test Video",
            description="Test description",
            transcription="Test transcription",
            transcription_language="en",
            tags=["test", "video"],
            ai_thumbnails=["thumb1.jpg"],
            extracted_thumbnails=["thumb2.jpg"],
            selected_thumbnail="thumb1.jpg",
            output_quality="720p",
            applied_styles=["cinematic"],
            output_video_url="https://storage.com/video.mp4",
            output_video_size=512 * 1024,
            translated_transcription="Test translation",
            translation_language="es",
            processed_tier="free",
            processing_time=30.0,
            total_cost=0.05,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            processing_started=datetime(2024, 1, 1, 12, 1, 0),
            processing_completed=datetime(2024, 1, 1, 12, 1, 30),
            error_message=None,
            retry_count=0
        )
        
        video_dict = video.to_dict()
        
        assert video_dict["id"] == "test-video-123"
        assert video_dict["user_id"] == "user-123"
        assert video_dict["original_filename"] == "test.mp4"
        assert video_dict["duration"] == 60.0
        assert video_dict["status"] == "completed"
        assert video_dict["video_type"] == "speech"
        assert video_dict["progress"] == 100
        assert video_dict["title"] == "Test Video"
        assert video_dict["description"] == "Test description"
        assert video_dict["transcription"] == "Test transcription"
        assert video_dict["transcription_language"] == "en"
        assert video_dict["tags"] == ["test", "video"]
        assert video_dict["ai_thumbnails"] == ["thumb1.jpg"]
        assert video_dict["selected_thumbnail"] == "thumb1.jpg"
        assert video_dict["output_video_url"] == "https://storage.com/video.mp4"
        assert video_dict["output_quality"] == "720p"
        assert video_dict["applied_styles"] == ["cinematic"]
        assert video_dict["translated_transcription"] == "Test translation"
        assert video_dict["translation_language"] == "es"
        assert video_dict["processed_tier"] == "free"
        assert video_dict["processing_time"] == 30.0
        assert video_dict["total_cost"] == 0.05
        assert video_dict["created_at"] == "2024-01-01T12:00:00"
        assert video_dict["processing_started"] == "2024-01-01T12:01:00"
        assert video_dict["processing_completed"] == "2024-01-01T12:01:30"
        assert video_dict["error_message"] is None
        assert video_dict["retry_count"] == 0