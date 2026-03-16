"""
Integration tests for video API.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
import tempfile
import os

from src.app.config import TestingConfig

class TestVideoAPI:
    """Test video API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import create_app
        app, _ = create_app(TestingConfig)
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def auth_headers(self, client):
        """Create authenticated user and return headers."""
        # Register and login
        register_data = {
            "email": "video@example.com",
            "password": "StrongPassword123!"
        }
        
        response = client.post('/api/v1/auth/register', json=register_data)
        response_data = json.loads(response.data)
        access_token = response_data['access_token']
        
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'multipart/form-data'
        }
    
    def test_upload_video_success(self, client, auth_headers):
        """Test successful video upload."""
        # Create a test video file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Write some test data (not a real video, but enough for testing)
            f.write(b'test video content')
            video_path = f.name
        
        try:
            # Mock video processing
            with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
                mock_upload.return_value = (
                    MagicMock(
                        id='test_video_id',
                        user_id='test_user_id',
                        original_filename='test.mp4',
                        file_size=1024,
                        duration=30.0,
                        mime_type='video/mp4',
                        to_dict=lambda: {'id': 'test_video_id', 'status': 'uploaded'}
                    ),
                    video_path
                )
                
                # Upload video
                with open(video_path, 'rb') as video_file:
                    data = {
                        'video': (video_file, 'test.mp4'),
                        'quality': '1080p',
                        'styles': '["cinematic"]'
                    }
                    
                    response = client.post('/api/v1/videos/upload', 
                                         data=data,
                                         headers=auth_headers,
                                         content_type='multipart/form-data')
                
                assert response.status_code == 200
                response_data = json.loads(response.data)
                
                assert response_data['success'] == True
                assert 'video_id' in response_data
                assert response_data['video_id'] == 'test_video_id'
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
    
    def test_upload_video_no_file(self, client, auth_headers):
        """Test video upload without file."""
        response = client.post('/api/v1/videos/upload', 
                             data={},
                             headers=auth_headers)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_FILE'
    
    def test_upload_video_invalid_format(self, client, auth_headers):
        """Test video upload with invalid format."""
        # Create a test file with invalid extension
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b'test content')
            file_path = f.name
        
        try:
            with open(file_path, 'rb') as file_obj:
                data = {
                    'video': (file_obj, 'test.txt')
                }
                
                response = client.post('/api/v1/videos/upload', 
                                     data=data,
                                     headers=auth_headers,
                                     content_type='multipart/form-data')
            
            assert response.status_code == 400
            response_data = json.loads(response.data)
            
            assert response_data['error']['code'] == 'INVALID_VIDEO_FORMAT'
        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)
    
    def test_upload_video_too_large(self, client, auth_headers):
        """Test video upload with file too large."""
        # Mock file size check
        with patch('src.api.v1.routers.videos.request') as mock_request:
            mock_request.content_length = 3 * 1024 * 1024 * 1024  # 3GB
            mock_request.files = {'video': MagicMock(
                filename='test.mp4',
                content_type='video/mp4',
                save=MagicMock()
            )}
            
            response = client.post('/api/v1/videos/upload', 
                                 data={},
                                 headers=auth_headers)
            
            assert response.status_code == 413
            response_data = json.loads(response.data)
            
            assert response_data['error']['code'] == 'VIDEO_TOO_LARGE'
    
    def test_get_video_status(self, client, auth_headers):
        """Test getting video processing status."""
        video_id = 'test_video_id'
        
        # Mock video service
        with patch('src.services.video_service.VideoService.get_processing_status') as mock_status:
            mock_status.return_value = {
                'video': {
                    'id': video_id,
                    'status': 'processing',
                    'progress': 50
                },
                'job': {
                    'id': 'test_job_id',
                    'status': 'processing'
                }
            }
            
            response = client.get(f'/api/v1/videos/{video_id}/status', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['video']['id'] == video_id
            assert response_data['video']['status'] == 'processing'
            assert response_data['video']['progress'] == 50
    
    def test_get_video_status_not_found(self, client, auth_headers):
        """Test getting status for non-existent video."""
        video_id = 'nonexistent_video_id'
        
        # Mock video service returning None
        with patch('src.services.video_service.VideoService.get_processing_status') as mock_status:
            mock_status.return_value = None
            
            response = client.get(f'/api/v1/videos/{video_id}/status', 
                                headers=auth_headers)
            
            assert response.status_code == 404
            response_data = json.loads(response.data)
            
            assert response_data['error']['code'] == 'NOT_FOUND'
    
    def test_get_video_results(self, client, auth_headers):
        """Test getting video processing results."""
        video_id = 'test_video_id'
        
        # Mock video service
        with patch('src.services.video_service.VideoService.get_video') as mock_get:
            mock_video = MagicMock()
            mock_video.id = video_id
            mock_video.status = 'completed'
            mock_video.output_video_url = 'https://storage.example.com/video.mp4'
            mock_video.title = 'Test Video Title'
            mock_video.description = 'Test Video Description'
            mock_video.transcription = 'Test transcription text'
            mock_video.ai_thumbnails = ['thumb1.jpg', 'thumb2.jpg']
            mock_video.to_dict.return_value = {
                'id': video_id,
                'status': 'completed',
                'output_video_url': 'https://storage.example.com/video.mp4',
                'title': 'Test Video Title',
                'description': 'Test Video Description',
                'transcription': 'Test transcription text',
                'ai_thumbnails': ['thumb1.jpg', 'thumb2.jpg']
            }
            mock_get.return_value = mock_video
            
            response = client.get(f'/api/v1/videos/{video_id}/results', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['video']['id'] == video_id
            assert response_data['video']['status'] == 'completed'
            assert response_data['video']['output_video_url'] == 'https://storage.example.com/video.mp4'
    
    def test_get_video_results_not_completed(self, client, auth_headers):
        """Test getting results for video still processing."""
        video_id = 'test_video_id'
        
        # Mock video service
        with patch('src.services.video_service.VideoService.get_video') as mock_get:
            mock_video = MagicMock()
            mock_video.id = video_id
            mock_video.status = 'processing'
            mock_video.to_dict.return_value = {
                'id': video_id,
                'status': 'processing',
                'progress': 50
            }
            mock_get.return_value = mock_video
            
            response = client.get(f'/api/v1/videos/{video_id}/results', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['video']['status'] == 'processing'
            assert 'output_video_url' not in response_data['video']
    
    def test_download_video(self, client, auth_headers):
        """Test video download."""
        video_id = 'test_video_id'
        
        # Mock storage service
        with patch('src.services.storage_service.StorageService.generate_download_url') as mock_url:
            mock_url.return_value = 'https://storage.example.com/download/video.mp4?token=abc123'
            
            response = client.get(f'/api/v1/videos/{video_id}/download', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'download_url' in response_data
            assert response_data['download_url'] == 'https://storage.example.com/download/video.mp4?token=abc123'
    
    def test_list_user_videos(self, client, auth_headers):
        """Test listing user's videos."""
        # Mock video service
        with patch('src.services.video_service.VideoService.get_user_videos') as mock_list:
            mock_videos = [
                MagicMock(
                    id='video1',
                    status='completed',
                    title='Video 1',
                    created_at='2024-01-01T00:00:00',
                    to_dict=lambda: {
                        'id': 'video1',
                        'status': 'completed',
                        'title': 'Video 1',
                        'created_at': '2024-01-01T00:00:00'
                    }
                ),
                MagicMock(
                    id='video2',
                    status='processing',
                    title='Video 2',
                    created_at='2024-01-02T00:00:00',
                    to_dict=lambda: {
                        'id': 'video2',
                        'status': 'processing',
                        'title': 'Video 2',
                        'created_at': '2024-01-02T00:00:00'
                    }
                )
            ]
            mock_list.return_value = mock_videos
            
            response = client.get('/api/v1/videos', headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'videos' in response_data
            assert len(response_data['videos']) == 2
            assert response_data['videos'][0]['id'] == 'video1'
            assert response_data['videos'][1]['id'] == 'video2'
    
    def test_list_user_videos_pagination(self, client, auth_headers):
        """Test listing videos with pagination."""
        with patch('src.services.video_service.VideoService.get_user_videos') as mock_list:
            mock_list.return_value = []
            
            # Test with pagination parameters
            response = client.get('/api/v1/videos?page=2&per_page=10', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            mock_list.assert_called_once()
            
            # Check pagination parameters were passed
            call_args = mock_list.call_args
            assert call_args[1]['offset'] == 10  # (page-1) * per_page
            assert call_args[1]['limit'] == 10
    
    def test_delete_video(self, client, auth_headers):
        """Test video deletion."""
        video_id = 'test_video_id'
        
        # Mock video service
        with patch('src.services.video_service.VideoService.delete_video') as mock_delete:
            mock_delete.return_value = True
            
            response = client.delete(f'/api/v1/videos/{video_id}', 
                                   headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['message'] == 'Video deleted successfully'
    
    def test_delete_video_not_found(self, client, auth_headers):
        """Test deleting non-existent video."""
        video_id = 'nonexistent_video_id'
        
        # Mock video service
        with patch('src.services.video_service.VideoService.delete_video') as mock_delete:
            mock_delete.return_value = False
            
            response = client.delete(f'/api/v1/videos/{video_id}', 
                                   headers=auth_headers)
            
            assert response.status_code == 404
            response_data = json.loads(response.data)
            
            assert response_data['error']['code'] == 'NOT_FOUND'
    
    def test_get_video_analytics(self, client, auth_headers):
        """Test getting video analytics."""
        # Mock analytics service
        with patch('src.services.video_service.VideoService.get_user_videos') as mock_list:
            mock_videos = [
                MagicMock(
                    id='video1',
                    status='completed',
                    duration=300,
                    total_cost=0.05,
                    created_at='2024-01-01T00:00:00',
                    to_dict=lambda: {
                        'id': 'video1',
                        'status': 'completed',
                        'duration': 300,
                        'total_cost': 0.05,
                        'created_at': '2024-01-01T00:00:00'
                    }
                )
            ]
            mock_list.return_value = mock_videos
            
            response = client.get('/api/v1/videos/analytics', headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'analytics' in response_data
            assert 'total_videos' in response_data['analytics']
            assert 'total_processing_time' in response_data['analytics']
            assert 'total_cost' in response_data['analytics']
    
    def test_websocket_connection(self, client):
        """Test WebSocket connection for real-time updates."""
        # Note: WebSocket testing requires a different approach
        # This is a placeholder test
        pass
    
    def test_upload_video_rate_limiting(self, client, auth_headers):
        """Test rate limiting on video upload."""
        # Mock file upload multiple times
        with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
            mock_upload.return_value = (
                MagicMock(
                    id='test_video_id',
                    to_dict=lambda: {'id': 'test_video_id'}
                ),
                '/tmp/test.mp4'
            )
            
            responses = []
            for i in range(15):  # More than free tier limit
                with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
                    f.write(b'test')
                    f.seek(0)
                    
                    data = {
                        'video': (f, 'test.mp4')
                    }
                    
                    response = client.post('/api/v1/videos/upload', 
                                         data=data,
                                         headers=auth_headers,
                                         content_type='multipart/form-data')
                    responses.append(response.status_code)
            
            # Some requests should be rate limited
            assert 429 in responses
    
    def test_tier_limit_enforcement(self, client, auth_headers):
        """Test tier limit enforcement on video upload."""
        # Mock tier limit exceeded
        from src.core.exceptions import TierLimitExceeded
        
        with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
            mock_upload.side_effect = TierLimitExceeded(
                'monthly_videos',
                3,
                3
            )
            
            with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
                f.write(b'test')
                f.seek(0)
                
                data = {
                    'video': (f, 'test.mp4')
                }
                
                response = client.post('/api/v1/videos/upload', 
                                     data=data,
                                     headers=auth_headers,
                                     content_type='multipart/form-data')
                
                assert response.status_code == 403
                response_data = json.loads(response.data)
                
                assert response_data['error']['code'] == 'TIER_LIMIT_EXCEEDED'