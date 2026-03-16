"""
Test FFmpeg provider.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import subprocess

from src.providers.ffmpeg_provider import FFmpegProvider
from src.core.exceptions import ProcessingError

class TestFFmpegProvider:
    """Test FFmpeg provider."""
    
    def setup_method(self):
        """Setup test."""
        self.ffmpeg = FFmpegProvider()
    
    def test_initialization(self):
        """Test FFmpeg provider initialization."""
        assert self.ffmpeg.ffmpeg_path == "ffmpeg"
        assert self.ffmpeg.ffprobe_path == "ffprobe"
    
    @patch('subprocess.run')
    def test_get_video_duration(self, mock_run):
        """Test getting video duration."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.stdout = """{
            "format": {
                "duration": "300.5"
            }
        }"""
        mock_run.return_value = mock_result
        
        duration = self.ffmpeg.get_video_duration("test.mp4")
        
        assert duration == 300.5
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_get_video_resolution(self, mock_run):
        """Test getting video resolution."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.stdout = """{
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080
                }
            ]
        }"""
        mock_run.return_value = mock_result
        
        width, height = self.ffmpeg.get_video_resolution("test.mp4")
        
        assert width == 1920
        assert height == 1080
    
    @patch('subprocess.run')
    def test_get_video_framerate(self, mock_run):
        """Test getting video framerate."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.stdout = """{
            "streams": [
                {
                    "codec_type": "video",
                    "avg_frame_rate": "30/1"
                }
            ]
        }"""
        mock_run.return_value = mock_result
        
        framerate = self.ffmpeg.get_video_framerate("test.mp4")
        
        assert framerate == 30.0
    
    @patch('subprocess.run')
    def test_get_video_codec(self, mock_run):
        """Test getting video codec."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.stdout = """{
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264"
                }
            ]
        }"""
        mock_run.return_value = mock_result
        
        codec = self.ffmpeg.get_video_codec("test.mp4")
        
        assert codec == "h264"
    
    @patch('subprocess.run')
    def test_extract_audio(self, mock_run):
        """Test audio extraction."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_file:
            video_path = video_file.name
        
        audio_path = video_path.replace(".mp4", ".wav")
        
        try:
            self.ffmpeg.extract_audio(video_path, audio_path)
            
            # Check command was called correctly
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            
            assert "ffmpeg" in args[0]
            assert "-i" in args
            assert video_path in args
            assert audio_path in args[-1]
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
            if os.path.exists(audio_path):
                os.unlink(audio_path)
    
    @patch('subprocess.run')
    def test_extract_thumbnails(self, mock_run):
        """Test thumbnail extraction."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_file:
            video_path = video_file.name
        
        output_dir = tempfile.mkdtemp()
        
        try:
            thumbnails = self.ffmpeg.extract_thumbnails(video_path, output_dir, 5)
            
            # Should extract 5 thumbnails
            assert len(thumbnails) == 5
            
            # Check each thumbnail exists (mocked)
            for thumbnail in thumbnails:
                assert thumbnail.endswith(".jpg")
                assert os.path.basename(thumbnail).startswith("thumbnail_")
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
            if os.path.exists(output_dir):
                import shutil
                shutil.rmtree(output_dir)
    
    @patch('subprocess.run')
    def test_process_video(self, mock_run):
        """Test video processing."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as input_file:
            input_path = input_file.name
        
        output_path = input_path.replace(".mp4", "_processed.mp4")
        
        try:
            self.ffmpeg.process_video(
                input_path=input_path,
                output_path=output_path,
                quality="1080p",
                preset="medium",
                crf=18,
                audio_bitrate="192k"
            )
            
            # Check command was called
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            
            assert "ffmpeg" in args[0]
            assert "-i" in args
            assert input_path in args
            assert output_path in args[-1]
            assert "-preset" in args
            assert "medium" in args[args.index("-preset") + 1]
            assert "-crf" in args
            assert "18" in args[args.index("-crf") + 1]
        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    @patch('subprocess.run')
    def test_detect_silent_video(self, mock_run):
        """Test silent video detection."""
        # Mock subprocess response for non-silent video
        mock_result = Mock()
        mock_result.stdout = """{
            "streams": [
                {
                    "codec_type": "audio",
                    "tags": {
                        "language": "eng"
                    }
                }
            ]
        }"""
        mock_run.return_value = mock_result
        
        is_silent = self.ffmpeg.detect_silent_video("test.mp4")
        
        assert not is_silent
        
        # Mock subprocess response for silent video
        mock_result.stdout = """{
            "streams": []
        }"""
        mock_run.return_value = mock_result
        
        is_silent = self.ffmpeg.detect_silent_video("test.mp4")
        
        assert is_silent
    
    @patch('subprocess.run')
    def test_ffmpeg_error_handling(self, mock_run):
        """Test FFmpeg error handling."""
        # Mock subprocess error
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
        
        with pytest.raises(ProcessingError):
            self.ffmpeg.get_video_duration("test.mp4")
    
    def test_generate_ffmpeg_command(self):
        """Test FFmpeg command generation."""
        # Test basic command
        cmd = self.ffmpeg._generate_ffmpeg_command(
            input_path="input.mp4",
            output_path="output.mp4",
            filters=["scale=1920:1080"],
            codec="libx264",
            preset="medium",
            crf=18,
            audio_bitrate="192k"
        )
        
        assert "ffmpeg" in cmd[0]
        assert "-i" in cmd
        assert "input.mp4" in cmd
        assert "output.mp4" in cmd[-1]
        assert "-preset" in cmd
        assert "medium" in cmd[cmd.index("-preset") + 1]
        assert "-crf" in cmd
        assert "18" in cmd[cmd.index("-crf") + 1]
        assert "-c:a" in cmd
        assert "aac" in cmd[cmd.index("-c:a") + 1]
        
        # Test with filters
        cmd = self.ffmpeg._generate_ffmpeg_command(
            input_path="input.mp4",
            output_path="output.mp4",
            filters=["scale=1920:1080", "fps=30"],
            codec="libx264"
        )
        
        assert "-filter_complex" in cmd
        assert "scale=1920:1080,fps=30" in cmd
    
    def test_get_quality_settings(self):
        """Test quality settings generation."""
        # Test 1080p quality
        settings = self.ffmpeg.get_quality_settings("1080p", "starter")
        
        assert settings["resolution"] == (1920, 1080)
        assert settings["preset"] == "medium"
        assert settings["crf"] == 18
        assert settings["video_bitrate"] == 5000000
        assert settings["audio_bitrate"] == "192k"
        
        # Test 4K quality
        settings = self.ffmpeg.get_quality_settings("4k", "pro")
        
        assert settings["resolution"] == (3840, 2160)
        assert settings["preset"] == "slow"
        assert settings["crf"] == 16
        assert settings["video_bitrate"] == 15000000
        assert settings["audio_bitrate"] == "256k"
    
    def test_apply_video_style(self):
        """Test video style application."""
        style_filters = [
            "colorchannelmixer=rr=1.2:gg=1.0:bb=0.8",
            "curves=preset=strong_contrast",
            "unsharp=5:5:0.5:5:5:0.5"
        ]
        
        filters = self.ffmpeg._apply_video_style(style_filters)
        
        assert "colorchannelmixer=rr=1.2:gg=1.0:bb=0.8" in filters
        assert "curves=preset=strong_contrast" in filters
        assert "unsharp=5:5:0.5:5:5:0.5" in filters
    
    @patch('subprocess.run')
    def test_merge_video_and_audio(self, mock_run):
        """Test video and audio merging."""
        # Mock subprocess response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_file:
            video_path = video_file.name
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
        
        output_path = video_path.replace(".mp4", "_merged.mp4")
        
        try:
            self.ffmpeg.merge_video_and_audio(video_path, audio_path, output_path)
            
            # Check command was called
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            
            assert "ffmpeg" in args[0]
            assert "-i" in args
            assert video_path in args
            assert audio_path in args[args.index("-i", 2) + 1]
            assert output_path in args[-1]
            assert "-c:v" in args
            assert "copy" in args[args.index("-c:v") + 1]
            assert "-c:a" in args
            assert "aac" in args[args.index("-c:a") + 1]
        finally:
            for path in [video_path, audio_path, output_path]:
                if os.path.exists(path):
                    os.unlink(path)