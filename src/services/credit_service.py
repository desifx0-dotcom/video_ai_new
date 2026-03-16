"""
Credit management service.
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

from core.domain.entities.user import Tier
from core.exceptions import ValidationError, InsufficientCreditsError
from providers.firebase_provider import FirebaseProvider

logger = logging.getLogger(__name__)

class CreditService:
    """Credit management service."""
    
    def __init__(self):
        self.db = None  # Temporarily disabled for development
    
    def add_credits(self, user_id: str, amount: int, 
                   description: str = "", source: str = "purchase") -> Dict[str, Any]:
        """
        Add credits to user account.
        
        Args:
            user_id: User ID
            amount: Number of credits to add
            description: Transaction description
            source: Source of credits (purchase, bonus, refund, etc.)
        
        Returns:
            Transaction details
        """
        if amount <= 0:
            raise ValidationError("Amount must be positive", field="amount")
        
        # Get user
        from services.user_service import UserService
        user_service = UserService()
        user = user_service.get_user(user_id)
        if not user:
            raise ValidationError("User not found", field="user_id")
        
        # Update user credits
        user.credits_remaining += amount
        user.updated_at = datetime.utcnow()
        
        self.db.save('users', user_id, user.to_dict())
        
        # Create transaction record
        transaction_id = str(uuid.uuid4())
        transaction = {
            'id': transaction_id,
            'user_id': user_id,
            'amount': amount,
            'description': description,
            'source': source,
            'balance_after': user.credits_remaining,
            'created_at': datetime.utcnow().isoformat()
        }
        
        self.db.save('credit_transactions', transaction_id, transaction)
        
        logger.info(f"Added {amount} credits to user {user_id} ({source})")
        
        return {
            'transaction_id': transaction_id,
            'user_id': user_id,
            'amount': amount,
            'new_balance': user.credits_remaining,
            'description': description,
            'source': source
        }
    
    def use_credits(self, user_id: str, amount: int, 
                   description: str = "", video_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Use credits from user account.
        
        Args:
            user_id: User ID
            amount: Number of credits to use
            description: Transaction description
            video_id: Optional video ID associated with credit usage
        
        Returns:
            Transaction details
        """
        if amount <= 0:
            raise ValidationError("Amount must be positive", field="amount")
        
        # Get user
        from services.user_service import UserService
        user_service = UserService()
        user = user_service.get_user(user_id)
        if not user:
            raise ValidationError("User not found", field="user_id")
        
        # Check if user has sufficient credits
        # Unlimited tiers don't need credits
        if user.tier not in [Tier.PLUS, Tier.ENTERPRISE]:
            if user.credits_remaining < amount:
                raise InsufficientCreditsError(user.credits_remaining, amount)
        
        # Update user credits
        user.credits_remaining = max(0, user.credits_remaining - amount)
        user.updated_at = datetime.utcnow()
        
        self.db.save('users', user_id, user.to_dict())
        
        # Create transaction record
        transaction_id = str(uuid.uuid4())
        transaction = {
            'id': transaction_id,
            'user_id': user_id,
            'amount': -amount,
            'description': description,
            'video_id': video_id,
            'balance_after': user.credits_remaining,
            'created_at': datetime.utcnow().isoformat()
        }
        
        self.db.save('credit_transactions', transaction_id, transaction)
        
        logger.info(f"Used {amount} credits from user {user_id} for {description}")
        
        return {
            'transaction_id': transaction_id,
            'user_id': user_id,
            'amount': amount,
            'new_balance': user.credits_remaining,
            'description': description,
            'video_id': video_id
        }
    
    def calculate_credits_needed(self, video_duration: float, tier: Tier) -> int:
        """
        Calculate credits needed for video processing.
        
        Args:
            video_duration: Video duration in seconds
            tier: User tier
        
        Returns:
            Number of credits needed
        """
        # Unlimited tiers don't need credits
        if tier in [Tier.PLUS, Tier.ENTERPRISE]:
            return 0
        
        # Calculate based on video length (1 credit per minute, minimum 1)
        minutes = max(1, int(video_duration) // 60)
        
        # Apply tier multipliers
        tier_multipliers = {
            Tier.FREE: 1.0,
            Tier.STARTER: 1.0,
            Tier.PRO: 1.0,
            Tier.PLUS: 0.0,  # No credits needed
            Tier.ENTERPRISE: 0.0  # No credits needed
        }
        
        credits = int(minutes * tier_multipliers.get(tier, 1.0))
        return max(1, credits)
    
    def get_user_balance(self, user_id: str) -> Dict[str, Any]:
        """Get user credit balance and transaction history."""
        # Get user
        from services.user_service import UserService
        user_service = UserService()
        user = user_service.get_user(user_id)
        if not user:
            raise ValidationError("User not found", field="user_id")
        
        # Get recent transactions
        transactions = self.db.query(
            'credit_transactions',
            filters={'user_id': user_id},
            order_by='created_at',
            descending=True,
            limit=20
        )
        
        # Calculate monthly usage
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        monthly_usage = self.db.query(
            'credit_transactions',
            filters={
                'user_id': user_id,
                'amount': {'$lt': 0},  # Negative amounts are usage
                'created_at': {'$gte': thirty_days_ago}
            }
        )
        
        monthly_credits_used = abs(sum(tx['amount'] for tx in monthly_usage))
        
        return {
            'user_id': user_id,
            'current_balance': user.credits_remaining,
            'monthly_credits_used': monthly_credits_used,
            'tier': user.tier.value,
            'has_unlimited': user.tier in [Tier.PLUS, Tier.ENTERPRISE],
            'recent_transactions': transactions
        }
    
    def get_transaction_history(self, user_id: str, limit: int = 50, 
                               offset: int = 0) -> List[Dict[str, Any]]:
        """Get credit transaction history for user."""
        transactions = self.db.query(
            'credit_transactions',
            filters={'user_id': user_id},
            order_by='created_at',
            descending=True,
            limit=limit,
            offset=offset
        )
        
        return transactions
    
    def get_purchase_packages(self) -> List[Dict[str, Any]]:
        """Get available credit purchase packages."""
        return [
            {
                'id': 'small',
                'name': 'Small Package',
                'credits': 100,
                'price': 9.99,
                'price_per_credit': 0.0999,
                'description': 'For casual users',
                'best_for': '1-2 videos per month'
            },
            {
                'id': 'medium',
                'name': 'Medium Package',
                'credits': 300,
                'price': 24.99,
                'price_per_credit': 0.0833,
                'description': 'For regular users',
                'best_for': '3-5 videos per month'
            },
            {
                'id': 'large',
                'name': 'Large Package',
                'credits': 1000,
                'price': 79.99,
                'price_per_credit': 0.0799,
                'description': 'For power users',
                'best_for': '10+ videos per month'
            },
            {
                'id': 'pro',
                'name': 'Pro Package',
                'credits': 3000,
                'price': 199.99,
                'price_per_credit': 0.0666,
                'description': 'For professionals',
                'best_for': '30+ videos per month'
            }
        ]
    
    def calculate_cost(self, credits: int, package_id: Optional[str] = None) -> float:
        """
        Calculate cost for purchasing credits.
        
        Args:
            credits: Number of credits
            package_id: Optional package ID for bulk discounts
        
        Returns:
            Cost in USD
        """
        if package_id:
            packages = {pkg['id']: pkg for pkg in self.get_purchase_packages()}
            if package_id in packages:
                return packages[package_id]['price']
        
        # Default pricing
        if credits >= 3000:
            return credits * 0.0666
        elif credits >= 1000:
            return credits * 0.0799
        elif credits >= 300:
            return credits * 0.0833
        else:
            return credits * 0.0999
    
    def refund_credits(self, transaction_id: str, reason: str = "") -> bool:
        """
        Refund credits from a transaction.
        
        Args:
            transaction_id: Original transaction ID
            reason: Refund reason
        
        Returns:
            True if successful
        """
        # Get original transaction
        transaction = self.db.get('credit_transactions', transaction_id)
        if not transaction:
            return False
        
        user_id = transaction['user_id']
        amount = transaction['amount']
        
        # Only refund positive transactions (purchases)
        if amount <= 0:
            return False
        
        # Add refund transaction
        refund_id = str(uuid.uuid4())
        refund_transaction = {
            'id': refund_id,
            'user_id': user_id,
            'amount': -amount,  # Negative to reverse original
            'description': f"Refund: {reason}",
            'refund_of': transaction_id,
            'created_at': datetime.utcnow().isoformat()
        }
        
        self.db.save('credit_transactions', refund_id, refund_transaction)
        
        # Update user balance
        from services.user_service import UserService
        user_service = UserService()
        user = user_service.get_user(user_id)
        if user:
            user.credits_remaining = max(0, user.credits_remaining - amount)
            user.updated_at = datetime.utcnow()
            self.db.save('users', user_id, user.to_dict())
        
        logger.info(f"Refunded {amount} credits to user {user_id} ({reason})")
        
        return True
    
    def get_low_balance_users(self, threshold: int = 10) -> List[Dict[str, Any]]:
        """Get users with low credit balance."""
        # Get all active users
        users = self.db.query('users', filters={'status': 'active'})
        
        low_balance_users = []
        for user_data in users:
            if user_data['tier'] in ['free', 'starter', 'pro']:
                if user_data.get('credits_remaining', 0) <= threshold:
                    low_balance_users.append({
                        'user_id': user_data['id'],
                        'email': user_data['email'],
                        'tier': user_data['tier'],
                        'balance': user_data.get('credits_remaining', 0),
                        'last_login': user_data.get('last_login')
                    })
        
        return low_balance_users
