"""
Google AI provider for Gemini, Translation, and Vision.
Updated with new model names and proper error handling.
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List
import google.generativeai as genai
from google.cloud import translate_v2 as translate
import google.auth
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from core.exceptions import ExternalServiceError
from core.domain.value_objects.tier import Tier

logger = logging.getLogger(__name__)


class GoogleProvider:
    """Google AI provider with retry and timeout."""

    # Updated model names (as of March 2026)
    MODELS = {
        "text": "gemini-2.0-flash",  # For text generation
        "text_pro": "gemini-2.0-pro",  # For higher quality text
        "vision": "gemini-2.0-flash",  # For vision/image analysis
        "translation": "gemini-2.0-flash-lite",  # For translation
    }

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        """
        Initialize Google provider.

        Args:
            api_key: Google API key (optional, will use env var if not provided)
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")

        # Check mock mode from .env FIRST
        self._mock_mode = os.getenv("GOOGLE_MOCK_MODE", "false").lower() == "true"

        if self._mock_mode:
            print(
                "🔧 [MOCK] Using mock Google AI (no API calls) - enabled by GOOGLE_MOCK_MODE=true"
            )
            self.translate_client = None
            self._genai = None
            return

        # Only proceed with real API if not in mock mode. if self.mock_mode is false
        if not self.api_key:
            if os.getenv("FLASK_ENV") == "development":
                print("⚠️  Development mode: No API key, using mock Google AI")
                self._mock_mode = True
                self.translate_client = None
                self._genai = None
                return
            else:
                raise ExternalServiceError("Google", "API key not configured")

        try:
            # Configure Gemini with the API key
            genai.configure(api_key=self.api_key)
            print("✅ Google Gemini configured with new models")

            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path and os.path.exists(credentials_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                self.translate_client = translate.Client()
                print("✅ Google Translate client initialized")
            else:
                print("⚠️  Google Translate credentials not found, using mock")
                self.translate_client = None

            logger.info("Google provider initialized successfully with new models")

        except Exception as e:
            logger.error(f"Google provider initialization failed: {e}")
            if os.getenv("FLASK_ENV") == "development":
                print(f"⚠️  Google init failed, using mock: {e}")
                self._mock_mode = True
                self.translate_client = None
                self._genai = None
            else:
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(ExternalServiceError),
    )
    def generate_text(
        self,
        prompt: str,
        model: str = None,  # Now optional, will use default
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> str:
        """Generate text with retry and timeout."""
        if self._mock_mode:
            print(f"🔧 [MOCK] Google Gemini called with prompt: {prompt[:50]}...")
            mock_responses = [
                "This is a mock AI-generated response for development.",
                f"Mock response for: {prompt[:30]}...",
                "Generated title: Amazing Video Content",
                "Tags: education, tutorial, learning, video, content",
                "Description: A comprehensive video about the topic.",
            ]
            return mock_responses[len(prompt) % len(mock_responses)]

        # Use default model if none provided
        if model is None:
            model = self.MODELS["text"]

        # Map old model names to new ones if needed
        model_map = {
            "gemini-2.0-flash-lite": self.MODELS["text"],
            "gemini-2.0-flash": self.MODELS["text"],
            "gemini-2.0-flash-exp": self.MODELS["text"],
            "gemini-2.0-pro": self.MODELS["text_pro"],
            "gemini-1.5-pro": self.MODELS["text_pro"],
        }
        actual_model = model_map.get(model, model)

        try:
            model_instance = genai.GenerativeModel(actual_model)

            response = model_instance.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    **kwargs,
                },
            )

            return response.text

        except Exception as e:
            logger.error(
                f"Google Gemini generation failed with model {actual_model}: {str(e)}"
            )

            # Try fallback model if the first one fails
            if actual_model == self.MODELS["text_pro"]:
                try:
                    logger.info("Falling back to flash model")
                    fallback_model = genai.GenerativeModel(self.MODELS["text"])
                    response = fallback_model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                            **kwargs,
                        },
                    )
                    return response.text
                except Exception as e2:
                    logger.error(f"Fallback also failed: {e2}")

            raise ExternalServiceError("Google", str(e))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(ExternalServiceError),
    )
    def analyze_image(
        self, image_path: str, features: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Analyze image with retry."""
        if self._mock_mode:
            print(f"🔧 [MOCK] Google Vision analyzing: {image_path}")
            return {
                "description": "Mock image analysis: Contains various elements suitable for video thumbnail.",
                "objects": ["person", "background", "text"],
                "colors": ["blue", "white", "black"],
                "labels": ["professional", "clean", "modern"],
                "cost": 0.0,
            }

        try:
            with open(image_path, "rb") as image_file:
                image_data = image_file.read()

            model = genai.GenerativeModel(self.MODELS["vision"])

            response = model.generate_content(
                [
                    "Analyze this image in detail. Provide:",
                    "1. Main objects and subjects",
                    "2. Colors and lighting",
                    "3. Scene description",
                    "4. Possible context or activity",
                    image_data,
                ],
                generation_config={
                    "temperature": 0.3,
                },
            )

            analysis_text = response.text

            return {
                "description": analysis_text,
                "objects": self._extract_objects(analysis_text),
                "colors": self._extract_colors(analysis_text),
                "labels": self._extract_labels(analysis_text),
                "cost": 0.0025,
            }

        except Exception as e:
            logger.error(f"Google Vision analysis failed: {str(e)}")
            raise ExternalServiceError("Google", str(e))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(ExternalServiceError),
    )
    def translate_text(
        self, text: str, target_language: str, source_language: str = "auto"
    ) -> str:
        """Translate text with retry."""
        if self._mock_mode or self.translate_client is None:
            print(f"🔧 [MOCK] Translate '{text[:30]}...' to {target_language}")
            mock_translations = {
                "es": f"[ES] {text}",
                "fr": f"[FR] {text}",
                "de": f"[DE] {text}",
                "zh": f"[ZH] {text}",
                "ja": f"[JA] {text}",
            }
            return mock_translations.get(
                target_language, f"[{target_language.upper()}] {text}"
            )

        try:
            result = self.translate_client.translate(
                text,
                target_language=target_language,
                source_language=source_language if source_language != "auto" else None,
            )
            return result["translatedText"]

        except Exception as e:
            logger.error(f"Google Translate failed: {str(e)}")
            raise ExternalServiceError("Google Translate", str(e))

    def _extract_objects(self, analysis_text: str) -> List[str]:
        """Extract objects from analysis text."""
        common_objects = [
            "person",
            "people",
            "man",
            "woman",
            "child",
            "face",
            "car",
            "vehicle",
            "building",
            "house",
            "tree",
            "plant",
            "animal",
            "dog",
            "cat",
            "bird",
            "sky",
            "cloud",
            "water",
            "food",
            "drink",
            "computer",
            "phone",
            "book",
            "chair",
            "table",
            "bed",
            "clothing",
            "shoe",
            "bag",
            "instrument",
        ]

        found_objects = []
        for obj in common_objects:
            if obj in analysis_text.lower():
                found_objects.append(obj)

        return found_objects[:10]

    def _extract_colors(self, analysis_text: str) -> List[str]:
        """Extract colors from analysis text."""
        colors = [
            "red",
            "orange",
            "yellow",
            "green",
            "blue",
            "purple",
            "pink",
            "brown",
            "black",
            "white",
            "gray",
            "grey",
            "vibrant",
            "bright",
            "dark",
            "light",
        ]

        found_colors = []
        for color in colors:
            if color in analysis_text.lower():
                found_colors.append(color)

        return found_colors[:5]

    def _extract_labels(self, analysis_text: str) -> List[str]:
        """Extract labels from analysis text."""
        sentences = analysis_text.split(".")
        labels = []

        for sentence in sentences[:5]:
            sentence = sentence.strip()
            if sentence and len(sentence.split()) <= 10:
                labels.append(sentence)

        return labels

    def test_connection(self) -> bool:
        """Test Google AI API connection."""
        try:
            # Try to list models to test connection
            genai.list_models(limit=1)
            return True
        except Exception as e:
            logger.error(f"Google AI connection test failed: {str(e)}")
            return False
