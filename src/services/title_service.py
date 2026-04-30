"""
Title generation service using AI models with tier-based model selection and regeneration limits.
Complete production version with proper regeneration tracking, credit deduction, and fallback chain.
"""

from typing import Dict, Any, List, Optional
import logging
import json
import re
import random
import hashlib
from datetime import datetime

from core.domain.value_objects.tier import Tier
from core.exceptions import (
    ProcessingError,
    ExternalServiceError,
    TierLimitExceeded,
    InsufficientCreditsError,
)
from providers.google_provider import GoogleProvider
from providers.openai_provider import OpenAIProvider
from services.tier_service import TierService
from services.credit_service import CreditService

logger = logging.getLogger(__name__)


class TitleService:
    """Title generation service with tier-based model selection and fallback chain."""

    # Unique concept templates for true variety
    CONCEPTS = [
        "energetic and exciting",
        "calm and relaxing",
        "mysterious and intriguing",
        "educational and informative",
        "funny and entertaining",
        "inspiring and motivational",
        "controversial and thought-provoking",
        "heartwarming and emotional",
        "action-packed and thrilling",
        "simple and straightforward",
        "clever and witty",
        "professional and authoritative",
        "personal and relatable",
        "urgent and time-sensitive",
        "curiosity-driven",
        "list-style (Top 10, Best Ways, etc.)",
        "question-based",
        "how-to tutorial style",
        "storytelling narrative",
        "behind-the-scenes",
    ]

    MODEL_COSTS = {
        # Gemini models
        "gemini-2.0-flash-lite": 0.00005,
        "gemini-2.0-flash-exp": 0.0001,
        "gemini-2.0-flash": 0.0001,
        "gemini-1.5-pro": 0.0003,
        "gemini-2.0-pro": 0.0003,
        # OpenAI models
        "gpt-4o-mini": 0.00015,
        "gpt-3.5-turbo": 0.0005,
        "gpt-4": 0.03,
        "gpt-4-turbo": 0.01,
    }

    def __init__(self, redis_client=None):
        self.google = GoogleProvider()
        self.openai = OpenAIProvider()
        self.tier_service = TierService(redis_client)
        self.credit_service = CreditService()
        self._redis = redis_client

        # In-memory fallback for development
        self._regeneration_count = {}
        self._used_concepts = {}

    def _get_redis_key(self, video_id: str, suffix: str) -> str:
        """Generate Redis key for tracking."""
        return f"title:{video_id}:{suffix}"

    def _get_regeneration_count(self, video_id: str) -> int:
        """Get regeneration count from Redis or memory."""
        if self._redis:
            key = self._get_redis_key(video_id, "regen_count")
            count = self._redis.get(key)
            return int(count) if count else 0
        return self._regeneration_count.get(video_id, 0)

    def _increment_regeneration_count(self, video_id: str) -> int:
        """Increment regeneration count."""
        if self._redis:
            key = self._get_redis_key(video_id, "regen_count")
            new_count = self._redis.incr(key)
            self._redis.expire(key, 2592000)  # 30 days
            return new_count
        new_count = self._regeneration_count.get(video_id, 0) + 1
        self._regeneration_count[video_id] = new_count
        return new_count

    def _get_used_concepts(self, video_id: str) -> List[str]:
        """Get used concepts from Redis or memory."""
        if self._redis:
            key = self._get_redis_key(video_id, "concepts")
            concepts = self._redis.lrange(key, 0, -1)
            return [c.decode() for c in concepts] if concepts else []
        return self._used_concepts.get(video_id, [])

    def _add_used_concept(self, video_id: str, concept: str):
        """Track used concept in Redis or memory."""
        if self._redis:
            key = self._get_redis_key(video_id, "concepts")
            self._redis.rpush(key, concept)
            self._redis.expire(key, 2592000)
        else:
            if video_id not in self._used_concepts:
                self._used_concepts[video_id] = []
            self._used_concepts[video_id].append(concept)

    def _check_credits(self, user_id: str, operation: str = "title_generation") -> bool:
        """Check if user has enough credits."""
        if not self.credit_service.can_process(user_id, operation):
            raise InsufficientCreditsError(
                f"Insufficient credits for {operation}",
                credits_needed=1,
                credits_remaining=self.credit_service.get_credits(user_id),
            )
        return True

    def generate_metadata(
        self,
        transcript: str,
        video_id: str,
        user_id: Optional[str] = None,
        options: dict = None,
    ) -> dict:
        """Generate title, description, and tags with proper fallback chain."""
        try:
            # Get user tier from options or default to free
            user_tier = options.get("tier", "free") if options else "free"
            tier = Tier(user_tier)

            # Check credits
            if user_id:
                self._check_credits(user_id, "title_generation")

            # Reset tracking for initial generation
            self._regeneration_count[video_id] = 0

            # Generate with fallback chain
            result = self._generate_with_fallback(transcript, tier)

            # Store the first concept used
            self._add_used_concept(video_id, "initial_generation")

            # Deduct credits
            if user_id:
                self.credit_service.use_credits(
                    user_id, 1, f"Title generation for video {video_id}"
                )

            return result

        except Exception as e:
            logger.error(f"Metadata generation failed for video {video_id}: {e}")
            # Ultimate fallback: return mock data
            return self._generate_mock_metadata(transcript, video_id)

    def regenerate_metadata(
        self,
        video_id: str,
        transcript: str,
        user_tier: Tier,
        previous_metadata: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Regenerate metadata with different concepts."""
        # Check regeneration limits
        current_count = self._get_regeneration_count(video_id)
        max_regenerations = self.tier_service.get_text_regenerations(user_tier)

        if current_count >= max_regenerations:
            raise TierLimitExceeded(
                "text_regenerations",
                current_count,
                max_regenerations,
                message=f"You've used {current_count} of {max_regenerations} text regenerations",
            )

        # Check credits
        if user_id:
            self._check_credits(user_id, "title_generation")

        # Generate a truly different concept
        concept = self._get_different_concept(video_id)

        # Create prompt with concept
        prompt = self._create_regeneration_prompt(
            transcript, previous_metadata, concept, current_count + 1
        )

        # Generate with fallback chain
        result = self._generate_with_fallback(transcript, user_tier, prompt)

        # Increment count and store concept
        new_count = self._increment_regeneration_count(video_id)
        self._add_used_concept(video_id, concept)

        # Deduct credits
        if user_id:
            self.credit_service.use_credits(
                user_id, 1, f"Title regeneration for video {video_id}"
            )

        return {
            **result,
            "regeneration_count": new_count,
            "max_regenerations": max_regenerations,
            "concept_used": concept,
        }

    def _generate_with_fallback(
        self, transcript: str, tier: Tier, custom_prompt: str = None
    ) -> dict:
        """
        Complete fallback chain based on tier specifications.

        Fallback order:
        1. Primary model (tier-specific)
        2. Fallback model (tier-specific)
        3. Mock generation (always works)
        """
        # Step 1: Try primary model
        primary_model, primary_provider = self._get_primary_model(tier)
        logger.info(f"🔄 Trying primary model: {primary_model} for tier {tier.value}")

        try:
            result = self._generate_with_provider(
                transcript, primary_provider, primary_model, custom_prompt
            )
            if result:
                logger.info(f"✅ Primary model {primary_model} succeeded")
                return result
        except Exception as e:
            logger.warning(f"⚠️ Primary model {primary_model} failed: {e}")

        # Step 2: Try fallback model
        fallback_model, fallback_provider = self._get_fallback_model(tier)
        logger.info(f"🔄 Trying fallback model: {fallback_model} for tier {tier.value}")

        try:
            result = self._generate_with_provider(
                transcript, fallback_provider, fallback_model, custom_prompt
            )
            if result:
                logger.info(f"✅ Fallback model {fallback_model} succeeded")
                return result
        except Exception as e:
            logger.warning(f"⚠️ Fallback model {fallback_model} failed: {e}")

        # Step 3: Ultimate fallback - mock generation
        logger.warning("⚠️ All AI services failed, using mock generation")
        return self._generate_mock_metadata(transcript)

    def _get_primary_model(self, tier: Tier) -> tuple:
        """Get primary model and provider for the tier."""
        primary_config = {
            Tier.FREE: ("gemini-2.0-flash-exp", "google"),
            Tier.STARTER: ("gemini-2.0-flash-exp", "google"),
            Tier.PRO: ("gemini-1.5-pro", "google"),
            Tier.PLUS: ("gemini-2.0-pro", "google"),
            Tier.ENTERPRISE: ("gpt-4-turbo", "openai"),
        }
        return primary_config.get(tier, ("gemini-2.0-flash-exp", "google"))

    def _get_fallback_model(self, tier: Tier) -> tuple:
        """Get fallback model and provider for the tier."""
        fallback_config = {
            Tier.FREE: ("gpt-4o-mini", "openai"),
            Tier.STARTER: ("gpt-4o-mini", "openai"),
            Tier.PRO: ("gpt-4", "openai"),
            Tier.PLUS: ("gpt-3.5-turbo", "openai"),
            Tier.ENTERPRISE: ("gemini-2.0-pro", "google"),
        }
        return fallback_config.get(tier, ("gpt-4o-mini", "openai"))

    def _generate_with_provider(
        self,
        transcript: str,
        provider: str,
        model: str,
        custom_prompt: str = None,
    ) -> Optional[dict]:
        """Generate metadata with specific provider."""
        prompt = custom_prompt or self._create_prompt(transcript)

        try:
            if provider == "google":
                response = self.google.generate_text(
                    prompt=prompt,
                    model=model,
                    temperature=0.8,
                    max_tokens=1200,
                )
            else:  # openai
                response = self.openai.generate_text(
                    prompt=prompt,
                    model=model,
                    temperature=0.8,
                    max_tokens=1200,
                )

            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Provider {provider} with model {model} failed: {e}")
            return None

    def _generate_mock_metadata(self, transcript: str, video_id: str = None) -> dict:
        """Generate mock metadata when all AI services fail."""
        # Extract first few words as title
        words = transcript.split()[:5] if transcript else ["Video"]
        title = " ".join(words)
        if len(title) > 60:
            title = title[:57] + "..."

        # Generate description
        description = f"This video was processed by Video AI Studio. "
        if transcript:
            description += transcript[:200]
        else:
            description += "No transcript available for this video."

        # Generate tags based on content
        tags = ["video", "ai", "processing", "content"]
        if transcript:
            # Extract common words as tags
            common_words = ["video", "content", "tutorial", "guide", "how-to"]
            for word in common_words:
                if word in transcript.lower():
                    tags.append(word)

        return {
            "title": title or "My Video",
            "description": description[:2000],
            "tags": list(set(tags))[:10],  # Unique tags, max 10
            "_fallback": True,  # Flag to indicate this is fallback
        }

    def _get_different_concept(self, video_id: str) -> str:
        """Get a concept different from previously used ones."""
        used = self._get_used_concepts(video_id)
        available = [c for c in self.CONCEPTS if c not in used]

        if not available:
            # If all concepts used, create variations
            base_concept = random.choice(self.CONCEPTS[:10])
            count = len(used)
            return f"{base_concept} (variation {count + 1})"

        return random.choice(available)

    def _create_prompt(self, transcript: str) -> str:
        """Create prompt for title generation."""
        return f"""
        Based on this video transcript, generate:
        1. A catchy YouTube title (max 60 chars)
        2. An engaging description (150-200 words)
        3. 10 relevant SEO tags
        
        Transcript: {transcript[:3000]}
        
        Return as JSON with keys: title, description, tags (as list)
        """

    def _create_regeneration_prompt(
        self,
        transcript: str,
        previous_metadata: Dict[str, Any],
        concept: str,
        attempt: int,
    ) -> str:
        """Create prompt for regeneration."""
        previous_title = previous_metadata.get("title", "")
        previous_desc = previous_metadata.get("description", "")

        return f"""
        Based on this video transcript, generate a NEW and DIFFERENT version of:
        1. A catchy YouTube title (max 60 chars)
        2. An engaging description (150-200 words)
        3. 10 relevant SEO tags

        The previous version was:
        - Title: {previous_title}
        - Description: {previous_desc[:200]}...

        Make this version #{attempt} have a {concept} tone/style.
        Do NOT repeat the same ideas as before.
        Be creative and think differently.

        Transcript: {transcript[:3000]}

        Return as JSON with keys: title, description, tags (as list)
        """

    def _parse_response(self, response: str) -> dict:
        """Parse AI response into structured data."""
        try:
            # Try to extract JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "title": data.get("title", "Untitled Video")[:100],
                    "description": data.get("description", "")[:2000],
                    "tags": data.get("tags", [])[:20],
                }
        except Exception as e:
            logger.warning(f"JSON parsing failed: {e}")

        # Fallback parsing
        lines = response.strip().split("\n")
        return {
            "title": lines[0][:100] if lines else "My Video",
            "description": " ".join(lines[1:3]) if len(lines) > 1 else "",
            "tags": ["video", "content", "ai", "processing"],
        }

    def _calculate_cost(self, transcript: str, model: str) -> float:
        """Calculate cost for generation."""
        token_count = len(transcript) / 4  # Approximate tokens
        cost_per_1k = self.MODEL_COSTS.get(model, 0.000075)
        return (token_count / 1000) * cost_per_1k

    def get_regeneration_count(self, video_id: str) -> int:
        """Get number of regenerations for a video."""
        return self._get_regeneration_count(video_id)

    def get_max_regenerations(self, tier: Tier) -> int:
        """Get max regenerations allowed for tier."""
        return self.tier_service.get_text_regenerations(tier)
