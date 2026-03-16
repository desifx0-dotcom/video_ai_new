"""
Transcription service using OpenAI Whisper.
"""

import os
import tempfile
from typing import Dict, Any, Optional
import logging

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError, ExternalServiceError
from providers.openai_provider import OpenAIProvider
from providers.ffmpeg_provider import FFmpegProvider

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Transcription service using Whisper API."""

    def __init__(self):
        self.openai = OpenAIProvider()
        self.ffmpeg = FFmpegProvider()

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,  # User selected language
        tier: Tier = Tier.FREE,
        detect_language: bool = True,
    ) -> Dict[str, Any]:
        """
        Transcribe audio file using Whisper API.

        Args:
            audio_path: Path to audio file
            language: Optional language code
            tier: User tier for model selection
            detect_language: Whether to detect language automatically

        Returns:
            Transcription results
        """
        if not os.path.exists(audio_path):
            raise ProcessingError(f"Audio file not found: {audio_path}")

        # Prepare audio for Whisper
        prepared_audio = self._prepare_audio(audio_path)

        try:

            # If language not specified but detection requested, use auto
            whisper_language = language
            if detect_language and not language:
                # Let Whisper auto-detect
                whisper_language = None

            # Transcribe using Whisper
            transcription = self.openai.transcribe_audio(
                audio_path=prepared_audio["path"],
                model=self._get_model_for_tier(tier),
                language=whisper_language,  # None = auto-detect
                response_format="verbose_json",
                tier=tier,
            )

            segments = (
                transcription.get("segments", [])
                if isinstance(transcription, dict)
                else []
            )

            # Get detected language from Whisper response
            detected_language = transcription.get("language", language or "en")
            # detected_confidence = transcription.get("language_confidence", 0.9)

            # Calculate cost
            cost = self._calculate_cost(duration=prepared_audio["duration"], tier=tier)

            # Cleanup prepared audio file
            if (
                os.path.exists(prepared_audio["path"])
                and prepared_audio["path"] != audio_path
            ):
                os.remove(prepared_audio["path"])

            result = {
                "text": transcription["text"],
                "language": detected_language,
                # "language_confidence": detected_confidence,
                # "language_detected": detect_language and not language,
                "user_selected_language": language,  # What user selected (if any)
                "duration": prepared_audio["duration"],
                "cost": cost,
                "model": transcription.get("model", "whisper-1"),
                "tier": tier.value,
                "segments": segments,
            }

            # If auto-detection was used, log it
            # if detect_language and not language:
            #     logger.info(
            #         f"Auto-detected language: {detected_language} (confidence: {detected_confidence})"
            #     )

            return result

        except Exception as e:
            # Cleanup on error
            if (
                os.path.exists(prepared_audio["path"])
                and prepared_audio["path"] != audio_path
            ):
                os.remove(prepared_audio["path"])

            if "OpenAI" in str(e) or "Whisper" in str(e):
                raise ExternalServiceError("OpenAI", str(e))
            else:
                raise ProcessingError(
                    f"Transcription failed: {str(e)}", step="transcription"
                )

    # def detect_language_from_audio(self, audio_path: str) -> Optional[Dict[str, Any]]:
    #     """
    #     Detect language of audio file without full transcription.

    #     Args:
    #         audio_path: Path to audio file

    #     Returns:
    #         Language detection results
    #     """
    #     if not os.path.exists(audio_path):
    #         return None

    #     try:
    #         # Use Whisper to detect language (transcribe with return_language_only)
    #         result = self.openai.detect_language(audio_path)

    #         return {
    #             "language": result.get("language"),
    #             "confidence": result.get("confidence", 0.8),
    #             "method": "whisper_detection",
    #         }
    #     except Exception as e:
    #         logger.error(f"Language detection failed: {str(e)}")
    #         return {
    #             "language": "en",
    #             "confidence": 0.0,
    #             "method": "fallback",
    #             "error": str(e),
    #         }

    # def transcribe_with_detection(
    #     self,
    #     audio_path: str,
    #     tier: Tier = Tier.FREE,
    #     preferred_languages: Optional[list[str]] = None,
    # ) -> Dict[str, Any]:
    #     """
    #     Transcribe with multi-language support and fallback.

    #     Args:
    #         audio_path: Path to audio file
    #         tier: User tier
    #         preferred_languages: List of preferred language codes

    #     Returns:
    #         Transcription with language detection
    #     """
    #     # First try with auto-detection
    #     result = self.transcribe(
    #         audio_path=audio_path,
    #         language=None,  # Auto-detect
    #         tier=tier,
    #         detect_language=True,
    #     )

    #     # If confidence is low and preferred languages provided, try each
    #     if result.get("language_confidence", 0) < 0.7 and preferred_languages:
    #         best_result = result
    #         best_confidence = result.get("language_confidence", 0)

    #         for lang in preferred_languages:
    #             try:
    #                 lang_result = self.transcribe(
    #                     audio_path=audio_path,
    #                     language=lang,
    #                     tier=tier,
    #                     detect_language=False,
    #                 )

    #                 # Compare confidence (this is simplified)
    #                 if lang_result.get("language_confidence", 0) > best_confidence:
    #                     best_result = lang_result
    #                     best_confidence = lang_result.get("language_confidence", 0)
    #             except Exception as e:
    #                 logger.debug(f"Failed to transcribe with language {lang}: {e}")
    #                 continue

    #         return best_result

    #     return result

    def _prepare_audio(self, audio_path: str) -> Dict[str, Any]:
        """Prepare audio file for Whisper API."""
        # Get audio duration
        duration = self.ffmpeg.get_audio_duration(audio_path)

        # Check if audio needs conversion
        # Whisper prefers 16kHz mono WAV files

        # Create temporary output file
        temp_dir = tempfile.mkdtemp(prefix="video_ai_transcribe_")
        output_path = os.path.join(temp_dir, "audio.wav")

        # Convert audio if needed
        cmd = [
            "ffmpeg",
            "-i",
            audio_path,
            "-ar",
            "16000",  # 16kHz sample rate
            "-ac",
            "1",  # Mono
            "-acodec",
            "pcm_s16le",  # WAV format
            "-y",  # Overwrite output
            output_path,
        ]

        import subprocess

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # If conversion fails, try to use original
            logger.warning(f"Audio conversion failed: {result.stderr}")
            output_path = audio_path

        return {
            "path": output_path,
            "duration": duration,
            "converted": output_path != audio_path,
        }

    def _get_model_for_tier(self, tier: Tier) -> str:
        """Get Whisper model for user tier."""
        # All tiers use whisper-1 for now
        # Could use different models for different tiers in the future
        return "whisper-1"

    def _calculate_cost(self, duration: float, tier: Tier) -> float:
        """Calculate transcription cost."""
        # Whisper API pricing: $0.006 per minute
        cost_per_minute = 0.006

        # Calculate minutes
        minutes = max(1, duration / 60)  # Minimum 1 minute

        # Apply tier discounts if any
        tier_multipliers = {
            Tier.FREE: 1.0,
            Tier.STARTER: 1.0,
            Tier.PRO: 1.0,
            Tier.PLUS: 1.0,
            Tier.ENTERPRISE: 1.0,
        }

        multiplier = tier_multipliers.get(tier, 1.0)

        return cost_per_minute * minutes * multiplier

    def get_supported_languages(self) -> Dict[str, str]:
        """Get supported languages for transcription."""
        return {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "ar": "Arabic",
            "hi": "Hindi",
            "bn": "Bengali",
            "tr": "Turkish",
            "vi": "Vietnamese",
            "th": "Thai",
            "id": "Indonesian",
            "nl": "Dutch",
            "pl": "Polish",
            "uk": "Ukrainian",
            "sv": "Swedish",
            "da": "Danish",
            "fi": "Finnish",
            "no": "Norwegian",
            "he": "Hebrew",
            "el": "Greek",
        }

    def detect_language(self, audio_path: str) -> Optional[str]:
        """Detect language of audio file."""
        if not os.path.exists(audio_path):
            return None

        try:
            # Use Whisper to detect language
            result = self.openai.detect_language(audio_path)
            return result.get("language")
        except Exception as e:
            logger.error(f"Language detection failed: {str(e)}")
            return None

    def estimate_transcription_time(self, duration: float) -> float:
        """Estimate transcription time in seconds."""
        # Rough estimate: 2x realtime for API calls
        # Local models would be slower
        return duration * 2

    def validate_audio_for_transcription(self, audio_path: str) -> Dict[str, Any]:
        """Validate audio file for transcription."""
        if not os.path.exists(audio_path):
            return {"valid": False, "error": "File not found", "size": 0, "duration": 0}

        try:
            # Get file size
            size = os.path.getsize(audio_path)

            # Get duration
            duration = self.ffmpeg.get_audio_duration(audio_path)

            # Check constraints
            max_duration = 3600  # 60 minutes
            max_size = 25 * 1024 * 1024  # 25MB (Whisper API limit)

            valid = True
            errors = []

            if duration > max_duration:
                valid = False
                errors.append(f"Audio too long ({duration}s > {max_duration}s)")

            if size > max_size:
                valid = False
                errors.append(
                    f"Audio file too large ({size/1024/1024:.1f}MB > {max_size/1024/1024:.1f}MB)"
                )

            if duration <= 0:
                valid = False
                errors.append("Audio duration is zero or negative")

            return {
                "valid": valid,
                "error": "; ".join(errors) if errors else None,
                "size": size,
                "duration": duration,
                "max_duration": max_duration,
                "max_size": max_size,
            }

        except Exception as e:
            return {"valid": False, "error": str(e), "size": 0, "duration": 0}
