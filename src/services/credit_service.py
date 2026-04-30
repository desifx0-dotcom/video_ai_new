"""
Credit management service with tier-based credits and transaction tracking.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from core.domain.entities.user import User
from core.exceptions import InsufficientCreditsError
from providers.firebase_provider import FirebaseProvider

logger = logging.getLogger(__name__)


class CreditOperation(str, Enum):
    """Types of credit operations."""

    TRANSCRIPTION = "transcription"
    TITLE_GENERATION = "title_generation"
    DESCRIPTION_GENERATION = "description_generation"
    TAGS_GENERATION = "tags_generation"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    AI_THUMBNAIL = "ai_thumbnail"
    REGENERATION = "regeneration"
    TRANSLATION = "translation"
    STYLE_APPLICATION = "style_application"
    REFUND = "refund"
    BONUS = "bonus"
    PURCHASE = "purchase"
    VIDEO_PROCESSING = "video_processing"


class CreditService:
    """Credit management service with tier-based allocations."""

    # Base credit costs per operation
    CREDIT_COSTS = {
        CreditOperation.TRANSCRIPTION: 1,
        CreditOperation.TITLE_GENERATION: 1,
        CreditOperation.DESCRIPTION_GENERATION: 1,
        CreditOperation.TAGS_GENERATION: 1,
        CreditOperation.THUMBNAIL_GENERATION: 2,
        CreditOperation.AI_THUMBNAIL: 2,
        CreditOperation.REGENERATION: 2,
        CreditOperation.TRANSLATION: 1,
        CreditOperation.STYLE_APPLICATION: 3,
        CreditOperation.VIDEO_PROCESSING: 1,
    }
    # Monthly credits per tier
    MONTHLY_CREDITS = {
        "free": 3,
        "starter": 30,
        "pro": 75,
        "plus": 250,
        "enterprise": 10000,  # Effectively unlimited
    }

    def __init__(self):
        self.db = FirebaseProvider()
        self._user_cache = {}

    def get_credits(self, user_id: str) -> int:
        """Get current credit balance for user."""
        try:
            user_data = self.db.get("users", user_id)
            if user_data:
                return user_data.get("credits_remaining", 0)
            return 0
        except Exception as e:
            logger.error(f"Failed to get credits for {user_id}: {e}")
            return 0

    def get_monthly_credits(self, tier: str) -> int:
        """Get monthly credit allocation for tier."""
        return self.MONTHLY_CREDITS.get(tier, 3)

    def can_process(self, user_id: str, operation: str) -> bool:
        """Check if user has enough credits for operation."""
        credits = self.get_credits(user_id)
        cost = self.CREDIT_COSTS.get(CreditOperation(operation), 1)
        return credits >= cost

    def use_credits(
        self,
        user_id: str,
        amount: int,
        description: str,
        video_id: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> bool:
        """Use credits from user account with transaction record."""
        try:
            # Get current user data
            user_data = self.db.get("users", user_id)
            if not user_data:
                logger.error(f"User not found: {user_id}")
                return False

            current_credits = user_data.get("credits_remaining", 0)

            if current_credits < amount:
                raise InsufficientCreditsError(current_credits, amount)

            # Update credits
            new_credits = current_credits - amount
            user_data["credits_remaining"] = new_credits
            user_data["updated_at"] = datetime.utcnow().isoformat()
            self.db.save("users", user_id, user_data)

            # Record transaction
            transaction_id = str(uuid.uuid4())
            transaction = {
                "id": transaction_id,
                "user_id": user_id,
                "amount": -amount,
                "balance_before": current_credits,
                "balance_after": new_credits,
                "description": description,
                "operation": operation,
                "video_id": video_id,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.db.save("credit_transactions", transaction_id, transaction)

            logger.info(f"Used {amount} credits for user {user_id}: {description}")
            return True

        except InsufficientCreditsError:
            raise
        except Exception as e:
            logger.error(f"Failed to use credits for {user_id}: {e}")
            return False

    def add_credits(
        self,
        user_id: str,
        amount: int,
        description: str,
        operation: Optional[str] = None,
    ) -> bool:
        """Add credits to user account."""
        try:
            user_data = self.db.get("users", user_id)
            if not user_data:
                logger.error(f"User not found: {user_id}")
                return False

            current_credits = user_data.get("credits_remaining", 0)
            new_credits = current_credits + amount

            user_data["credits_remaining"] = new_credits
            user_data["updated_at"] = datetime.utcnow().isoformat()
            self.db.save("users", user_id, user_data)

            # Record transaction
            transaction_id = str(uuid.uuid4())
            transaction = {
                "id": transaction_id,
                "user_id": user_id,
                "amount": amount,
                "balance_before": current_credits,
                "balance_after": new_credits,
                "description": description,
                "operation": operation,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.db.save("credit_transactions", transaction_id, transaction)

            logger.info(f"Added {amount} credits to user {user_id}: {description}")
            return True

        except Exception as e:
            logger.error(f"Failed to add credits to {user_id}: {e}")
            return False

    def allocate_monthly_credits(self, user_id: str, tier: str) -> bool:
        """Allocate monthly credits to user."""
        monthly_credits = self.get_monthly_credits(tier)

        # Check if already allocated this month
        last_allocation_key = f"last_credit_allocation_{user_id}"
        last_allocation = self.db.get("metadata", last_allocation_key)

        now = datetime.utcnow()
        if last_allocation:
            last_date = datetime.fromisoformat(last_allocation.get("date"))
            if (now - last_date).days < 30:
                return False

        # Add credits
        success = self.add_credits(
            user_id,
            monthly_credits,
            f"Monthly credit allocation for {tier} tier",
            operation=CreditOperation.BONUS,
        )

        if success:
            # Update last allocation date
            self.db.save(
                "metadata",
                last_allocation_key,
                {"date": now.isoformat(), "tier": tier, "credits": monthly_credits},
            )
            logger.info(f"Allocated {monthly_credits} monthly credits to {user_id}")

        return success

    def get_transaction_history(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get credit transaction history for user."""
        try:
            transactions = self.db.query(
                "credit_transactions",
                filters={"user_id": user_id},
                order_by="created_at",
                descending=True,
                limit=limit,
                offset=offset,
            )
            return list(transactions) if transactions else []
        except Exception as e:
            logger.error(f"Failed to get transaction history for {user_id}: {e}")
            return []

    def get_operation_cost(self, operation: str) -> int:
        """Get credit cost for operation."""
        return self.CREDIT_COSTS.get(CreditOperation(operation), 1)

    def track_usage(
        self,
        user_id: str,
        operation: str,
        video_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Track usage for analytics."""
        try:
            usage_record = {
                "user_id": user_id,
                "operation": operation,
                "video_id": video_id,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": metadata or {},
            }
            usage_id = str(uuid.uuid4())
            self.db.save("usage_logs", usage_id, usage_record)
        except Exception as e:
            logger.error(f"Failed to track usage: {e}")
