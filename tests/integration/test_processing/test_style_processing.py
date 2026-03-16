"""
Integration tests for video style processing.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import os
import yaml

from src.app.config import TestingConfig
from src.services.style_service import StyleService
from src.core.domain.value_objects.video_style import VideoStyle, StyleCategory

class TestStyleProcessing:
    """Test video style processing."""
    
    @pytest.fixture
    def style_service(self):
        """Create style service instance."""
        return StyleService()
    
    @pytest.fixture
    def sample_style_config(self):
        """Create sample style configuration."""
        return {
            "cinematic": {
                "name": "Cinematic",
                "category": "cinematic",
                "description": "Movie-like film look with enhanced contrast and colors",
                "preview_image": "/static/images/styles/cinematic-preview.jpg",
                "ffmpeg_filters": [
                    "colorchannelmixer=rr=1.2:gg=1.0:bb=0.8",
                    "curves=preset=strong_contrast",
                    "unsharp=5:5:0.5:5:5:0.5"
                ],
                "color_grading": {
                    "brightness": 0.1,
                    "contrast": 1.2,
                    "saturation": 1.1,
                    "gamma": 0.9
                },
                "transitions": ["fade"],
                "text_overlay": {
                    "font": "Arial",
                    "size": 24,
                    "color": "#FFFFFF"
                },
                "prompt_template": "cinematic film look, professional grade, movie quality, {description}",
                "negative_prompt": "amateur, low quality, blurry",
                "style_weight": 0.8,
                "available_tiers": ["free", "starter", "pro", "plus"],
                "requires_gpu": False,
                "created_by": "system",
                "is_public": True
            }
        }
    
    def test_load_styles(self, style_service, sample_style_config):
        """Test loading video styles from config."""
        # Mock config file loading
        mock_config = yaml.dump(sample_style_config)
        
        with patch('builtins.open', mock_open(read_data=mock_config)):
            with patch('yaml.safe_load') as mock_yaml:
                mock_yaml.return_value = sample_style_config
                
                styles = style_service.load_styles()
                
                assert len(styles) > 0
                assert 'cinematic' in styles
                assert isinstance(styles['cinematic'], VideoStyle)
                assert styles['cinematic'].name == "Cinematic"
                assert styles['cinematic'].category == StyleCategory.CINEMATIC
    
    def test_get_available_styles(self, style_service):
        """Test getting available styles for a tier."""
        # Mock styles
        mock_styles = {
            'cinematic': MagicMock(spec=VideoStyle),
            'gaming': MagicMock(spec=VideoStyle),
            'educational': MagicMock(spec=VideoStyle),
            'corporate': MagicMock(spec=VideoStyle)
        }
        
        # Configure mock styles
        mock_styles['cinematic'].is_available_for_tier.return_value = True
        mock_styles['gaming'].is_available_for_tier.return_value = True
        mock_styles['educational'].is_available_for_tier.return_value = False  # Not available for free
        mock_styles['corporate'].is_available_for_tier.return_value = False   # Not available for free
        
        with patch.object(style_service, 'styles', mock_styles):
            # Free tier
            free_styles = style_service.get_available_styles('free')
            
            # Should only include styles available for free tier
            assert len(free_styles) == 2
            assert 'cinematic' in free_styles
            assert 'gaming' in free_styles
            assert 'educational' not in free_styles
            assert 'corporate' not in free_styles
            
            # Pro tier (all styles available)
            for style in mock_styles.values():
                style.is_available_for_tier.return_value = True
            
            pro_styles = style_service.get_available_styles('pro')
            assert len(pro_styles) == len(mock_styles)
    
    def test_apply_single_style(self, style_service):
        """Test applying a single video style."""
        # Mock FFmpeg processing
        with patch.object(style_service.ffmpeg, 'process_video') as mock_process:
            mock_process.return_value = {
                'success': True,
                'output_path': '/tmp/output.mp4',
                'processing_time': 30.5,
                'size': 1024 * 1024  # 1MB
            }
            
            # Mock style
            mock_style = MagicMock(spec=VideoStyle)
            mock_style.ffmpeg_filters = [
                "colorchannelmixer=rr=1.2:gg=1.0:bb=0.8",
                "curves=preset=strong_contrast"
            ]
            mock_style.color_grading = {
                "brightness": 0.1,
                "contrast": 1.2
            }
            mock_style.get_ffmpeg_command.return_value = [
                'ffmpeg', '-i', 'input.mp4', '-filter_complex', 
                'colorchannelmixer=rr=1.2:gg=1.0:bb=0.8,curves=preset=strong_contrast',
                'output.mp4'
            ]
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
                input_path = input_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                output_path = output_file.name
            
            try:
                result = style_service._apply_single_style(
                    input_path=input_path,
                    output_path=output_path,
                    style=mock_style,
                    tier='pro'
                )
                
                assert result['success'] == True
                assert result['output_path'] == '/tmp/output.mp4'
                assert 'processing_time' in result
                assert 'size' in result
                
                # Verify FFmpeg was called
                mock_process.assert_called_once()
            finally:
                for path in [input_path, output_path]:
                    if os.path.exists(path):
                        os.unlink(path)
    
    def test_apply_multiple_styles(self, style_service):
        """Test applying multiple styles sequentially."""
        # Mock individual style applications
        style_results = [
            {
                'success': True,
                'output_path': '/tmp/style1_output.mp4',
                'processing_time': 15.0,
                'size': 500 * 1024
            },
            {
                'success': True,
                'output_path': '/tmp/style2_output.mp4',
                'processing_time': 20.0,
                'size': 750 * 1024
            }
        ]
        
        with patch.object(style_service, '_apply_single_style') as mock_apply:
            mock_apply.side_effect = style_results
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
                input_path = input_file.name
            
            try:
                result = style_service.apply_styles(
                    video_path=input_path,
                    style_names=['cinematic', 'gaming'],
                    tier='pro'
                )
                
                assert result['success'] == True
                assert result['output_path'] == '/tmp/style2_output.mp4'
                assert result['processing_time'] == 35.0  # 15 + 20
                assert result['size'] == 750 * 1024
                assert result['styles_applied'] == ['cinematic', 'gaming']
                
                # Should have been called twice
                assert mock_apply.call_count == 2
            finally:
                if os.path.exists(input_path):
                    os.unlink(input_path)
    
    def test_style_application_error_handling(self, style_service):
        """Test error handling during style application."""
        # Mock style application failure
        with patch.object(style_service, '_apply_single_style') as mock_apply:
            mock_apply.side_effect = Exception("FFmpeg processing failed")
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
                input_path = input_file.name
            
            try:
                result = style_service.apply_styles(
                    video_path=input_path,
                    style_names=['cinematic'],
                    tier='pro'
                )
                
                # Should return error
                assert result['success'] == False
                assert 'error' in result
                assert 'FFmpeg' in result['error']
            finally:
                if os.path.exists(input_path):
                    os.unlink(input_path)
    
    def test_tier_based_style_limitations(self, style_service):
        """Test tier-based style limitations."""
        # Mock styles with tier restrictions
        mock_styles = {
            'cinematic': MagicMock(spec=VideoStyle),
            'corporate': MagicMock(spec=VideoStyle),
            'premium': MagicMock(spec=VideoStyle)
        }
        
        # Configure tier availability
        mock_styles['cinematic'].available_tiers = ['free', 'starter', 'pro', 'plus']
        mock_styles['corporate'].available_tiers = ['starter', 'pro', 'plus']
        mock_styles['premium'].available_tiers = ['pro', 'plus']
        
        with patch.object(style_service, 'styles', mock_styles):
            # Free tier can only use cinematic
            free_styles = style_service.get_available_styles('free')
            assert len(free_styles) == 1
            assert 'cinematic' in free_styles
            assert 'corporate' not in free_styles
            assert 'premium' not in free_styles
            
            # Starter tier can use cinematic and corporate
            starter_styles = style_service.get_available_styles('starter')
            assert len(starter_styles) == 2
            assert 'cinematic' in starter_styles
            assert 'corporate' in starter_styles
            assert 'premium' not in starter_styles
            
            # Pro tier can use all styles
            pro_styles = style_service.get_available_styles('pro')
            assert len(pro_styles) == 3
    
    def test_gpu_required_styles(self, style_service):
        """Test GPU-required styles."""
        # Mock styles with GPU requirements
        mock_styles = {
            'basic': MagicMock(spec=VideoStyle),
            'advanced': MagicMock(spec=VideoStyle),
            'gpu_heavy': MagicMock(spec=VideoStyle)
        }
        
        # Configure GPU requirements
        mock_styles['basic'].requires_gpu = False
        mock_styles['advanced'].requires_gpu = True
        mock_styles['gpu_heavy'].requires_gpu = True
        
        with patch.object(style_service, 'styles', mock_styles):
            # Without GPU, only basic style should be available
            with patch.object(style_service, 'has_gpu', False):
                available = style_service.get_available_styles('pro')
                assert len(available) == 1
                assert 'basic' in available
            
            # With GPU, all styles should be available
            with patch.object(style_service, 'has_gpu', True):
                available = style_service.get_available_styles('pro')
                assert len(available) == 3
    
    def test_style_cost_calculation(self, style_service):
        """Test cost calculation for style application."""
        # Mock style application
        with patch.object(style_service, '_apply_single_style') as mock_apply:
            mock_apply.return_value = {
                'success': True,
                'output_path': '/tmp/output.mp4',
                'processing_time': 30.0,
                'size': 1024 * 1024
            }
            
            # Test different tiers
            test_cases = [
                ('free', 0.0),     # Free tier: no style cost
                ('starter', 0.01), # Starter tier: $0.01 per style
                ('pro', 0.02),     # Pro tier: $0.02 per style  
                ('plus', 0.03)     # Plus tier: $0.03 per style (higher quality)
            ]
            
            for tier, expected_cost in test_cases:
                result = style_service.apply_styles(
                    video_path='/tmp/input.mp4',
                    style_names=['cinematic'],
                    tier=tier
                )
                
                assert result['cost'] == expected_cost
    
    def test_style_preview_generation(self, style_service):
        """Test style preview generation."""
        # Mock preview generation
        with patch.object(style_service.ffmpeg, 'extract_thumbnails') as mock_extract:
            mock_extract.return_value = ['/tmp/preview.jpg']
            
            with patch.object(style_service.ffmpeg, 'process_video') as mock_process:
                mock_process.return_value = {
                    'success': True,
                    'output_path': '/tmp/preview_processed.jpg'
                }
                
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
                    video_path = video_file.name
                
                try:
                    preview = style_service.generate_style_preview(
                        video_path=video_path,
                        style_name='cinematic',
                        tier='pro'
                    )
                    
                    assert preview['success'] == True
                    assert 'preview_image' in preview
                    assert preview['preview_image'].endswith('.jpg')
                    
                    # Should extract thumbnail and process it
                    mock_extract.assert_called_once()
                    mock_process.assert_called_once()
                finally:
                    if os.path.exists(video_path):
                        os.unlink(video_path)
    
    def test_custom_style_creation(self, style_service):
        """Test custom style creation."""
        # Mock user style creation
        custom_style_data = {
            'name': 'My Custom Style',
            'category': 'custom',
            'description': 'My personal video style',
            'ffmpeg_filters': ['eq=brightness=0.1', 'eq=contrast=1.1'],
            'color_grading': {'brightness': 0.1, 'contrast': 1.1},
            'prompt_template': 'custom style, {description}',
            'available_tiers': ['pro', 'plus'],
            'requires_gpu': False
        }
        
        user_id = 'user_123'
        
        # Mock saving custom style
        with patch.object(style_service.db, 'save') as mock_save:
            result = style_service.create_custom_style(
                user_id=user_id,
                style_data=custom_style_data
            )
            
            assert result['success'] == True
            assert 'style_id' in result
            
            # Verify style was saved
            mock_save.assert_called_once()
    
    def test_style_performance_optimization(self, style_service):
        """Test style performance optimization for different tiers."""
        # Test processing time limits per tier
        processing_limits = {
            'free': 60,     # 60 seconds max
            'starter': 120, # 120 seconds max
            'pro': 300,     # 300 seconds max
            'plus': 600     # 600 seconds max
        }
        
        for tier, max_time in processing_limits.items():
            # Mock style that takes a long time
            with patch.object(style_service, '_apply_single_style') as mock_apply:
                mock_apply.return_value = {
                    'success': True,
                    'output_path': '/tmp/output.mp4',
                    'processing_time': max_time + 100,  # Exceeds limit
                    'size': 1024 * 1024
                }
                
                result = style_service.apply_styles(
                    video_path='/tmp/input.mp4',
                    style_names=['heavy_style'],
                    tier=tier
                )
                
                # Should fail or be optimized for lower tiers
                if tier in ['free', 'starter']:
                    assert result['success'] == False or 'processing_time' in result
                else:
                    # Higher tiers can handle longer processing
                    assert result['success'] == True