"""
Unit tests for QualityService.
"""
import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

from src.services.quality_service import QualityService
from src.core.domain.value_objects.tier import Tier
from src.core.exceptions import ProcessingError

class TestQualityService:
    """Test QualityService class."""
    
    @pytest.fixture
    def quality_service(self):
        """Create QualityService instance."""
        return QualityService()
    
    @pytest.fixture
    def temp_video_path(self, tmp_path):
        """Create a temporary video file."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video data")
        return str(video_path)
    
    def test_get_quality_settings_free(self, quality_service):
        """Test getting quality settings for Free tier."""
        settings = quality_service.get_quality_settings(Tier.FREE)
        
        assert settings["quality"] == "720p"
        assert settings["bitrate"] == 2000000  # 2 Mbps
        assert settings["preset"] == "ultrafast"
        assert settings["crf"] == 28
        assert settings["audio_bitrate"] == 128000  # 128 kbps
    
    def test_get_quality_settings_starter(self, quality_service):
        """Test getting quality settings for Starter tier."""
        settings = quality_service.get_quality_settings(Tier.STARTER)
        
        assert settings["quality"] == "1080p"
        assert settings["bitrate"] == 5000000  # 5 Mbps
        assert settings["preset"] == "medium"
        assert settings["crf"] == 18
        assert settings["audio_bitrate"] == 192000  # 192 kbps
    
    def test_get_quality_settings_pro(self, quality_service):
        """Test getting quality settings for Pro tier."""
        settings = quality_service.get_quality_settings(Tier.PRO)
        
        assert settings["quality"] == "4k"
        assert settings["bitrate"] == 15000000  # 15 Mbps
        assert settings["preset"] == "slow"
        assert settings["crf"] == 16
        assert settings["audio_bitrate"] == 256000  # 256 kbps
    
    def test_get_quality_settings_plus(self, quality_service):
        """Test getting quality settings for Plus tier."""
        settings = quality_service.get_quality_settings(Tier.PLUS)
        
        assert settings["quality"] == "4k+hdr"
        assert settings["bitrate"] == 25000000  # 25 Mbps
        assert settings["preset"] == "veryslow"
        assert settings["crf"] == 12
        assert settings["audio_bitrate"] == 320000  # 320 kbps
    
    def test_get_quality_settings_enterprise(self, quality_service):
        """Test getting quality settings for Enterprise tier."""
        settings = quality_service.get_quality_settings(Tier.ENTERPRISE)
        
        assert settings["quality"] == "4k+hdr"
        assert settings["bitrate"] == 25000000  # 25 Mbps
        assert settings["preset"] == "veryslow"
        assert settings["crf"] == 12
        assert settings["audio_bitrate"] == 320000  # 320 kbps
    
    def test_get_ffmpeg_command_free(self, quality_service, temp_video_path):
        """Test getting FFmpeg command for Free tier."""
        output_path = temp_video_path.replace(".mp4", "_processed.mp4")
        command = quality_service.get_ffmpeg_command(
            input_path=temp_video_path,
            output_path=output_path,
            tier=Tier.FREE
        )
        
        assert "ffmpeg" in command[0]
        assert "-i" in command
        assert temp_video_path in command
        assert output_path in command
        assert "-crf" in command
        assert "28" in command  # Free tier CRF
        assert "-preset" in command
        assert "ultrafast" in command
    
    def test_get_ffmpeg_command_plus(self, quality_service, temp_video_path):
        """Test getting FFmpeg command for Plus tier."""
        output_path = temp_video_path.replace(".mp4", "_processed.mp4")
        command = quality_service.get_ffmpeg_command(
            input_path=temp_video_path,
            output_path=output_path,
            tier=Tier.PLUS
        )
        
        assert "ffmpeg" in command[0]
        assert "-i" in command
        assert temp_video_path in command
        assert output_path in command
        assert "-crf" in command
        assert "12" in command  # Plus tier CRF
        assert "-preset" in command
        assert "veryslow" in command
    
    def test_process_video_success(self, quality_service, temp_video_path):
        """Test successful video processing."""
        with patch.object(quality_service.ffmpeg, 'process_video') as mock_process:
            with patch('os.path.getsize', return_value=1024 * 1024):  # 1MB
                mock_process.return_value = temp_video_path
                
                result = quality_service.process_video(
                    input_path=temp_video_path,
                    quality="720p",
                    tier=Tier.FREE
                )
        
        assert "path" in result
        assert "size" in result
        assert "quality" in result
        assert "tier" in result
        assert result["quality"] == "720p"
        assert result["tier"] == Tier.FREE.value
        assert result["size"] == 1024 * 1024
    
    def test_process_video_ffmpeg_error(self, quality_service, temp_video_path):
        """Test video processing with FFmpeg error."""
        with patch.object(quality_service.ffmpeg, 'process_video', 
                         side_effect=Exception("FFmpeg error")):
            with pytest.raises(ProcessingError):
                quality_service.process_video(
                    input_path=temp_video_path,
                    quality="720p",
                    tier=Tier.FREE
                )
    
    def test_process_video_file_not_found(self, quality_service):
        """Test video processing with non-existent file."""
        with pytest.raises(ProcessingError):
            quality_service.process_video(
                input_path="/non/existent/video.mp4",
                quality="720p",
                tier=Tier.FREE
            )
    
    def test_get_default_quality(self, quality_service):
        """Test getting default quality for tier."""
        # Free tier: 720p
        quality = quality_service.get_default_quality(Tier.FREE)
        assert quality == "720p"
        
        # Starter tier: 1080p
        quality = quality_service.get_default_quality(Tier.STARTER)
        assert quality == "1080p"
        
        # Pro tier: 4k
        quality = quality_service.get_default_quality(Tier.PRO)
        assert quality == "4k"
        
        # Plus tier: 4k+hdr
        quality = quality_service.get_default_quality(Tier.PLUS)
        assert quality == "4k+hdr"
        
        # Enterprise tier: 4k+hdr
        quality = quality_service.get_default_quality(Tier.ENTERPRISE)
        assert quality == "4k+hdr"
    
    def test_validate_quality_for_tier(self, quality_service):
        """Test validating quality for tier."""
        # Free tier can use 720p
        is_valid, message = quality_service.validate_quality_for_tier("720p", Tier.FREE)
        assert is_valid is True
        assert message == ""
        
        # Free tier cannot use 4k
        is_valid, message = quality_service.validate_quality_for_tier("4k", Tier.FREE)
        assert is_valid is False
        assert "Free tier" in message
        
        # Pro tier can use 4k
        is_valid, message = quality_service.validate_quality_for_tier("4k", Tier.PRO)
        assert is_valid is True
        assert message == ""
        
        # Pro tier can use 1080p (downgrade allowed)
        is_valid, message = quality_service.validate_quality_for_tier("1080p", Tier.PRO)
        assert is_valid is True
        assert message == ""
    
    def test_get_available_qualities(self, quality_service):
        """Test getting available qualities for tier."""
        # Free tier: only 720p
        qualities = quality_service.get_available_qualities(Tier.FREE)
        assert len(qualities) == 1
        assert "720p" in qualities
        
        # Starter tier: 720p, 1080p
        qualities = quality_service.get_available_qualities(Tier.STARTER)
        assert len(qualities) == 2
        assert "720p" in qualities
        assert "1080p" in qualities
        
        # Pro tier: 720p, 1080p, 4k
        qualities = quality_service.get_available_qualities(Tier.PRO)
        assert len(qualities) == 3
        assert "720p" in qualities
        assert "1080p" in qualities
        assert "4k" in qualities
        
        # Plus tier: all qualities
        qualities = quality_service.get_available_qualities(Tier.PLUS)
        assert len(qualities) == 4
        assert "720p" in qualities
        assert "1080p" in qualities
        assert "4k" in qualities
        assert "4k+hdr" in qualities
    
    def test_get_quality_comparison(self, quality_service):
        """Test getting quality comparison between tiers."""
        comparison = quality_service.get_quality_comparison()
        
        assert "tiers" in comparison
        assert "qualities" in comparison
        assert "bitrates" in comparison
        
        # Check all tiers are included
        for tier in [Tier.FREE, Tier.STARTER, Tier.PRO, Tier.PLUS, Tier.ENTERPRISE]:
            assert tier.value in comparison["tiers"]
        
        # Check all qualities are included
        for quality in ["720p", "1080p", "4k", "4k+hdr"]:
            assert quality in comparison["qualities"]
    
    def test_estimate_output_size(self, quality_service):
        """Test estimating output file size."""
        # 1-minute video at 720p (2 Mbps)
        size = quality_service.estimate_output_size(
            duration_seconds=60,
            quality="720p"
        )
        
        # 2 Mbps * 60 seconds = 120 Mb = 15 MB
        expected_size = (2000000 * 60) / 8  # Convert bits to bytes
        assert abs(size - expected_size) < expected_size * 0.1  # Within 10%
    
    def test_estimate_output_size_with_audio(self, quality_service):
        """Test estimating output file size with audio."""
        # 1-minute video at 1080p (5 Mbps video + 192 kbps audio)
        size = quality_service.estimate_output_size(
            duration_seconds=60,
            quality="1080p",
            include_audio=True
        )
        
        # 5 Mbps video + 0.192 Mbps audio = 5.192 Mbps
        # 5.192 Mbps * 60 seconds = 311.52 Mb = ~38.94 MB
        video_bitrate = 5000000
        audio_bitrate = 192000
        total_bitrate = video_bitrate + audio_bitrate
        expected_size = (total_bitrate * 60) / 8  # Convert bits to bytes
        assert abs(size - expected_size) < expected_size * 0.1  # Within 10%
    
    def test_get_quality_improvement(self, quality_service):
        """Test getting quality improvement percentage."""
        # 720p to 1080p
        improvement = quality_service.get_quality_improvement("720p", "1080p")
        assert improvement > 0  # Should be positive improvement
        
        # 1080p to 4k
        improvement = quality_service.get_quality_improvement("1080p", "4k")
        assert improvement > 0
        
        # Same quality
        improvement = quality_service.get_quality_improvement("720p", "720p")
        assert improvement == 0
        
        # Downgrade
        improvement = quality_service.get_quality_improvement("4k", "720p")
        assert improvement < 0  # Negative improvement (downgrade)