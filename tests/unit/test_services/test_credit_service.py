"""
Unit tests for CreditService.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.services.credit_service import CreditService
from src.core.domain.entities.user import User, Tier
from src.core.exceptions import ValidationError, InsufficientCreditsError

class TestCreditService:
    """Test CreditService class."""
    
    @pytest.fixture
    def credit_service(self):
        """Create CreditService instance."""
        return CreditService()
    
    @pytest.fixture
    def test_user(self):
        """Create a test user."""
        return User(
            id="test-user-123",
            email="test@example.com",
            hashed_password="hashed_password",
            tier=Tier.FREE,
            credits_remaining=10,
            videos_processed_this_month=0,
            monthly_video_limit=3
        )
    
    def test_calculate_credits_needed(self, credit_service):
        """Test calculating credits needed for video."""
        # 30 seconds = 1 credit (minimum)
        credits = credit_service.calculate_credits_needed(30)
        assert credits == 1
        
        # 60 seconds = 1 credit
        credits = credit_service.calculate_credits_needed(60)
        assert credits == 1
        
        # 90 seconds = 2 credits
        credits = credit_service.calculate_credits_needed(90)
        assert credits == 2
        
        # 300 seconds (5 minutes) = 5 credits
        credits = credit_service.calculate_credits_needed(300)
        assert credits == 5
    
    def test_calculate_credits_needed_invalid(self, credit_service):
        """Test calculating credits for invalid duration."""
        with pytest.raises(ValidationError):
            credit_service.calculate_credits_needed(0)
        
        with pytest.raises(ValidationError):
            credit_service.calculate_credits_needed(-10)
    
    def test_has_sufficient_credits_free_tier(self, credit_service, test_user):
        """Test checking sufficient credits for Free tier."""
        test_user.tier = Tier.FREE
        test_user.credits_remaining = 5
        
        # User has 5 credits, needs 3 for 3-minute video
        has_credits = credit_service.has_sufficient_credits(test_user, 180)
        assert has_credits is True
        
        # User has 5 credits, needs 10 for 10-minute video
        has_credits = credit_service.has_sufficient_credits(test_user, 600)
        assert has_credits is False
    
    def test_has_sufficient_credits_unlimited_tier(self, credit_service, test_user):
        """Test checking credits for unlimited tiers."""
        # Plus tier has unlimited credits
        test_user.tier = Tier.PLUS
        
        has_credits = credit_service.has_sufficient_credits(test_user, 10000)
        assert has_credits is True
        
        # Enterprise tier also has unlimited credits
        test_user.tier = Tier.ENTERPRISE
        
        has_credits = credit_service.has_sufficient_credits(test_user, 10000)
        assert has_credits is True
    
    def test_deduct_credits_success(self, credit_service, test_user):
        """Test successfully deducting credits."""
        initial_credits = test_user.credits_remaining
        
        credit_service.deduct_credits(test_user, 3)
        
        assert test_user.credits_remaining == initial_credits - 3
        assert test_user.updated_at is not None
    
    def test_deduct_credits_insufficient(self, credit_service, test_user):
        """Test deducting credits with insufficient balance."""
        test_user.credits_remaining = 2
        
        with pytest.raises(InsufficientCreditsError):
            credit_service.deduct_credits(test_user, 5)
        
        # Credits should not change
        assert test_user.credits_remaining == 2
    
    def test_deduct_credits_unlimited_tier(self, credit_service, test_user):
        """Test deducting credits from unlimited tier (should not deduct)."""
        test_user.tier = Tier.PLUS
        initial_credits = test_user.credits_remaining
        
        credit_service.deduct_credits(test_user, 100)
        
        # Credits should not change for unlimited tiers
        assert test_user.credits_remaining == initial_credits
    
    def test_add_credits(self, credit_service, test_user):
        """Test adding credits to user."""
        initial_credits = test_user.credits_remaining
        
        credit_service.add_credits(test_user, 50)
        
        assert test_user.credits_remaining == initial_credits + 50
        assert test_user.updated_at is not None
    
    def test_add_credits_invalid(self, credit_service, test_user):
        """Test adding invalid amount of credits."""
        with pytest.raises(ValidationError):
            credit_service.add_credits(test_user, 0)
        
        with pytest.raises(ValidationError):
            credit_service.add_credits(test_user, -10)
    
    def test_reset_monthly_credits_free_tier(self, credit_service, test_user):
        """Test resetting monthly credits for Free tier."""
        test_user.tier = Tier.FREE
        test_user.videos_processed_this_month = 5
        test_user.credits_remaining = 2
        
        credit_service.reset_monthly_credits(test_user)
        
        # Free tier gets 3 credits per month
        assert test_user.credits_remaining == 3
        assert test_user.videos_processed_this_month == 0
    
    def test_reset_monthly_credits_starter_tier(self, credit_service, test_user):
        """Test resetting monthly credits for Starter tier."""
        test_user.tier = Tier.STARTER
        test_user.videos_processed_this_month = 30
        test_user.credits_remaining = 5
        
        credit_service.reset_monthly_credits(test_user)
        
        # Starter tier gets credits based on videos processed
        # 30 videos * 1 credit per minute (average) = 30 credits
        assert test_user.credits_remaining == 30
        assert test_user.videos_processed_this_month == 0
    
    def test_reset_monthly_credits_unlimited_tier(self, credit_service, test_user):
        """Test resetting monthly credits for unlimited tier."""
        test_user.tier = Tier.PLUS
        test_user.videos_processed_this_month = 100
        initial_credits = test_user.credits_remaining
        
        credit_service.reset_monthly_credits(test_user)
        
        # Unlimited tiers don't get reset credits
        assert test_user.credits_remaining == initial_credits
        assert test_user.videos_processed_this_month == 0
    
    def test_get_credit_packages(self, credit_service):
        """Test getting available credit packages."""
        packages = credit_service.get_credit_packages()
        
        assert len(packages) > 0
        for package in packages:
            assert "id" in package
            assert "credits" in package
            assert "price" in package
            assert "description" in package
            assert package["credits"] > 0
            assert package["price"] > 0
    
    def test_calculate_package_value(self, credit_service):
        """Test calculating value of credit package."""
        package = {
            "credits": 100,
            "price": 10.0
        }
        
        value = credit_service.calculate_package_value(package)
        assert value == 0.10  # $0.10 per credit
    
    def test_get_recommended_package_free_tier(self, credit_service, test_user):
        """Test getting recommended package for Free tier."""
        test_user.tier = Tier.FREE
        test_user.credits_remaining = 1
        
        package = credit_service.get_recommended_package(test_user)
        
        # Free tier with low credits should recommend small package
        assert package is not None
        assert package["credits"] <= 50  # Small package
    
    def test_get_recommended_package_pro_tier(self, credit_service, test_user):
        """Test getting recommended package for Pro tier."""
        test_user.tier = Tier.PRO
        test_user.credits_remaining = 10
        test_user.videos_processed_this_month = 50
        
        package = credit_service.get_recommended_package(test_user)
        
        # Pro tier with moderate usage should recommend medium package
        assert package is not None
        assert package["credits"] >= 100  # Medium to large package
    
    def test_create_credit_transaction(self, credit_service, test_user):
        """Test creating credit transaction."""
        with patch.object(credit_service.db, 'save') as mock_save:
            transaction = credit_service.create_credit_transaction(
                user_id=test_user.id,
                amount=50,
                description="Purchased credits",
                video_id=None
            )
        
        assert transaction["user_id"] == test_user.id
        assert transaction["amount"] == 50
        assert transaction["description"] == "Purchased credits"
        assert "created_at" in transaction
    
    def test_get_user_transactions(self, credit_service, test_user):
        """Test getting user's credit transactions."""
        mock_transactions = [
            {
                "id": "txn-1",
                "user_id": test_user.id,
                "amount": 50,
                "description": "Credit purchase",
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "id": "txn-2",
                "user_id": test_user.id,
                "amount": -3,
                "description": "Video processing",
                "video_id": "video-123",
                "created_at": datetime.utcnow().isoformat()
            }
        ]
        
        with patch.object(credit_service.db, 'query', return_value=mock_transactions):
            transactions = credit_service.get_user_transactions(
                user_id=test_user.id,
                limit=10,
                offset=0
            )
        
        assert len(transactions) == 2
        assert transactions[0]["amount"] == 50
        assert transactions[1]["amount"] == -3
    
    def test_get_credit_balance(self, credit_service, test_user):
        """Test getting user's credit balance."""
        balance = credit_service.get_credit_balance(test_user)
        
        assert "current" in balance
        assert "monthly_usage" in balance
        assert "recommended_package" in balance
        assert balance["current"] == test_user.credits_remaining
        assert balance["monthly_usage"] == test_user.videos_processed_this_month
    
    def test_validate_credit_purchase(self, credit_service, test_user):
        """Test validating credit purchase."""
        # Valid purchase
        is_valid, message = credit_service.validate_credit_purchase(
            user=test_user,
            package_id="package-50",
            payment_method="stripe"
        )
        
        assert is_valid is True
        assert message == ""
    
    def test_validate_credit_purchase_invalid_user(self, credit_service):
        """Test validating credit purchase for invalid user."""
        is_valid, message = credit_service.validate_credit_purchase(
            user=None,
            package_id="package-50",
            payment_method="stripe"
        )
        
        assert is_valid is False
        assert "User not found" in message
    
    def test_process_credit_purchase(self, credit_service, test_user):
        """Test processing credit purchase."""
        package = {
            "id": "package-100",
            "credits": 100,
            "price": 10.0,
            "description": "100 credits"
        }
        
        with patch.object(credit_service, 'get_credit_packages', return_value=[package]):
            with patch.object(credit_service, 'add_credits'):
                with patch.object(credit_service, 'create_credit_transaction'):
                    result = credit_service.process_credit_purchase(
                        user=test_user,
                        package_id="package-100",
                        payment_id="pay_123",
                        payment_method="stripe"
                    )
        
        assert "success" in result
        assert "credits_added" in result
        assert "new_balance" in result
        assert result["success"] is True
        assert result["credits_added"] == 100
    
    def test_process_credit_purchase_invalid_package(self, credit_service, test_user):
        """Test processing credit purchase with invalid package."""
        with patch.object(credit_service, 'get_credit_packages', return_value=[]):
            result = credit_service.process_credit_purchase(
                user=test_user,
                package_id="invalid-package",
                payment_id="pay_123",
                payment_method="stripe"
            )
        
        assert result["success"] is False
        assert "Credit package not found" in result["message"]