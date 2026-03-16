"""
Translation service using googletrans (free).
"""

from typing import Dict, Any, List, Optional
import logging

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError
from core.constants import SUPPORTED_LANGUAGES

# from googletrans import Translator
from google.cloud import translate_v2 as translator

logger = logging.getLogger(__name__)


class TranslationService:
    """Translation service using googletrans."""

    def __init__(self):
        self.translator = translator
        self._cache = {}  # Simple in-memory cache

    def translate(
        self,
        text: str,
        target_language: str,
        tier: Tier,
        source_language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Translate text to target language.

        Args:
            text: Text to translate
            target_language: Target language code
            tier: User tier (for rate limiting)
            source_language: Optional source language code

        Returns:
            Translation result
        """
        if not text or not text.strip():
            return {
                "text": "",
                "source_language": source_language or "auto",
                "target_language": target_language,
                "cost": 0.0,
                "cached": False,
            }

        # Validate language codes
        if not self._is_language_supported(target_language):
            raise ProcessingError(f"Unsupported target language: {target_language}")

        if source_language and not self._is_language_supported(source_language):
            raise ProcessingError(f"Unsupported source language: {source_language}")

        # Check cache
        cache_key = f"{text[:100]}_{source_language}_{target_language}"
        if cache_key in self._cache:
            cached_result = self._cache[cache_key]
            return {
                **cached_result,
                "cached": True,
                "cost": 0.0,  # Cached translations are free
            }

        try:
            # Perform translation
            translated = self.translator.translate(
                text=text, dest=target_language, src=source_language
            )

            result = {
                "text": translated.text,
                "source_language": translated.src,
                "target_language": translated.dest,
                "pronunciation": getattr(translated, "pronunciation", None),
                "original_text": text,
                "cost": self._calculate_cost(len(text), tier),
                "cached": False,
                "confidence": 0.9,  # Google Translate confidence estimate
            }

            # Cache result
            self._cache[cache_key] = {
                "text": translated.text,
                "source_language": translated.src,
                "target_language": translated.dest,
                "pronunciation": getattr(translated, "pronunciation", None),
            }

            # Limit cache size
            if len(self._cache) > 1000:
                # Remove oldest entries
                keys = list(self._cache.keys())
                for key in keys[:100]:
                    del self._cache[key]

            return result

        except Exception as e:
            raise ProcessingError(f"Translation failed: {str(e)}", step="translation")

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        tier: Tier,
        source_language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Translate multiple texts in batch.

        Args:
            texts: List of texts to translate
            target_language: Target language code
            tier: User tier
            source_language: Optional source language code

        Returns:
            List of translation results
        """
        if not texts:
            return []

        # Check if batch translation is allowed for tier
        if not self._is_batch_translation_allowed(tier):
            # Fall back to individual translations
            results = []
            for text in texts:
                try:
                    result = self.translate(
                        text, target_language, tier, source_language
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to translate text in batch: {str(e)}")
                    results.append(
                        {
                            "text": text,  # Return original text on error
                            "source_language": source_language or "auto",
                            "target_language": target_language,
                            "error": str(e),
                            "cost": 0.0,
                        }
                    )
            return results

        try:
            # Batch translation
            translated_list = self.translator.translate(
                texts=texts, dest=target_language, src=source_language
            )

            results = []
            total_cost = 0.0

            for i, translated in enumerate(translated_list):
                text_cost = self._calculate_cost(len(texts[i]), tier)
                total_cost += text_cost

                results.append(
                    {
                        "text": translated.text,
                        "source_language": translated.src,
                        "target_language": translated.dest,
                        "pronunciation": getattr(translated, "pronunciation", None),
                        "original_text": texts[i],
                        "cost": text_cost,
                        "cached": False,
                        "confidence": 0.9,
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Batch translation failed: {str(e)}")
            # Fall back to individual translations
            return self.translate_batch(texts, target_language, tier, source_language)

    def detect_language(self, text: str) -> Dict[str, Any]:
        """Detect language of text."""
        if not text or not text.strip():
            return {"language": "en", "confidence": 0.0, "text": text}

        try:
            detected = self.translator.detect(text)

            return {
                "language": detected.lang,
                "confidence": detected.confidence,
                "text": text,
            }

        except Exception as e:
            logger.error(f"Language detection failed: {str(e)}")
            return {"language": "en", "confidence": 0.0, "text": text}

    def get_supported_languages(self) -> Dict[str, str]:
        """Get all supported languages."""
        # Map language codes to names
        language_names = {
            "af": "Afrikaans",
            "sq": "Albanian",
            "am": "Amharic",
            "ar": "Arabic",
            "hy": "Armenian",
            "az": "Azerbaijani",
            "eu": "Basque",
            "be": "Belarusian",
            "bn": "Bengali",
            "bs": "Bosnian",
            "bg": "Bulgarian",
            "ca": "Catalan",
            "ceb": "Cebuano",
            "ny": "Chichewa",
            "zh-cn": "Chinese (Simplified)",
            "zh-tw": "Chinese (Traditional)",
            "co": "Corsican",
            "hr": "Croatian",
            "cs": "Czech",
            "da": "Danish",
            "nl": "Dutch",
            "en": "English",
            "eo": "Esperanto",
            "et": "Estonian",
            "tl": "Filipino",
            "fi": "Finnish",
            "fr": "French",
            "fy": "Frisian",
            "gl": "Galician",
            "ka": "Georgian",
            "de": "German",
            "el": "Greek",
            "gu": "Gujarati",
            "ht": "Haitian Creole",
            "ha": "Hausa",
            "haw": "Hawaiian",
            "he": "Hebrew",
            "hi": "Hindi",
            "hmn": "Hmong",
            "hu": "Hungarian",
            "is": "Icelandic",
            "ig": "Igbo",
            "id": "Indonesian",
            "ga": "Irish",
            "it": "Italian",
            "ja": "Japanese",
            "jw": "Javanese",
            "kn": "Kannada",
            "kk": "Kazakh",
            "km": "Khmer",
            "ko": "Korean",
            "ku": "Kurdish (Kurmanji)",
            "ky": "Kyrgyz",
            "lo": "Lao",
            "la": "Latin",
            "lv": "Latvian",
            "lt": "Lithuanian",
            "lb": "Luxembourgish",
            "mk": "Macedonian",
            "mg": "Malagasy",
            "ms": "Malay",
            "ml": "Malayalam",
            "mt": "Maltese",
            "mi": "Maori",
            "mr": "Marathi",
            "mn": "Mongolian",
            "my": "Myanmar (Burmese)",
            "ne": "Nepali",
            "no": "Norwegian",
            "ps": "Pashto",
            "fa": "Persian",
            "pl": "Polish",
            "pt": "Portuguese",
            "pa": "Punjabi",
            "ro": "Romanian",
            "ru": "Russian",
            "sm": "Samoan",
            "gd": "Scots Gaelic",
            "sr": "Serbian",
            "st": "Sesotho",
            "sn": "Shona",
            "sd": "Sindhi",
            "si": "Sinhala",
            "sk": "Slovak",
            "sl": "Slovenian",
            "so": "Somali",
            "es": "Spanish",
            "su": "Sundanese",
            "sw": "Swahili",
            "sv": "Swedish",
            "tg": "Tajik",
            "ta": "Tamil",
            "te": "Telugu",
            "th": "Thai",
            "tr": "Turkish",
            "uk": "Ukrainian",
            "ur": "Urdu",
            "uz": "Uzbek",
            "vi": "Vietnamese",
            "cy": "Welsh",
            "xh": "Xhosa",
            "yi": "Yiddish",
            "yo": "Yoruba",
            "zu": "Zulu",
        }

        return language_names

    def _is_language_supported(self, language_code: str) -> bool:
        """Check if language code is supported."""
        # Normalize language code
        lang = language_code.lower().replace("_", "-")

        # Check against our list
        return lang in SUPPORTED_LANGUAGES

    def _is_batch_translation_allowed(self, tier: Tier) -> bool:
        """Check if batch translation is allowed for tier."""
        # Batch translation for Pro tier and above
        return tier in [Tier.PRO, Tier.PLUS, Tier.ENTERPRISE]

    def _calculate_cost(self, text_length: int, tier: Tier) -> float:
        """
        Calculate translation cost.

        Note: googletrans is free, but we calculate "cost" for consistency
        and potential future paid service integration.
        """
        # Free translation service
        return 0.0

    def estimate_translation_time(self, text_length: int) -> float:
        """Estimate translation time in seconds."""
        # Rough estimate: 0.1 seconds per 100 characters
        return max(0.5, text_length / 1000)  # Minimum 0.5 seconds

    def translate_video_metadata(
        self,
        title: str,
        description: str,
        tags: List[str],
        target_language: str,
        tier: Tier,
    ) -> Dict[str, Any]:
        """
        Translate video metadata (title, description, tags).

        Args:
            title: Video title
            description: Video description
            tags: Video tags
            target_language: Target language code
            tier: User tier

        Returns:
            Translated metadata
        """
        results = {}
        total_cost = 0.0

        # Translate title
        if title:
            title_result = self.translate(title, target_language, tier)
            results["title"] = title_result["text"]
            total_cost += title_result["cost"]

        # Translate description
        if description:
            # Split description if too long (Google Translate has limits)
            if len(description) > 5000:
                # Split into chunks
                chunks = self._split_text(description, 4500)
                translated_chunks = []

                for chunk in chunks:
                    chunk_result = self.translate(chunk, target_language, tier)
                    translated_chunks.append(chunk_result["text"])
                    total_cost += chunk_result["cost"]

                results["description"] = " ".join(translated_chunks)
            else:
                desc_result = self.translate(description, target_language, tier)
                results["description"] = desc_result["text"]
                total_cost += desc_result["cost"]

        # Translate tags
        if tags:
            # Translate tags in batch if allowed
            if self._is_batch_translation_allowed(tier):
                tags_results = self.translate_batch(tags, target_language, tier)
                results["tags"] = [r["text"] for r in tags_results]
                total_cost += sum(r["cost"] for r in tags_results)
            else:
                translated_tags = []
                for tag in tags:
                    tag_result = self.translate(tag, target_language, tier)
                    translated_tags.append(tag_result["text"])
                    total_cost += tag_result["cost"]
                results["tags"] = translated_tags

        results["total_cost"] = total_cost
        results["target_language"] = target_language
        results["original_title"] = title
        results["original_description"] = description
        results["original_tags"] = tags

        return results

    def _split_text(self, text: str, max_length: int) -> List[str]:
        """Split text into chunks of maximum length."""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            word_length = len(word) + 1  # +1 for space

            if current_length + word_length > max_length:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [word]
                    current_length = word_length
                else:
                    # Single word longer than max_length
                    chunks.append(word)
                    current_chunk = []
                    current_length = 0
            else:
                current_chunk.append(word)
                current_length += word_length

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks
