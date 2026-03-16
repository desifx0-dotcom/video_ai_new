"""
Unit tests for OpenAI provider.
"""
import pytest
from unittest.mock import Mock, patch

from src.providers.openai_provider import OpenAIProvider
from src.core.exceptions import ExternalServiceError

class TestOpenAIProvider:
    """Test OpenAIProvider class."""
    
    def test_transcribe_success(self):
        """Test successful transcription."""
        # Test implementation...
        pass
    
    # More tests for other methods...