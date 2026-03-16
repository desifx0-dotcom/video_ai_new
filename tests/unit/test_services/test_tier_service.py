"""
Unit tests for TierService.
"""
import pytest
from unittest.mock import Mock, patch

from src.services.tier_service import TierService
from src.core.domain.value_objects.tier import Tier, TierSpec
from src.core.exceptions import ValidationError

class TestTierService:
    """Test TierService class."""
    
    @pytest.fixture
    def tier_service(self):
        """Create TierService instance."""
        return TierService()
    
    def test_get_tier_spec_free(self, tier_service):
        """Test getting Free tier specification."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        
        assert spec.name == Tier.FREE
        assert spec.price_monthly == 0
        assert spec.videos_per_month == 3
        assert spec.max_video_length == 180  # 3 minutes
        assert spec.max_quality == "720p"
        assert spec.ai_thumbnails_count == 1
        assert spec.ai_thumbnail_steps == 20
        assert spec.priority == 1
    
    def test_get_tier_spec_starter(self, tier_service):
        """Test getting Starter tier specification."""
        spec = tier_service.get_tier_spec(Tier.STARTER)
        
        assert spec.name == Tier.STARTER
        assert spec.price_monthly == 24
        assert spec.videos_per_month == 50
        assert spec.max_video_length == 1800  # 30 minutes
        assert spec.max_quality == "1080p"
        assert spec.ai_thumbnails_count == 3
        assert spec.ai_thumbnail_steps == 30
        assert spec.priority == 3
    
    def test_get_tier_spec_pro(self, tier_service):
        """Test getting Pro tier specification."""
        spec = tier_service.get_tier_spec(Tier.PRO)
        
        assert spec.name == Tier.PRO
        assert spec.price_monthly == 79
        assert spec.videos_per_month == 100
        assert spec.max_video_length == 3600  # 60 minutes
        assert spec.max_quality == "4k"
        assert spec.ai_thumbnails_count == 5
        assert spec.ai_thumbnail_steps == 40
        assert spec.priority == 5
    
    def test_get_tier_spec_plus(self, tier_service):
        """Test getting Plus tier specification."""
        spec = tier_service.get_tier_spec(Tier.PLUS)
        
        assert spec.name == Tier.PLUS
        assert spec.price_monthly == 250
        assert spec.videos_per_month == 500
        assert spec.max_video_length == 7200  # 120 minutes
        assert spec.max_quality == "4k+hdr"
        assert spec.ai_thumbnails_count == 10
        assert spec.ai_thumbnail_steps == 50
        assert spec.priority == 10
    
    def test_get_tier_spec_enterprise(self, tier_service):
        """Test getting Enterprise tier specification."""
        spec = tier_service.get_tier_spec(Tier.ENTERPRISE)
        
        assert spec.name == Tier.ENTERPRISE
        assert spec.price_monthly >= 999
        assert spec.videos_per_month is None  # Unlimited
        assert spec.max_video_length > 7200
        assert spec.max_quality == "4k+hdr"
        assert spec.ai_thumbnails_count >= 10
        assert spec.priority == 10
    
    def test_get_tier_spec_invalid(self, tier_service):
        """Test getting invalid tier specification."""
        with pytest.raises(ValidationError):
            tier_service.get_tier_spec("invalid_tier")
    
    def test_get_all_tiers(self, tier_service):
        """Test getting all tier specifications."""
        tiers = tier_service.get_all_tiers()
        
        assert len(tiers) == 5
        assert Tier.FREE in tiers
        assert Tier.STARTER in tiers
        assert Tier.PRO in tiers
        assert Tier.PLUS in tiers
        assert Tier.ENTERPRISE in tiers
        
        # Verify each tier has correct spec
        for tier_name, spec in tiers.items():
            assert isinstance(spec, TierSpec)
            assert spec.name == tier_name
    
    def test_can_process_video_free_success(self, tier_service):
        """Test Free tier can process video within limits."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        
        # Within limits: 2 minutes video, 0 processed this month
        can_process = spec.can_process_video(
            video_length=120,  # 2 minutes
            videos_processed_this_month=0
        )
        
        assert can_process is True
    
    def test_can_process_video_free_exceeds_length(self, tier_service):
        """Test Free tier cannot process video exceeding length limit."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        
        # Exceeds length: 4 minutes video
        can_process = spec.can_process_video(
            video_length=240,  # 4 minutes
            videos_processed_this_month=0
        )
        
        assert can_process is False
    
    def test_can_process_video_free_exceeds_monthly(self, tier_service):
        """Test Free tier cannot process video exceeding monthly limit."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        
        # Exceeds monthly: already processed 3 videos
        can_process = spec.can_process_video(
            video_length=60,  # 1 minute
            videos_processed_this_month=3
        )
        
        assert can_process is False
    
    def test_can_process_video_enterprise_unlimited(self, tier_service):
        """Test Enterprise tier can process any video (unlimited)."""
        spec = tier_service.get_tier_spec(Tier.ENTERPRISE)
        
        # Enterprise should allow any video
        can_process = spec.can_process_video(
            video_length=10000,  # Very long video
            videos_processed_this_month=1000  # Many videos
        )
        
        assert can_process is True
    
    def test_get_quality_preset(self, tier_service):
        """Test getting quality preset for tier."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        preset = spec.get_quality_preset()
        
        assert 'crf' in preset
        assert 'preset' in preset
        assert preset['preset'] == 'ultrafast'  # Free tier uses ultrafast
    
    def test_get_video_bitrate(self, tier_service):
        """Test getting video bitrate for tier."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        bitrate = spec.get_video_bitrate()
        
        assert bitrate == 2000000  # 720p = 2 Mbps
    
    def test_get_ai_model_cost(self, tier_service):
        """Test getting AI model cost for tier."""
        spec = tier_service.get_tier_spec(Tier.FREE)
        
        # Test transcription cost
        transcription_cost = spec.get_ai_model_cost('transcription')
        assert transcription_cost > 0
        
        # Test thumbnail cost (Free tier uses 20 steps)
        thumbnail_cost = spec.get_ai_model_cost('thumbnail')
        assert thumbnail_cost > 0
        
        # Test unknown service
        unknown_cost = spec.get_ai_model_cost('unknown')
        assert unknown_cost == 0.0
    
    def test_get_yearly_savings(self, tier_service):
        """Test calculating yearly savings."""
        spec = tier_service.get_tier_spec(Tier.STARTER)
        savings = spec.get_yearly_savings()
        
        # Starter: $24/month = $288/year, $240/year = 16.67% savings
        assert savings == 20.0  # 20% discount as defined in constants
    
    def test_get_retention_days(self, tier_service):
        """Test getting retention days for tier."""
        # Free tier: 1 day
        days = tier_service.get_retention_days(Tier.FREE)
        assert days == 1
        
        # Starter tier: 7 days
        days = tier_service.get_retention_days(Tier.STARTER)
        assert days == 7
        
        # Pro tier: 30 days
        days = tier_service.get_retention_days(Tier.PRO)
        assert days == 30
        
        # Plus tier: 90 days
        days = tier_service.get_retention_days(Tier.PLUS)
        assert days == 90
        
        # Enterprise tier: 365 days
        days = tier_service.get_retention_days(Tier.ENTERPRISE)
        assert days == 365
    
    def test_get_default_quality(self, tier_service):
        """Test getting default quality for tier."""
        # Free tier: 720p
        quality = tier_service.get_default_quality(Tier.FREE)
        assert quality == "720p"
        
        # Starter tier: 1080p
        quality = tier_service.get_default_quality(Tier.STARTER)
        assert quality == "1080p"
        
        # Pro tier: 4k
        quality = tier_service.get_default_quality(Tier.PRO)
        assert quality == "4k"
        
        # Plus tier: 4k+hdr
        quality = tier_service.get_default_quality(Tier.PLUS)
        assert quality == "4k+hdr"
        
        # Enterprise tier: 4k+hdr
        quality = tier_service.get_default_quality(Tier.ENTERPRISE)
        assert quality == "4k+hdr"
    
    def test_is_tier_available(self, tier_service):
        """Test checking if tier is available."""
        # All tiers should be available
        assert tier_service.is_tier_available(Tier.FREE) is True
        assert tier_service.is_tier_available(Tier.STARTER) is True
        assert tier_service.is_tier_available(Tier.PRO) is True
        assert tier_service.is_tier_available(Tier.PLUS) is True
        assert tier_service.is_tier_available(Tier.ENTERPRISE) is True
        
        # Invalid tier should not be available
        assert tier_service.is_tier_available("invalid") is False
    
    def test_get_upgrade_options(self, tier_service):
        """Test getting upgrade options for a tier."""
        # Free tier can upgrade to Starter, Pro, Plus, Enterprise
        options = tier_service.get_upgrade_options(Tier.FREE)
        assert Tier.STARTER in options
        assert Tier.PRO in options
        assert Tier.PLUS in options
        assert Tier.ENTERPRISE in options
        assert Tier.FREE not in options  # Can't "upgrade" to same tier
        
        # Starter tier can upgrade to Pro, Plus, Enterprise
        options = tier_service.get_upgrade_options(Tier.STARTER)
        assert Tier.PRO in options
        assert Tier.PLUS in options
        assert Tier.ENTERPRISE in options
        assert Tier.FREE not in options
        assert Tier.STARTER not in options
        
        # Enterprise tier has no upgrade options
        options = tier_service.get_upgrade_options(Tier.ENTERPRISE)
        assert len(options) == 0
    
    def test_compare_tiers(self, tier_service):
        """Test comparing two tiers."""
        comparison = tier_service.compare_tiers(Tier.FREE, Tier.STARTER)
        
        assert "from" in comparison
        assert "to" in comparison
        assert "improvements" in comparison
        assert comparison["from"]["tier"] == Tier.FREE
        assert comparison["to"]["tier"] == Tier.STARTER
        assert "videos_increase" in comparison["improvements"]
        assert "quality_upgrade" in comparison["improvements"]
        assert "retention_increase" in comparison["improvements"]
    
    def test_get_pricing_info(self, tier_service):
        """Test getting pricing information for tier."""
        pricing = tier_service.get_pricing_info(Tier.STARTER)
        
        assert "monthly" in pricing
        assert "yearly" in pricing
        assert "savings_percentage" in pricing
        assert pricing["monthly"] == 24
        assert pricing["yearly"] == 230.4  # $24 * 12 * 0.8 (20% discount)
        assert pricing["savings_percentage"] == 20.0