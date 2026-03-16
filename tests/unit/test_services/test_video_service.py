"""
Unit tests for VideoService.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.core.domain.entities.user import User, Tier
from src.core.domain.entities.video import Video, VideoStatus, VideoType
from src.services.video_service import VideoService
from src.core.exceptions import (
    ValidationError, TierLimitExceeded, InsufficientCreditsError,
    ProcessingError, VideoTooLargeError, InvalidVideoFormatError
)

class TestVideoService:
    """Test VideoService class."""
    
    @pytest.fixture
    def video_service(self, mock_firebase, mock_ffmpeg):
        """Create VideoService instance."""
        return VideoService()
    
    @pytest.fixture
    def mock_file(self):
        """Create a mock file object."""
        file_obj = Mock()
        file_obj.save = Mock()
        return file_obj
    
    def test_validate_upload_success(self, video_service, test_user):
        """Test successful upload validation."""
        # Should not raise any exceptions
        video_service._validate_upload(
            user=test_user,
            filename="test.mp4",
            file_size=50 * 1024 * 1024,  # 50MB
            content_type="video/mp4"
        )
    
    def test_validate_upload_too_large(self, video_service, test_user):
        """Test upload validation with file too large."""
        with pytest.raises(VideoTooLargeError):
            video_service._validate_upload(
                user=test_user,
                filename="test.mp4",
                file_size=3 * 1024 * 1024 * 1024,  # 3GB
                content_type="video/mp4"
            )
    
    def test_validate_upload_invalid_extension(self, video_service, test_user):
        """Test upload validation with invalid extension."""
        with pytest.raises(InvalidVideoFormatError):
            video_service._validate_upload(
                user=test_user,
                filename="test.txt",
                file_size=1024,
                content_type="text/plain"
            )
    
    def test_validate_upload_invalid_mime_type(self, video_service, test_user):
        """Test upload validation with invalid MIME type."""
        with pytest.raises(InvalidVideoFormatError):
            video_service._validate_upload(
                user=test_user,
                filename="test.mp4",
                file_size=1024,
                content_type="application/json"
            )
    
    def test_upload_video_success(self, video_service, test_user, mock_file, mock_ffmpeg):
        """Test successful video upload."""
        with patch.object(video_service.user_service, 'get_user', return_value=test_user):
            with patch.object(video_service.silent_video_service, 'is_silent_video', return_value=False):
                with patch('src.services.video_service.uuid.uuid4', return_value='test-video-id'):
                    with patch.object(video_service.db, 'save'):
                        with patch.object(video_service.db, 'query', return_value=[]):
                            video, upload_path = video_service.upload_video(
                                user_id=test_user.id,
                                file_obj=mock_file,
                                filename="test.mp4",
                                file_size=50 * 1024 * 1024,
                                content_type="video/mp4",
                                options={"quality": "720p"}
                            )
        
        assert video.id == "test-video-id"
        assert video.user_id == test_user.id
        assert video.original_filename == "test.mp4"
        assert video.output_quality == "720p"
        assert video.video_type == VideoType.SPEECH
    
    def test_upload_video_silent_detected(self, video_service, test_user, mock_file, mock_ffmpeg):
        """Test video upload with silent video detection."""
        with patch.object(video_service.user_service, 'get_user', return_value=test_user):
            with patch.object(video_service.silent_video_service, 'is_silent_video', return_value=True):
                with patch('src.services.video_service.uuid.uuid4', return_value='test-video-id'):
                    with patch.object(video_service.db, 'save'):
                        with patch.object(video_service.db, 'query', return_value=[]):
                            video, upload_path = video_service.upload_video(
                                user_id=test_user.id,
                                file_obj=mock_file,
                                filename="test.mp4",
                                file_size=50 * 1024 * 1024,
                                content_type="video/mp4"
                            )
        
        assert video.video_type == VideoType.SILENT
    
    def test_upload_video_tier_limit_exceeded(self, video_service, test_user, mock_file):
        """Test video upload when tier limit is exceeded."""
        test_user.videos_processed_this_month = test_user.monthly_video_limit
        
        with patch.object(video_service.user_service, 'get_user', return_value=test_user):
            with pytest.raises(TierLimitExceeded):
                video_service.upload_video(
                    user_id=test_user.id,
                    file_obj=mock_file,
                    filename="test.mp4",
                    file_size=1024,
                    content_type="video/mp4"
                )
    
    def test_upload_video_insufficient_credits(self, video_service, test_user, mock_file, mock_ffmpeg):
        """Test video upload with insufficient credits."""
        test_user.credits_remaining = 0
        
        with patch.object(video_service.user_service, 'get_user', return_value=test_user):
            with patch.object(video_service.silent_video_service, 'is_silent_video', return_value=False):
                with pytest.raises(InsufficientCreditsError):
                    video_service.upload_video(
                        user_id=test_user.id,
                        file_obj=mock_file,
                        filename="test.mp4",
                        file_size=1024,
                        content_type="video/mp4"
                    )
    
    def test_process_video_success(self, video_service, test_user, test_video):
        """Test successful video processing."""
        with patch.object(video_service, 'get_video', return_value=test_video):
            with patch.object(video_service.user_service, 'get_user', return_value=test_user):
                with patch.object(video_service.transcription_service, 'transcribe') as mock_transcribe:
                    with patch.object(video_service.title_service, 'generate_title') as mock_title:
                        with patch.object(video_service.thumbnail_service, 'generate_thumbnails') as mock_thumb:
                            with patch.object(video_service.quality_service, 'process_video') as mock_quality:
                                with patch.object(video_service.storage_service, 'upload_video') as mock_storage:
                                    with patch.object(video_service.db, 'save'):
                                        # Setup mocks
                                        mock_transcribe.return_value = {
                                            'text': 'Test transcription',
                                            'language': 'en',
                                            'cost': 0.01
                                        }
                                        mock_title.return_value = {
                                            'title': 'Test Title',
                                            'description': 'Test Description',
                                            'tags': ['test'],
                                            'cost': 0.005
                                        }
                                        mock_thumb.return_value = {
                                            'ai_thumbnails': ['thumb1.jpg'],
                                            'extracted_thumbnails': ['thumb2.jpg'],
                                            'selected': 'thumb1.jpg',
                                            'cost': 0.02
                                        }
                                        mock_quality.return_value = {
                                            'path': '/tmp/processed.mp4',
                                            'size': 1024 * 1024
                                        }
                                        mock_storage.return_value = 'https://storage.com/video.mp4'
                                        
                                        # Process video
                                        result = video_service.process_video(
                                            video_id=test_video.id,
                                            user_id=test_user.id,
                                            options={}
                                        )
        
        assert result.status == VideoStatus.COMPLETED
        assert result.title == 'Test Title'
        assert result.transcription == 'Test transcription'
        assert len(result.ai_thumbnails) == 1
        assert result.output_video_url == 'https://storage.com/video.mp4'
    
    def test_process_video_silent(self, video_service, test_user, test_video_silent):
        """Test silent video processing (no transcription)."""
        test_video_silent.video_type = VideoType.SILENT
        
        with patch.object(video_service, 'get_video', return_value=test_video_silent):
            with patch.object(video_service.user_service, 'get_user', return_value=test_user):
                with patch.object(video_service.title_service, 'generate_title') as mock_title:
                    with patch.object(video_service.thumbnail_service, 'generate_thumbnails') as mock_thumb:
                        with patch.object(video_service.quality_service, 'process_video') as mock_quality:
                            with patch.object(video_service.storage_service, 'upload_video') as mock_storage:
                                with patch.object(video_service.db, 'save'):
                                    # Setup mocks
                                    mock_title.return_value = {
                                        'title': 'Silent Video Title',
                                        'description': 'Silent video description',
                                        'tags': ['silent'],
                                        'cost': 0.005
                                    }
                                    mock_thumb.return_value = {
                                        'ai_thumbnails': ['thumb1.jpg'],
                                        'extracted_thumbnails': ['thumb2.jpg'],
                                        'selected': 'thumb1.jpg',
                                        'cost': 0.02
                                    }
                                    mock_quality.return_value = {
                                        'path': '/tmp/processed.mp4',
                                        'size': 512 * 1024
                                    }
                                    mock_storage.return_value = 'https://storage.com/silent.mp4'
                                    
                                    # Process video
                                    result = video_service.process_video(
                                        video_id=test_video_silent.id,
                                        user_id=test_user.id,
                                        options={}
                                    )
        
        assert result.status == VideoStatus.COMPLETED
        assert result.transcription is None  # No transcription for silent videos
    
    def test_process_video_with_styles(self, video_service, test_user, test_video):
        """Test video processing with styles applied."""
        test_video.applied_styles = ['cinematic']
        
        with patch.object(video_service, 'get_video', return_value=test_video):
            with patch.object(video_service.user_service, 'get_user', return_value=test_user):
                with patch.object(video_service.transcription_service, 'transcribe'):
                    with patch.object(video_service.title_service, 'generate_title'):
                        with patch.object(video_service.thumbnail_service, 'generate_thumbnails'):
                            with patch.object(video_service.style_service, 'apply_styles') as mock_style:
                                with patch.object(video_service.quality_service, 'process_video'):
                                    with patch.object(video_service.storage_service, 'upload_video'):
                                        with patch.object(video_service.db, 'save'):
                                            # Setup style mock
                                            mock_style.return_value = {
                                                'path': '/tmp/styled.mp4',
                                                'cost': 0.01
                                            }
                                            
                                            # Process video
                                            result = video_service.process_video(
                                                video_id=test_video.id,
                                                user_id=test_user.id,
                                                options={}
                                            )
        
        assert result.applied_styles == ['cinematic']
    
    def test_process_video_with_translation(self, video_service, test_user, test_video):
        """Test video processing with translation."""
        test_video.transcription = "Hello world"
        
        with patch.object(video_service, 'get_video', return_value=test_video):
            with patch.object(video_service.user_service, 'get_user', return_value=test_user):
                with patch.object(video_service.transcription_service, 'transcribe'):
                    with patch.object(video_service.title_service, 'generate_title'):
                        with patch.object(video_service.thumbnail_service, 'generate_thumbnails'):
                            with patch.object(video_service.quality_service, 'process_video'):
                                with patch.object(video_service.storage_service, 'upload_video'):
                                    with patch.object(video_service.translation_service, 'translate') as mock_translate:
                                        with patch.object(video_service.db, 'save'):
                                            # Setup translation mock
                                            mock_translate.return_value = {
                                                'text': 'Hola mundo',
                                                'target_language': 'es',
                                                'cost': 0.005
                                            }
                                            
                                            # Process video
                                            result = video_service.process_video(
                                                video_id=test_video.id,
                                                user_id=test_user.id,
                                                options={'translation_language': 'es'}
                                            )
        
        assert result.translated_transcription == 'Hola mundo'
        assert result.translation_language == 'es'
    
    def test_process_video_failure(self, video_service, test_user, test_video):
        """Test video processing failure."""
        with patch.object(video_service, 'get_video', return_value=test_video):
            with patch.object(video_service.user_service, 'get_user', return_value=test_user):
                with patch.object(video_service.transcription_service, 'transcribe', side_effect=Exception("Transcription failed")):
                    with patch.object(video_service.db, 'save'):
                        with pytest.raises(ProcessingError):
                            video_service.process_video(
                                video_id=test_video.id,
                                user_id=test_user.id,
                                options={}
                            )
    
    def test_get_video_success(self, video_service, test_video):
        """Test getting video successfully."""
        with patch.object(video_service.db, 'get', return_value=test_video.to_dict()):
            result = video_service.get_video(
                video_id=test_video.id,
                user_id=test_video.user_id
            )
        
        assert result.id == test_video.id
        assert result.user_id == test_video.user_id
    
    def test_get_video_not_found(self, video_service):
        """Test getting non-existent video."""
        with patch.object(video_service.db, 'get', return_value=None):
            result = video_service.get_video(
                video_id="non-existent",
                user_id="test-user"
            )
        
        assert result is None
    
    def test_get_video_wrong_user(self, video_service, test_video):
        """Test getting video with wrong user ID."""
        with patch.object(video_service.db, 'get', return_value=test_video.to_dict()):
            result = video_service.get_video(
                video_id=test_video.id,
                user_id="different-user"
            )
        
        assert result is None
    
    def test_get_user_videos(self, video_service, test_user):
        """Test getting user's videos."""
        test_videos = [
            Video(
                id=f"video-{i}",
                user_id=test_user.id,
                original_filename=f"test{i}.mp4",
                file_size=1024 * 1024,
                duration=60.0,
                mime_type="video/mp4",
                status=VideoStatus.COMPLETED
            ).to_dict()
            for i in range(3)
        ]
        
        with patch.object(video_service.db, 'query', return_value=test_videos):
            videos = video_service.get_user_videos(
                user_id=test_user.id,
                limit=10,
                offset=0
            )
        
        assert len(videos) == 3
        assert all(video.user_id == test_user.id for video in videos)
    
    def test_delete_video_success(self, video_service, test_video):
        """Test successful video deletion."""
        with patch.object(video_service, 'get_video', return_value=test_video):
            with patch.object(video_service.db, 'save'):
                with patch.object(video_service.storage_service, 'schedule_deletion'):
                    result = video_service.delete_video(
                        video_id=test_video.id,
                        user_id=test_video.user_id
                    )
        
        assert result is True
        assert test_video.is_deleted is True
    
    def test_delete_video_not_found(self, video_service):
        """Test deleting non-existent video."""
        with patch.object(video_service, 'get_video', return_value=None):
            result = video_service.delete_video(
                video_id="non-existent",
                user_id="test-user"
            )
        
        assert result is False
    
    def test_delete_video_wrong_user(self, video_service, test_video):
        """Test deleting video with wrong user ID."""
        with patch.object(video_service, 'get_video', return_value=test_video):
            result = video_service.delete_video(
                video_id=test_video.id,
                user_id="different-user"
            )
        
        assert result is False
    
    def test_get_processing_status(self, video_service, test_video):
        """Test getting processing status."""
        test_video.status = VideoStatus.PROCESSING
        
        with patch.object(video_service, 'get_video', return_value=test_video):
            with patch.object(video_service.db, 'query', return_value=[{'status': 'processing'}]):
                status = video_service.get_processing_status(
                    video_id=test_video.id,
                    user_id=test_video.user_id
                )
        
        assert status is not None
        assert status['video']['status'] == 'processing'
        assert status['progress'] == test_video.get_progress()
    
    def test_extract_audio(self, video_service, mock_ffmpeg, temp_video_file):
        """Test audio extraction."""
        result = video_service._extract_audio(temp_video_file)
        
        assert result.endswith('.wav')
        mock_ffmpeg.input.assert_called_once()
    
    def test_cleanup_temporary_files(self, video_service, test_video, tmp_path):
        """Test cleanup of temporary files."""
        # Create temporary files
        test_video.original_path = str(tmp_path / "original.mp4")
        test_video.processing_path = str(tmp_path / "processing.mp4")
        test_video.output_path = str(tmp_path / "output.mp4")
        
        for path in [test_video.original_path, test_video.processing_path, test_video.output_path]:
            Path(path).touch()
        
        # Run cleanup
        video_service._cleanup_temporary_files(test_video)
        
        # Verify files are deleted
        for path in [test_video.original_path, test_video.processing_path, test_video.output_path]:
            assert not Path(path).exists()