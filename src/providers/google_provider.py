"""
Google AI provider for Gemini, Translation, and Vision.
"""

import os
import logging
from typing import Dict, Any, Optional, List
import google.generativeai as genai
from google.cloud import translate_v2 as translate
import google.auth

from core.exceptions import ExternalServiceError
from core.domain.value_objects.tier import Tier

logger = logging.getLogger(__name__)


class GoogleProvider:
    """Google AI provider."""

    # In google_provider.py __init__, update:
    # In google_provider.py __init__, update:
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Google provider.

        Args:
            api_key: Google API key (optional, will use env var if not provided)
        """
        # Use provided API key or fall back to environment variable
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._mock_mode = False

        if not self.api_key:
            # Check if we're in development mode
            if os.getenv("FLASK_ENV") == "development":
                print("⚠️  Development mode: Using mock Google AI")
                self._mock_mode = True
                self.translate_client = None
                self._genai = None
                return
            else:
                raise ExternalServiceError("Google", "API key not configured")

        # Initialize only if not in mock mode AND we have API key
        try:
            # Configure Gemini with the API key
            genai.configure(api_key=self.api_key)

            # Initialize translation client ONLY if credentials exist
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path and os.path.exists(credentials_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                self.translate_client = translate.Client()
            else:
                print("⚠️  Google Translate credentials not found, using mock")
                self.translate_client = None

            logger.info("Google provider initialized successfully")

        except Exception as e:
            logger.error(f"Google provider initialization failed: {e}")
            if os.getenv("FLASK_ENV") == "development":
                print(f"⚠️  Google init failed, using mock: {e}")
                self._mock_mode = True
                self.translate_client = None
                self._genai = None
            else:
                raise

    def generate_text(
        self,
        prompt: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> str:
        """Generate text with mock in development."""
        if self._mock_mode:
            print(f"🔧 [MOCK] Google Gemini called with prompt: {prompt[:50]}...")
            # Return mock response
            mock_responses = [
                "This is a mock AI-generated response for development.",
                f"Mock response for: {prompt[:30]}...",
                "Generated title: Amazing Video Content",
                "Tags: education, tutorial, learning, video, content",
                "Description: A comprehensive video about the topic.",
            ]
            return mock_responses[len(prompt) % len(mock_responses)]

        """
        Generate text using Gemini models.

        Args:
            prompt: Input prompt
            model: Gemini model to use
            temperature: Creativity parameter
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model parameters

        Returns:
            Generated text
      """
        try:
            model_instance = genai.GenerativeModel(model)

            response = model_instance.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature, max_output_tokens=max_tokens, **kwargs
                ),
            )

            return response.text

        except Exception as e:
            logger.error(f"Google Gemini generation failed: {str(e)}")
            raise ExternalServiceError("Google", str(e))

    def analyze_image(
        self, image_path: str, features: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Analyze image with mock in development."""
        if self._mock_mode:
            print(f"🔧 [MOCK] Google Vision analyzing: {image_path}")
            return {
                "description": "Mock image analysis: Contains various elements suitable for video thumbnail.",
                "objects": ["person", "background", "text"],
                "colors": ["blue", "white", "black"],
                "labels": ["professional", "clean", "modern"],
                "cost": 0.0,
            }
        """
        Analyze image using Google Vision.

        Args:
            image_path: Path to image file
            features: List of features to analyze

        Returns:
            Analysis results
        """
        try:
            # For now, using Gemini Vision
            # In production, use Google Cloud Vision API

            with open(image_path, "rb") as image_file:
                image_data = image_file.read()

            model = genai.GenerativeModel("gemini-1.5-pro-vision")

            response = model.generate_content(
                [
                    "Analyze this image in detail. Provide:",
                    "1. Main objects and subjects",
                    "2. Colors and lighting",
                    "3. Scene description",
                    "4. Possible context or activity",
                    image_data,
                ]
            )

            # Parse response
            analysis_text = response.text

            # Simple parsing (in production, use structured output)
            return {
                "description": analysis_text,
                "objects": self._extract_objects(analysis_text),
                "colors": self._extract_colors(analysis_text),
                "labels": self._extract_labels(analysis_text),
                "cost": 0.0025,  # Approximate cost
            }

        except Exception as e:
            logger.error(f"Google Vision analysis failed: {str(e)}")
            raise ExternalServiceError("Google", str(e))

    def translate_text(
        self, text: str, target_language: str, source_language: str = "auto"
    ) -> str:
        """Translate text with mock in development."""
        if self._mock_mode or self.translate_client is None:
            print(f"🔧 [MOCK] Translate '{text[:30]}...' to {target_language}")
            # Return mock translation
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
        # Simple keyword extraction
        # In production, use NLP or structured output
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

        return found_objects[:10]  # Limit to 10 objects

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
            "pastel",
            "neutral",
        ]

        found_colors = []
        for color in colors:
            if color in analysis_text.lower():
                found_colors.append(color)

        return found_colors[:5]  # Limit to 5 colors

    def _extract_labels(self, analysis_text: str) -> List[str]:
        """Extract labels from analysis text."""
        # Extract key phrases (simple approach)
        sentences = analysis_text.split(".")
        labels = []

        for sentence in sentences[:5]:  # First 5 sentences
            sentence = sentence.strip()
            if sentence and len(sentence.split()) <= 10:
                labels.append(sentence)

        return labels

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available Google AI models."""
        try:
            models = genai.list_models()

            available_models = []
            for model in models:
                if "generateContent" in model.supported_generation_methods:
                    available_models.append(
                        {
                            "name": model.name,
                            "display_name": model.display_name,
                            "description": model.description,
                            "input_token_limit": model.input_token_limit,
                            "output_token_limit": model.output_token_limit,
                        }
                    )

            return available_models

        except Exception as e:
            logger.error(f"Failed to fetch Google AI models: {str(e)}")
            return []

    def get_supported_languages(self) -> Dict[str, str]:
        """Get supported languages for translation."""
        try:
            languages = self.translate_client.get_languages()

            language_dict = {}
            for lang in languages:
                language_dict[lang["language"]] = lang["name"]

            return language_dict

        except Exception as e:
            logger.error(f"Failed to fetch supported languages: {str(e)}")
            return {}

    def test_connection(self) -> bool:
        """Test Google AI API connection."""
        try:
            # Try to list models
            genai.list_models(limit=1)
            return True
        except Exception as e:
            logger.error(f"Google AI connection test failed: {str(e)}")
            return False
