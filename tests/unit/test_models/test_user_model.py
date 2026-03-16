"""
Unit tests for User model.
"""
import pytest
from datetime import datetime, timedelta

from src.core.domain.entities.user import User, Tier, UserStatus

class TestUserModel:
    """Test User model."""
    
    def test_user_creation(self):
        """Test user creation with default values."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass"
        )
        
        assert user.id == "test-123"
        assert user.email == "test@example.com"
        assert user.hashed_password == "hashed_pass"
        assert user.tier == Tier.FREE
        assert user.status == UserStatus.ACTIVE
        assert user.credits_remaining == 0
        assert user.videos_processed_this_month == 0
        assert user.monthly_video_limit == 3
        assert user.is_active() is True
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)
    
    def test_user_is_active(self):
        """Test user active status."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass"
        )
        
        # Default status is ACTIVE
        assert user.is_active() is True
        
        # INACTIVE status
        user.status = UserStatus.INACTIVE
        assert user.is_active() is False
        
        # SUSPENDED status
        user.status = UserStatus.SUSPENDED
        assert user.is_active() is False
        
        # BANNED status
        user.status = UserStatus.BANNED
        assert user.is_active() is False
    
    def test_has_sufficient_credits_free_tier(self):
        """Test credit checking for Free tier."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            credits_remaining=5
        )
        
        # 3-minute video needs 3 credits
        assert user.has_sufficient_credits(180) is True
        
        # 10-minute video needs 10 credits
        assert user.has_sufficient_credits(600) is False
    
    def test_has_sufficient_credits_unlimited_tier(self):
        """Test credit checking for unlimited tiers."""
        # Plus tier has unlimited credits
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.PLUS,
            credits_remaining=0  # Even with 0 credits, unlimited tier should pass
        )
        
        assert user.has_sufficient_credits(10000) is True
        
        # Enterprise tier also has unlimited credits
        user.tier = Tier.ENTERPRISE
        assert user.has_sufficient_credits(10000) is True
    
    def test_can_process_video_success(self):
        """Test successful video processing check."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            credits_remaining=5,
            videos_processed_this_month=0
        )
        
        can_process, reason = user.can_process_video(120)  # 2-minute video
        
        assert can_process is True
        assert reason == ""
    
    def test_can_process_video_inactive_account(self):
        """Test video processing check with inactive account."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            status=UserStatus.SUSPENDED
        )
        
        can_process, reason = user.can_process_video(60)
        
        assert can_process is False
        assert "Account is not active" in reason
    
    def test_can_process_video_monthly_limit(self):
        """Test video processing check with monthly limit reached."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            videos_processed_this_month=3  # At limit
        )
        
        can_process, reason = user.can_process_video(60)
        
        assert can_process is False
        assert "Monthly video limit reached" in reason
    
    def test_can_process_video_length_limit(self):
        """Test video processing check with length limit exceeded."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE
        )
        
        can_process, reason = user.can_process_video(240)  # 4 minutes > 3 minute limit
        
        assert can_process is False
        assert "exceeds maximum length" in reason
    
    def test_can_process_video_insufficient_credits(self):
        """Test video processing check with insufficient credits."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            credits_remaining=0
        )
        
        can_process, reason = user.can_process_video(120)
        
        assert can_process is False
        assert "Insufficient credits" in reason
    
    def test_get_max_video_length(self):
        """Test getting maximum video length per tier."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass"
        )
        
        # Free tier: 3 minutes
        user.tier = Tier.FREE
        assert user.get_max_video_length() == 180
        
        # Starter tier: 30 minutes
        user.tier = Tier.STARTER
        assert user.get_max_video_length() == 1800
        
        # Pro tier: 60 minutes
        user.tier = Tier.PRO
        assert user.get_max_video_length() == 3600
        
        # Plus tier: 120 minutes
        user.tier = Tier.PLUS
        assert user.get_max_video_length() == 7200
        
        # Enterprise tier: 300 minutes
        user.tier = Tier.ENTERPRISE
        assert user.get_max_video_length() == 18000
    
    def test_record_video_processing_free_tier(self):
        """Test recording video processing for Free tier."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            credits_remaining=10,
            videos_processed_this_month=0,
            total_videos_processed=0,
            total_processing_time=0.0
        )
        
        user.record_video_processing(180, 0.05)  # 3-minute video
        
        assert user.videos_processed_this_month == 1
        assert user.total_videos_processed == 1
        assert user.total_processing_time == 180
        assert user.credits_remaining == 7  # 10 - 3 = 7
        assert isinstance(user.updated_at, datetime)
    
    def test_record_video_processing_unlimited_tier(self):
        """Test recording video processing for unlimited tier."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.PLUS,
            credits_remaining=10,
            videos_processed_this_month=0
        )
        
        user.record_video_processing(180, 0.05)
        
        assert user.videos_processed_this_month == 1
        assert user.credits_remaining == 10  # Credits not deducted for unlimited tier
    
    def test_upgrade_tier(self):
        """Test upgrading user tier."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            monthly_video_limit=3
        )
        
        user.upgrade_tier(Tier.PRO)
        
        assert user.tier == Tier.PRO
        assert user.monthly_video_limit == 100  # Pro tier limit
        assert isinstance(user.updated_at, datetime)
    
    def test_to_dict(self):
        """Test converting user to dictionary."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE,
            credits_remaining=5,
            videos_processed_this_month=2,
            monthly_video_limit=3,
            total_videos_processed=10,
            is_admin=True,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            last_login=datetime(2024, 1, 2, 14, 0, 0)
        )
        
        user_dict = user.to_dict()
        
        assert user_dict["id"] == "test-123"
        assert user_dict["email"] == "test@example.com"
        assert user_dict["tier"] == "free"
        assert user_dict["credits_remaining"] == 5
        assert user_dict["videos_processed_this_month"] == 2
        assert user_dict["monthly_video_limit"] == 3
        assert user_dict["total_videos_processed"] == 10
        assert user_dict["is_admin"] is True
        assert user_dict["created_at"] == "2024-01-01T12:00:00"
        assert user_dict["last_login"] == "2024-01-02T14:00:00"
        assert user_dict["email_verified"] is False
    
    def test_get_quality_settings(self):
        """Test getting quality settings for user tier."""
        user = User(
            id="test-123",
            email="test@example.com",
            hashed_password="hashed_pass",
            tier=Tier.FREE
        )
        
        # Mock the settings module
        with pytest.MonkeyPatch().context() as m:
            m.setattr('src.core.domain.entities.user.settings', {
                'tiers': {
                    'free': {
                        'quality': {
                            'preset': 'ultrafast',
                            'bitrate': 2000000
                        }
                    }
                }
            })
            
            settings = user.get_quality_settings()
            
            assert settings["preset"] == "ultrafast"
            assert settings["bitrate"] == 2000000