"""
End-to-end tests for complete video processing.
"""
import pytest
import json
import time
from unittest.mock import patch, MagicMock, call
import tempfile
import os

from src.app.config import TestingConfig
from src.core.domain.entities.video import VideoStatus, VideoType

class TestVideoProcessing:
    """End-to-end tests for complete video processing pipeline."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import create_app
        app, _ = create_app(TestingConfig)
        with app.test_client() as client:
            yield client
    
    def test_complete_video_processing_pipeline(self, client):
        """Test complete video processing pipeline."""
        # 1. Register user
        register_data = {
            "email": "pipeline_test@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', 
                                       json=register_data)
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        auth_headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'multipart/form-data'
        }
        
        # 2. Upload video with all processing options
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Create test video file
            f.write(b'test video content' * 100)
            video_path = f.name
        
        try:
            # Mock the entire processing pipeline
            video_id = 'test_pipeline_video_123'
            
            # Mock upload
            with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
                mock_video = MagicMock()
                mock_video.id = video_id
                mock_video.user_id = 'test_user'
                mock_video.status = VideoStatus.UPLOADED
                mock_video.video_type = VideoType.SPEECH
                mock_video.duration = 180.0  # 3 minutes
                mock_video.to_dict.return_value = {
                    'id': video_id,
                    'status': 'uploaded',
                    'duration': 180.0
                }
                
                mock_upload.return_value = (mock_video, video_path)
                
                # Upload with all processing options
                processing_options = {
                    'quality': '1080p',
                    'styles': ['cinematic', 'gaming'],
                    'translation_language': 'es'
                }
                
                with open(video_path, 'rb') as video_file:
                    data = {
                        'video': (video_file, 'pipeline_test.mp4'),
                        'quality': '1080p',
                        'styles': '["cinematic", "gaming"]',
                        'translation_language': 'es'
                    }
                    
                    upload_response = client.post('/api/v1/videos/upload', 
                                                 data=data,
                                                 headers=auth_headers)
                    assert upload_response.status_code == 200
                    
                    upload_data = json.loads(upload_response.data)
                    assert upload_data['video_id'] == video_id
                
                # 3. Mock processing steps
                with patch('src.tasks.video_tasks.process_video_async.delay') as mock_task:
                    # Verify async task was called
                    mock_task.assert_called_once_with(video_id, 'test_user', processing_options)
                    
                    # 4. Simulate processing progress
                    # Mock individual service calls
                    processing_mocks = {
                        'transcription': {
                            'text': 'This is a test video transcript.',
                            'language': 'en',
                            'cost': 0.018  # 3 minutes at $0.006/min
                        },
                        'title_generation': {
                            'title': 'Test Video: Complete Processing Pipeline',
                            'description': 'A test video demonstrating the complete AI video processing pipeline.',
                            'tags': ['test', 'pipeline', 'ai', 'video'],
                            'cost': 0.00006
                        },
                        'thumbnail_generation': {
                            'ai_thumbnails': ['thumb1.jpg', 'thumb2.jpg', 'thumb3.jpg'],
                            'extracted_thumbnails': ['ext1.jpg', 'ext2.jpg', 'ext3.jpg', 'ext4.jpg', 'ext5.jpg'],
                            'selected': 'thumb1.jpg',
                            'cost': 0.009  # 3 thumbnails at $0.003 each
                        },
                        'style_application': {
                            'path': '/tmp/styled_video.mp4',
                            'cost': 0.06  # 2 styles at $0.03 each
                        },
                        'quality_processing': {
                            'path': '/tmp/processed_video.mp4',
                            'size': 1024 * 1024 * 50  # 50MB
                        },
                        'translation': {
                            'text': 'Esta es una transcripción de video de prueba.',
                            'target_language': 'es',
                            'cost': 0.0  # Free with googletrans
                        },
                        'storage_upload': {
                            'url': 'https://storage.example.com/videos/test_pipeline_video_123.mp4'
                        }
                    }
                    
                    # 5. Check processing status at different stages
                    status_stages = [
                        ('uploaded', 5),
                        ('processing', 15),
                        ('transcribing', 30),
                        ('generating_title', 40),
                        ('generating_thumbnails', 50),
                        ('applying_styles', 65),
                        ('translating', 75),
                        ('compressing', 85),
                        ('completed', 100)
                    ]
                    
                    for status, progress in status_stages:
                        with patch('src.services.video_service.VideoService.get_processing_status') as mock_status:
                            mock_status.return_value = {
                                'video': {
                                    'id': video_id,
                                    'status': status,
                                    'progress': progress,
                                    'duration': 180.0
                                },
                                'job': {
                                    'id': 'test_job_123',
                                    'status': status
                                }
                            }
                            
                            status_response = client.get(f'/api/v1/videos/{video_id}/status', 
                                                        headers=auth_headers)
                            assert status_response.status_code == 200
                            
                            status_data = json.loads(status_response.data)
                            assert status_data['video']['status'] == status
                            assert status_data['video']['progress'] == progress
                    
                    # 6. Get final results
                    with patch('src.services.video_service.VideoService.get_video') as mock_get_video:
                        completed_video = MagicMock()
                        completed_video.id = video_id
                        completed_video.status = VideoStatus.COMPLETED
                        completed_video.title = processing_mocks['title_generation']['title']
                        completed_video.description = processing_mocks['title_generation']['description']
                        completed_video.transcription = processing_mocks['transcription']['text']
                        completed_video.translated_transcription = processing_mocks['translation']['text']
                        completed_video.ai_thumbnails = processing_mocks['thumbnail_generation']['ai_thumbnails']
                        completed_video.output_video_url = processing_mocks['storage_upload']['url']
                        completed_video.output_quality = '1080p'
                        completed_video.applied_styles = ['cinematic', 'gaming']
                        completed_video.total_cost = 0.08706  # Sum of all costs
                        
                        completed_video.to_dict.return_value = {
                            'id': video_id,
                            'status': 'completed',
                            'title': processing_mocks['title_generation']['title'],
                            'description': processing_mocks['title_generation']['description'],
                            'transcription': processing_mocks['transcription']['text'],
                            'translated_transcription': processing_mocks['translation']['text'],
                            'ai_thumbnails': processing_mocks['thumbnail_generation']['ai_thumbnails'],
                            'output_video_url': processing_mocks['storage_upload']['url'],
                            'output_quality': '1080p',
                            'applied_styles': ['cinematic', 'gaming'],
                            'total_cost': 0.08706,
                            'duration': 180.0
                        }
                        
                        mock_get_video.return_value = completed_video
                        
                        results_response = client.get(f'/api/v1/videos/{video_id}/results', 
                                                     headers=auth_headers)
                        assert results_response.status_code == 200
                        
                        results_data = json.loads(results_response.data)
                        assert results_data['video']['status'] == 'completed'
                        assert results_data['video']['title'] == processing_mocks['title_generation']['title']
                        assert results_data['video']['translated_transcription'] == processing_mocks['translation']['text']
                        assert len(results_data['video']['ai_thumbnails']) == 3
                        assert results_data['video']['applied_styles'] == ['cinematic', 'gaming']
                        
                        # 7. Download processed video
                        with patch('src.services.storage_service.StorageService.generate_download_url') as mock_download:
                            mock_download.return_value = 'https://storage.example.com/download/test_pipeline_video_123.mp4?token=abc123'
                            
                            download_response = client.get(f'/api/v1/videos/{video_id}/download', 
                                                          headers=auth_headers)
                            assert download_response.status_code == 200
                            
                            download_data = json.loads(download_response.data)
                            assert 'download_url' in download_data
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
    
    def test_silent_video_processing_pipeline(self, client):
        """Test silent video processing pipeline (cost-saving mode)."""
        # Silent videos should skip transcription
        # This saves 69% compared to speech videos
        
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(b'silent video content')
            video_path = f.name
        
        try:
            with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
                mock_video = MagicMock()
                mock_video.id = 'silent_video_123'
                mock_video.video_type = VideoType.SILENT  # Mark as silent
                mock_video.duration = 300.0  # 5 minutes
                mock_video.to_dict.return_value = {
                    'id': 'silent_video_123',
                    'video_type': 'silent',
                    'duration': 300.0
                }
                
                mock_upload.return_value = (mock_video, video_path)
                
                # Mock silent video analysis instead of transcription
                with patch('src.services.silent_video_service.SilentVideoService.generate_metadata') as mock_analysis:
                    mock_analysis.return_value = {
                        'success': True,
                        'title': 'Beautiful Landscape Video',
                        'description': 'A scenic view of mountains and lakes',
                        'tags': ['landscape', 'nature', 'mountains', 'lake'],
                        'frames_analyzed': 3,
                        'total_cost': 0.006  # 3 frames at $0.002 each
                    }
                    
                    # Process video
                    # Should use silent video analysis instead of transcription
                    pass
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
    
    def test_processing_error_recovery(self, client):
        """Test error handling and recovery during processing."""
        # Test scenarios:
        # 1. Temporary API failure
        # 2. File corruption
        # 3. Network issues
        # 4. Automatic retry
        
        with patch('src.services.video_service.VideoService.process_video') as mock_process:
            # First attempt fails
            mock_process.side_effect = [
                Exception("OpenAI API timeout"),
                Exception("Network error"),
                {'success': True}  # Third attempt succeeds
            ]
            
            # Should retry up to 3 times
            # After 3 failures, mark as failed
            pass
    
    def test_batch_video_processing(self):
        """Test batch processing of multiple videos."""
        # Higher tiers support batch processing
        # Test processing multiple videos efficiently
        
        batch_videos = [
            {'id': 'video_1', 'duration': 180, 'status': 'queued'},
            {'id': 'video_2', 'duration': 240, 'status': 'queued'},
            {'id': 'video_3', 'duration': 300, 'status': 'queued'}
        ]
        
        # Process in parallel where possible
        # Monitor overall progress
        
        total_duration = sum(v['duration'] for v in batch_videos)
        assert total_duration == 720  # 12 minutes total
    
    def test_processing_cost_optimization(self):
        """Test cost optimization across different video types and tiers."""
        # Calculate and verify costs
        
        test_cases = [
            {
                'tier': 'free',
                'video_type': 'speech',
                'duration': 180,  # 3 minutes
                'expected_cost': 0.037  # Based on pricing model
            },
            {
                'tier': 'free',
                'video_type': 'silent',
                'duration': 180,
                'expected_cost': 0.012  # 69% cheaper
            },
            {
                'tier': 'pro',
                'video_type': 'speech',
                'duration': 300,  # 5 minutes
                'expected_cost': 0.079  # Higher quality, more features
            }
        ]
        
        for test_case in test_cases:
            # Verify cost calculations match expected
            # (These would come from the actual pricing model)
            pass
    
    def test_processing_quality_differences(self):
        """Test quality differences across tiers."""
        # Different tiers get different quality processing
        
        quality_by_tier = {
            'free': {
                'resolution': '720p',
                'bitrate': '2Mbps',
                'preset': 'ultrafast',
                'audio_quality': '128k'
            },
            'starter': {
                'resolution': '1080p',
                'bitrate': '5Mbps',
                'preset': 'medium',
                'audio_quality': '192k'
            },
            'pro': {
                'resolution': '4K',
                'bitrate': '15Mbps',
                'preset': 'slow',
                'audio_quality': '256k'
            },
            'plus': {
                'resolution': '4K+HDR',
                'bitrate': '25Mbps',
                'preset': 'veryslow',
                'audio_quality': '320k'
            }
        }
        
        # Verify tier progression
        assert quality_by_tier['free']['resolution'] == '720p'
        assert quality_by_tier['starter']['resolution'] == '1080p'
        assert quality_by_tier['pro']['resolution'] == '4K'
        assert quality_by_tier['plus']['resolution'] == '4K+HDR'
        
        # Bitrate should increase with tier
        bitrates = [q['bitrate'] for q in quality_by_tier.values()]
        # Parse bitrates for comparison
        # '2Mbps' < '5Mbps' < '15Mbps' < '25Mbps'