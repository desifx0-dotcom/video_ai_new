"""
Translation service with Gemini Flash primary and GPT-4o Mini fallback.
Complete production version with caching, batch limits, and cost tracking.
"""

from typing import Dict, Any, List, Optional
import logging
import json
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError, ExternalServiceError, TierLimitExceeded
from providers.google_provider import GoogleProvider
from providers.openai_provider import OpenAIProvider
from services.tier_service import TierService
from services.credit_service import CreditService

logger = logging.getLogger(__name__)


class TranslationService:
    """Translation service with tier-based limits, caching, and cost tracking."""

    # Cache TTL in seconds
    CACHE_TTL = 86400  # 24 hours

    # Cost per 1K characters by model
    COST_PER_1K = {
        "gemini-flash": 0.00006,
        "gpt-4o-mini": 0.00015,
        "batch": 0.00003,
    }

    def __init__(self, redis_client=None):
        self.google = GoogleProvider()
        self.openai = OpenAIProvider()
        self.tier_service = TierService(redis_client)
        self.credit_service = CreditService()
        self._redis = redis_client

    def _get_cache_key(self, text: str, source: Optional[str], target: str) -> str:
        """Generate cache key for translation."""
        # Use hash of normalized text for cache key
        normalized = text[:500].lower().strip()
        key_string = f"{normalized}_{source}_{target}"
        return f"trans:{hashlib.md5(key_string.encode()).hexdigest()}"

    def _get_cached_translation(self, key: str) -> Optional[str]:
        """Get cached translation."""
        if not self._redis:
            return None
        try:
            cached = self._redis.get(key)
            if cached:
                logger.debug(f"Cache hit for key {key}")
                return cached.decode()
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")
        return None

    def _cache_translation(self, key: str, text: str, ttl: int = None):
        """Cache translation result."""
        if not self._redis:
            return
        try:
            self._redis.setex(key, ttl or self.CACHE_TTL, text)
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    def _check_rate_limit(self, user_id: str, tier: Tier) -> bool:
        """Check translation rate limit."""
        if not self._redis:
            return True

        now = datetime.utcnow()
        hour_key = f"trans_rate:{user_id}:{now.strftime('%Y%m%d%H')}"

        try:
            count = self._redis.incr(hour_key)
            self._redis.expire(hour_key, 3600)

            tier_spec = self.tier_service.get_tier(tier)
            max_per_hour = tier_spec.rate_limit_per_hour if tier_spec else 200

            if count > max_per_hour:
                logger.warning(
                    f"Rate limit exceeded for user {user_id}: {count}/{max_per_hour}"
                )
                return False
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")

        return True

    def can_translate(self, video) -> bool:
        """Check if video can be translated (has text content)."""
        return bool(video.title or video.description or video.transcription)

    def translate(
        self,
        text: str,
        target_language: str,
        tier: Tier,
        source_language: Optional[str] = None,
        user_id: Optional[str] = None,
        video_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Translate text to target language with tier-based limits."""
        start_time = time.time()

        # Handle empty text
        if not text or not text.strip():
            return {
                "text": "",
                "source_language": "none",
                "target_language": target_language,
                "cost": 0.0,
                "cached": False,
                "message": "No text to translate",
            }

        # Check rate limit
        if not self._check_rate_limit(user_id, tier):
            raise TierLimitExceeded(
                "rate_limit",
                0,
                0,
                message="Translation rate limit exceeded. Please try again later.",
            )

        # Check tier translation permission
        tier_spec = self.tier_service.get_tier(tier)
        if not tier_spec.translation_enabled:
            raise TierLimitExceeded(
                "translation",
                0,
                0,
                message=f"Translation not available in {tier.value} tier. Upgrade to enable.",
                upgrade_url="/pricing",
            )

        # Check cache
        cache_key = self._get_cache_key(text, source_language, target_language)
        cached_result = self._get_cached_translation(cache_key)
        if cached_result:
            return {
                "text": cached_result,
                "source_language": source_language or "auto",
                "target_language": target_language,
                "cost": 0.0,
                "cached": True,
                "processing_time_ms": 0,
            }

        # Calculate approximate token count for cost
        char_count = len(text)
        approx_tokens = char_count / 4

        # Translate
        is_batch = char_count > 2000
        try:
            if is_batch and tier_spec.batch_translation:
                result = self._translate_batch(text, target_language, source_language)
                cost_model = "batch"
            else:
                result = self._translate_with_primary(
                    text, target_language, source_language
                )
                cost_model = "gemini-flash"

            # Calculate cost
            cost = (approx_tokens / 1000) * self.COST_PER_1K.get(cost_model, 0.00006)

            # Cache result
            self._cache_translation(cache_key, result)

            # Track usage
            if user_id and video_id:
                self.credit_service.track_usage(
                    user_id,
                    "translation",
                    video_id,
                    {
                        "characters": char_count,
                        "cost": cost,
                        "target_language": target_language,
                        "source_language": source_language,
                    },
                )

            processing_time = (time.time() - start_time) * 1000

            return {
                "text": result,
                "source_language": source_language or "auto",
                "target_language": target_language,
                "cost": cost,
                "cached": False,
                "provider": cost_model,
                "characters": char_count,
                "processing_time_ms": round(processing_time, 2),
                "is_batch": is_batch,
            }

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            raise ProcessingError(f"Translation failed: {str(e)}", step="translation")

    def _translate_with_primary(
        self, text: str, target_language: str, source_language: Optional[str]
    ) -> str:
        """Translate using Gemini 1.5 Flash."""
        try:
            return self._translate_with_gemini(text, target_language, source_language)
        except Exception as e:
            logger.warning(
                f"Gemini translation failed: {e}, falling back to GPT-4o Mini"
            )
            return self._translate_with_gpt4o_mini(
                text, target_language, source_language
            )

    def _translate_with_gemini(
        self, text: str, target_language: str, source_language: Optional[str]
    ) -> str:
        """Translate using Gemini 1.5 Flash."""
        if source_language and source_language != "auto":
            prompt = f"Translate this text from {source_language} to {target_language}. Only return the translated text, nothing else.\n\nText: {text}"
        else:
            prompt = f"Translate this text to {target_language}. Only return the translated text, nothing else.\n\nText: {text}"

        response = self.google.generate_text(
            prompt=prompt,
            model="gemini-2.0-flash-lite",
            temperature=0.3,
            max_tokens=len(text) * 2,
        )
        return response.strip()

    def _translate_with_gpt4o_mini(
        self, text: str, target_language: str, source_language: Optional[str]
    ) -> str:
        """Translate using GPT-4o Mini."""
        if source_language and source_language != "auto":
            prompt = f"Translate this text from {source_language} to {target_language}. Only return the translated text.\n\nText: {text}"
        else:
            prompt = f"Translate this text to {target_language}. Only return the translated text.\n\nText: {text}"

        response = self.openai.generate_text(
            prompt=prompt,
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=len(text) * 2,
        )
        return response.strip()

    def _translate_batch(
        self, text: str, target_language: str, source_language: Optional[str]
    ) -> str:
        """Translate large text in batches."""
        chunks = self._split_text(text, 4500)
        translated_chunks = []

        for chunk in chunks:
            translated = self._translate_with_primary(
                chunk, target_language, source_language
            )
            translated_chunks.append(translated)

        return " ".join(translated_chunks)

    def translate_video_metadata(
        self,
        title: str,
        description: str,
        tags: List[str],
        target_language: str,
        tier: Tier,
        user_id: Optional[str] = None,
        video_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Translate video metadata."""
        results = {}
        total_cost = 0.0

        # Check if there's anything to translate
        has_content = title or description or tags
        if not has_content:
            return {
                "message": "No content to translate",
                "target_language": target_language,
                "total_cost": 0.0,
            }

        # Translate title
        if title:
            title_result = self.translate(
                title, target_language, tier, user_id=user_id, video_id=video_id
            )
            results["title"] = title_result["text"]
            total_cost += title_result["cost"]

        # Translate description
        if description:
            desc_result = self.translate(
                description, target_language, tier, user_id=user_id, video_id=video_id
            )
            results["description"] = desc_result["text"]
            total_cost += desc_result["cost"]

        # Translate tags
        if tags:
            translated_tags = []
            for tag in tags[:20]:  # Limit to 20 tags
                tag_result = self.translate(
                    tag, target_language, tier, user_id=user_id, video_id=video_id
                )
                translated_tags.append(tag_result["text"])
                total_cost += tag_result["cost"]
            results["tags"] = translated_tags

        results["total_cost"] = total_cost
        results["target_language"] = target_language
        return results

    def _split_text(self, text: str, max_length: int) -> List[str]:
        """Split text into chunks by sentences."""
        sentences = text.split(".")
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_length = len(sentence) + 1
            if current_length + sentence_length > max_length and current_chunk:
                chunks.append(". ".join(current_chunk) + ".")
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length

        if current_chunk:
            chunks.append(". ".join(current_chunk) + ".")

        return chunks

    def get_supported_languages(self) -> List[Dict[str, str]]:
        """Get all supported languages for frontend dropdown."""
        from core.constants import LANGUAGE_METADATA

        languages = []
        for code, info in LANGUAGE_METADATA.items():
            languages.append(
                {
                    "code": code,
                    "name": info["name"],
                    "native": info["native"],
                    "rtl": info.get("rtl", False),
                }
            )
        languages.sort(key=lambda x: x["name"])
        return languages

    def clear_cache(self):
        """Clear translation cache."""
        if self._redis:
            try:
                keys = self._redis.keys("trans:*")
                if keys:
                    self._redis.delete(*keys)
                    logger.info(f"Cleared {len(keys)} translation cache entries")
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")
        logger.info("Translation cache cleared")
