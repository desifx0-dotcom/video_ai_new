"""OpenAI API provider with retry, timeout, and mock mode support."""

import os
import time
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from core.exceptions import ExternalServiceError
from core.logging import logger


class OpenAIProvider:
    """OpenAI API provider with retry, timeout, and mock mode."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout

        # Check mock mode from environment
        self._mock_mode = os.getenv("OPENAI_MOCK_MODE", "false").lower() == "true"

        # If mock mode is explicitly enabled
        if self._mock_mode:
            print(
                "🔧 [MOCK] Using mock OpenAI (no API calls) - enabled by OPENAI_MOCK_MODE=true"
            )
            self.client = None
            return

        # Check if API key is valid
        if (
            not self.api_key
            or self.api_key == "mock-key"
            or "test" in str(self.api_key)
            or self.api_key == "sk-test-key"
        ):
            print("🔧 [MOCK] Using mock OpenAI (no valid API key)")
            self._mock_mode = True
            self.client = None
            return

        try:
            self.client = OpenAI(api_key=self.api_key, timeout=timeout)
            print("✅ OpenAI client initialized")
        except Exception as e:
            print(f"⚠️ OpenAI initialization failed: {e}")
            self._mock_mode = True
            self.client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ExternalServiceError),
    )
    def transcribe_audio(self, audio_path: str, language: str = "en") -> str:
        """Transcribe audio using Whisper API with retry and billing fallback."""

        # Check mock mode first
        if self._mock_mode or not self.client:
            print(f"🔊 [MOCK] Transcribing {audio_path}")
            return "This is a mock transcription for development. In production, this would be the actual transcribed text."

        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="text",
                )
            return transcript

        except Exception as e:
            error_msg = str(e).lower()

            # CRITICAL: Detect billing/quota issues and fallback to mock
            if any(
                x in error_msg
                for x in ["billing", "quota", "insufficient_quota", "429"]
            ):
                logger.warning(f"OpenAI billing/quota issue detected: {e}")
                print(f"⚠️ OpenAI API has billing/quota issues. Switching to MOCK mode.")
                self._mock_mode = True
                # Retry with mock
                return self.transcribe_audio(audio_path, language)

            logger.error(f"OpenAI transcription failed: {e}")
            raise ExternalServiceError("OpenAI", f"Transcription failed: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ExternalServiceError),
    )
    def generate_text(self, prompt: str, model: str = "gpt-3.5-turbo", **kwargs) -> str:
        """Generate text using GPT models with retry and fallback."""

        if self._mock_mode or not self.client:
            print(f"🤖 [MOCK] Generating text with prompt: {prompt[:50]}...")
            mock_responses = {
                "gpt-4-turbo": "This is a high-quality mock response.",
                "gpt-4": "This is a mock response from GPT-4 for development.",
                "gpt-3.5-turbo": "This is a mock response from GPT-3.5 Turbo for development.",
                "gpt-4o-mini": "This is a mock response from GPT-4o Mini for development.",
            }
            return mock_responses.get(model, f"Mock AI response to: {prompt[:100]}...")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=self.timeout,
                **kwargs,
            )
            return response.choices[0].message.content

        except Exception as e:
            error_msg = str(e).lower()

            # if we have api key but not billing than Detect billing/quota issues and fallback to mock
            if any(
                x in error_msg
                for x in ["billing", "quota", "insufficient_quota", "429", "rate_limit"]
            ):
                logger.warning(f"OpenAI billing/quota issue detected: {e}")
                print(f"⚠️ OpenAI API has billing/quota issues. Switching to MOCK mode.")
                self._mock_mode = True
                # Retry with mock
                return self.generate_text(prompt, model, **kwargs)

            logger.error(f"OpenAI text generation failed with model {model}: {e}")
            raise ExternalServiceError("OpenAI", f"Text generation failed: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ExternalServiceError),
    )
    def generate_image(
        self,
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        quality: str = "standard",
        **kwargs,
    ) -> str:
        """Generate image using DALL-E with retry."""
        if self._mock_mode or not self.client:
            print(f"🎨 [MOCK] Generating image with prompt: {prompt[:50]}...")
            return "https://mock-image-url.com/placeholder.jpg"

        try:
            response = self.client.images.generate(
                model=model, prompt=prompt, size=size, quality=quality, n=1, **kwargs
            )
            return response.data[0].url

        except Exception as e:
            logger.error(f"OpenAI image generation failed: {e}")
            raise ExternalServiceError("OpenAI", f"Image generation failed: {str(e)}")

    def check_availability(self) -> bool:
        """Check if OpenAI API is available."""
        if self._mock_mode or self.client is None:
            return False

        try:
            self.client.models.list(limit=1)
            return True
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {str(e)}")
            return False

    def get_available_models(self) -> list:
        """Get list of available models."""
        if self._mock_mode or not self.client:
            return ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o-mini", "dall-e-3"]

        try:
            models = self.client.models.list()
            available = []
            for model in models:
                if any(m in model.id for m in ["gpt", "dall-e", "whisper"]):
                    available.append(model.id)
            return available[:20]
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]
