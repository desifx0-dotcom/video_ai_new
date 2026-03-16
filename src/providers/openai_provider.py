"""OpenAI API provider."""

import os
import time
from typing import Optional, Dict, Any
from openai import OpenAI
from core.exceptions import ExternalServiceError
from core.logging import logger


class OpenAIProvider:
    """OpenAI API provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        # Mock mode for development
        if (
            not self.api_key
            or self.api_key == "mock-key"
            or "test" in str(self.api_key)
        ):
            print("✅ Development mode: Using mock OpenAI")
            self.client = None  # Mock mode
            return

        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)

        # Rate limiting
        self.rate_limit_remaining = 60
        self.last_request_time = None

    def transcribe_audio(self, audio_path: str, language: str = "en") -> str:
        """Transcribe audio using Whisper API."""
        try:
            # Mock response for development
            if not self.client:
                print(f"🔊 [MOCK] Transcribing {audio_path}")
                return "This is a mock transcription for development. In a real scenario, this would be the transcribed text from the audio file."

            # Real transcription
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="text",
                )
            return transcript

        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}")
            raise ExternalServiceError("OpenAI", f"Transcription failed: {str(e)}")

    def generate_text(self, prompt: str, model: str = "gpt-3.5-turbo", **kwargs) -> str:
        """Generate text using GPT models."""
        try:
            # Mock response for development
            if not self.client:
                print(f"🤖 [MOCK] Generating text with prompt: {prompt[:50]}...")
                return f"Mock AI response to: {prompt[:100]}..."

            # Real generation
            response = self.client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], **kwargs
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI text generation failed: {e}")
            raise ExternalServiceError("OpenAI", f"Text generation failed: {str(e)}")

    def check_availability(self) -> bool:
        """Check if OpenAI API is available."""
        # Check if we're in mock mode
        if self.client is None:
            return False

        try:
            self.client.models.list(limit=1)
            return True
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {str(e)}")
            return False

    # def check_availability(self) -> bool:
    #     """Check if OpenAI API is available."""
    #     return self.client is not None
    #     # ."""
    #     try:
    #         self.client.models.list(limit=1)
    #         return True
    #     except Exception as e:
    #         logger.error(f"OpenAI connection test failed: {str(e)}")
    #         return False
