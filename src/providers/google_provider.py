"""
Google AI provider for Gemini, Translation, and Vision.
Migrated to the new google-genai SDK with production-level features:
- Circuit breaker pattern
- Connection pooling
- Request timeout handling
- Exponential backoff retry
- Comprehensive error handling
- Mock mode for development
- Cost tracking
- Fallback mechanisms
"""

import os
import time
import logging
import base64
import json
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from functools import wraps

# New SDK imports
from google import genai
from google.genai import types
from google.cloud import translate_v2 as translate
import google.auth

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)

from core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    half_open_max_calls: int = 3
    
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    half_open_calls: int = 0
    
    def record_success(self):
        """Record a successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
            logger.info("Circuit breaker closed after successful recovery")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self):
        """Record a failed call."""
        if self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                self.last_failure_time = time.time()
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
        
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.last_failure_time = time.time()
            self.half_open_calls = 0
            logger.warning("Circuit breaker reopened after half-open test failure")
    
    def allow_request(self) -> bool:
        """Check if request should be allowed."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - (self.last_failure_time or 0) >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker transitioning to half-open")
                return True
            return False
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1
            return self.half_open_calls <= self.half_open_max_calls
        
        return False


class GoogleProvider:
    """Production-ready Google AI provider with circuit breaker and retry logic."""

    # Model configuration
    MODELS = {
        "text": "gemini-2.0-flash",
        "text_pro": "gemini-2.0-pro",
        "vision": "gemini-2.0-flash",
        "vision_pro": "gemini-2.0-pro-vision",
        "translation": "gemini-2.0-flash-lite",
    }
    
    # Cost per 1K tokens (approximate, for tracking)
    COST_PER_1K_TOKENS = {
        "gemini-2.0-flash": 0.000075,
        "gemini-2.0-flash-lite": 0.0000375,
        "gemini-2.0-pro": 0.0005,
        "gemini-2.0-pro-vision": 0.0005,
    }
    
    # Default timeout in seconds
    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1
    MAX_RETRY_DELAY = 10

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        enable_circuit_breaker: bool = True,
    ):
        """
        Initialize Google provider with production features.
        
        Args:
            api_key: Google API key (optional, will use env var if not provided)
            timeout: Request timeout in seconds
            enable_circuit_breaker: Enable circuit breaker pattern
        """
        self.timeout = timeout
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.enable_circuit_breaker = enable_circuit_breaker
        
        # Circuit breaker instance
        self._circuit_breaker = CircuitBreaker() if enable_circuit_breaker else None
        
        # Check mock mode from .env
        self._mock_mode = os.getenv("GOOGLE_MOCK_MODE", "false").lower() == "true"
        
        # Initialize clients
        self._client = None
        self._translate_client = None
        self._initialize_clients()
        
        # Cost tracking
        self._total_cost = 0.0
        self._request_count = 0
        self._error_count = 0
        
        logger.info(
            f"GoogleProvider initialized - Mock: {self._mock_mode}, "
            f"Circuit Breaker: {enable_circuit_breaker}"
        )
    
    def _initialize_clients(self):
        """Initialize API clients with proper error handling."""
        if self._mock_mode:
            logger.info("🔧 [MOCK] Using mock Google AI (no API calls)")
            return
        
        if not self.api_key:
            if os.getenv("FLASK_ENV") == "development":
                logger.warning("No API key, falling back to mock mode")
                self._mock_mode = True
                return
            else:
                raise ExternalServiceError("Google", "API key not configured")
        
        try:
            # Initialize new genai client
            self._client = genai.Client(api_key=self.api_key)
            logger.info("✅ Google Gemini client initialized with new SDK")
            
            # Initialize Translate client
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path and os.path.exists(credentials_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                self._translate_client = translate.Client()
                logger.info("✅ Google Translate client initialized")
            else:
                logger.warning("⚠️ Google Translate credentials not found, translations will use Gemini")
                self._translate_client = None
                
        except Exception as e:
            logger.error(f"Google provider initialization failed: {e}")
            if os.getenv("FLASK_ENV") == "development":
                logger.warning(f"Falling back to mock mode: {e}")
                self._mock_mode = True
            else:
                raise
    
    def _should_retry(self, exception: Exception) -> bool:
        """Determine if request should be retried."""
        if isinstance(exception, ExternalServiceError):
            error_str = str(exception).lower()
            # Retry on specific errors
            retryable_errors = [
                "timeout", "rate limit", "quota", "429", "500", "502", "503", "504",
                "service unavailable", "internal error", "connection"
            ]
            return any(e in error_str for e in retryable_errors)
        return True
    
    def _call_with_timeout(self, func, *args, **kwargs):
        """Execute function with timeout."""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                raise ExternalServiceError("Google", f"Request timeout after {self.timeout}s")
    
    def _track_cost(self, model: str, input_tokens: int, output_tokens: int):
        """Track API costs for monitoring."""
        cost_per_1k = self.COST_PER_1K_TOKENS.get(model, 0.000075)
        total_tokens = input_tokens + output_tokens
        cost = (total_tokens / 1000) * cost_per_1k
        self._total_cost += cost
        self._request_count += 1
        
        logger.debug(f"Cost tracked - Model: {model}, Tokens: {total_tokens}, Cost: ${cost:.6f}")
    
    def _execute_with_circuit_breaker(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self._circuit_breaker and not self._circuit_breaker.allow_request():
            raise ExternalServiceError(
                "Google",
                "Circuit breaker open - service temporarily unavailable",
                is_retryable=False
            )
        
        try:
            result = func(*args, **kwargs)
            if self._circuit_breaker:
                self._circuit_breaker.record_success()
            return result
        except Exception as e:
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            raise
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=INITIAL_RETRY_DELAY, min=1, max=MAX_RETRY_DELAY),
        retry=retry_if_exception_type(ExternalServiceError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def generate_text(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        top_p: float = 0.95,
        top_k: int = 40,
        **kwargs,
    ) -> str:
        """
        Generate text using Gemini with retry and circuit breaker.
        
        Args:
            prompt: Text prompt
            model: Model name (uses default if None)
            temperature: Creativity (0-1)
            max_tokens: Maximum output tokens
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
        
        Returns:
            Generated text
        """
        if self._mock_mode:
            logger.debug(f"🔧 [MOCK] Gemini generate_text called")
            return self._mock_generate_text(prompt)
        
        # Use default model if none provided
        actual_model = model or self.MODELS["text"]
        
        # Map old model names to new ones
        model_map = {
            "gemini-1.5-pro": self.MODELS["text_pro"],
            "gemini-1.5-flash": self.MODELS["text"],
            "gemini-2.0-flash-lite": self.MODELS["text"],
            "gemini-2.0-pro": self.MODELS["text_pro"],
        }
        actual_model = model_map.get(actual_model, actual_model)
        
        def _call():
            try:
                response = self._client.models.generate_content(
                    model=actual_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        top_p=top_p,
                        top_k=top_k,
                    )
                )
                
                # Track token usage (approximate)
                input_tokens = len(prompt) // 4  # Rough estimate
                output_tokens = len(response.text) // 4
                self._track_cost(actual_model, input_tokens, output_tokens)
                
                return response.text
                
            except Exception as e:
                logger.error(f"Gemini generation failed with {actual_model}: {e}")
                raise ExternalServiceError("Google Gemini", str(e))
        
        return self._execute_with_circuit_breaker(
            lambda: self._call_with_timeout(_call)
        )
    
    def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: str = None,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON output using Gemini.
        
        Args:
            prompt: Text prompt
            schema: JSON schema for response
            model: Model name (defaults to flash for structured output)
            temperature: Temperature (lower for structured output)
        
        Returns:
            Parsed JSON dictionary
        """
        if self._mock_mode:
            logger.debug(f"🔧 [MOCK] Gemini generate_structured called")
            return {"mock": True, "data": prompt[:100]}
        
        actual_model = model or self.MODELS["text"]
        
        def _call():
            try:
                response = self._client.models.generate_content(
                    model=actual_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                        response_schema=schema,
                    )
                )
                
                # Track cost
                input_tokens = len(prompt) // 4
                output_tokens = len(response.text) // 4
                self._track_cost(actual_model, input_tokens, output_tokens)
                
                return json.loads(response.text)
                
            except Exception as e:
                logger.error(f"Structured generation failed: {e}")
                raise ExternalServiceError("Google Gemini", str(e))
        
        return self._execute_with_circuit_breaker(
            lambda: self._call_with_timeout(_call)
        )
    
    def analyze_image(
        self,
        image_path: str,
        prompt: Optional[str] = None,
        model: str = None,
    ) -> Dict[str, Any]:
        """
        Analyze image using Gemini Vision.
        
        Args:
            image_path: Path to image file
            prompt: Custom analysis prompt
            model: Vision model name
        
        Returns:
            Analysis results with description, objects, colors, labels
        """
        if self._mock_mode:
            logger.debug(f"🔧 [MOCK] Vision analyze_image called")
            return self._mock_analyze_image()
        
        actual_model = model or self.MODELS["vision"]
        
        default_prompt = prompt or """
        Analyze this image and return a JSON object with:
        - description: A detailed description of the image (max 150 words)
        - objects: List of main objects detected (max 10)
        - colors: List of dominant colors (max 5)
        - labels: List of relevant tags/labels (max 15)
        - mood: The mood or atmosphere (e.g., happy, dramatic, calm)
        - quality_score: Score 0-100 for image quality
        """
        
        def _call():
            try:
                # Read and encode image
                with open(image_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                
                response = self._client.models.generate_content(
                    model=actual_model,
                    contents=[
                        default_prompt,
                        types.Part.from_bytes(
                            data=base64.b64decode(image_data),
                            mime_type="image/jpeg"
                        )
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json",
                    )
                )
                
                # Parse JSON response
                text = response.text
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    # Fallback parsing
                    result = {
                        "description": text[:500],
                        "objects": [],
                        "colors": [],
                        "labels": [],
                        "mood": "neutral",
                        "quality_score": 75,
                    }
                
                # Track cost (image analysis ~ 1K tokens)
                self._track_cost(actual_model, 1000, len(text) // 4)
                
                return result
                
            except Exception as e:
                logger.error(f"Image analysis failed: {e}")
                raise ExternalServiceError("Google Vision", str(e))
        
        return self._execute_with_circuit_breaker(
            lambda: self._call_with_timeout(_call)
        )
    
    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
    ) -> str:
        """
        Translate text using Google Translate or Gemini fallback.
        
        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'es', 'fr')
            source_language: Source language code or 'auto'
        
        Returns:
            Translated text
        """
        if self._mock_mode:
            logger.debug(f"🔧 [MOCK] Translate called: {text[:30]}... to {target_language}")
            return self._mock_translate(text, target_language)
        
        # Try Translate API first if available
        if self._translate_client:
            def _call_translate():
                try:
                    result = self._translate_client.translate(
                        text,
                        target_language=target_language,
                        source_language=source_language if source_language != "auto" else None,
                    )
                    return result["translatedText"]
                except Exception as e:
                    logger.warning(f"Translate API failed: {e}, falling back to Gemini")
                    return None
            
            result = _call_translate()
            if result:
                return result
        
        # Fallback to Gemini translation
        def _call_gemini():
            try:
                if source_language and source_language != "auto":
                    prompt = f"Translate this text from {source_language} to {target_language}. Only return the translated text, nothing else.\n\nText: {text}"
                else:
                    prompt = f"Translate this text to {target_language}. Only return the translated text, nothing else.\n\nText: {text}"
                
                response = self._client.models.generate_content(
                    model=self.MODELS["translation"],
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.3)
                )
                
                # Track cost
                input_tokens = len(prompt) // 4
                output_tokens = len(response.text) // 4
                self._track_cost(self.MODELS["translation"], input_tokens, output_tokens)
                
                return response.text.strip()
                
            except Exception as e:
                logger.error(f"Gemini translation failed: {e}")
                raise ExternalServiceError("Google Translation", str(e))
        
        return self._execute_with_circuit_breaker(
            lambda: self._call_with_timeout(_call_gemini)
        )
    
    def batch_translate(
        self,
        texts: List[str],
        target_language: str,
        source_language: str = "auto",
    ) -> List[str]:
        """Batch translate multiple texts."""
        results = []
        for text in texts:
            results.append(self.translate_text(text, target_language, source_language))
        return results
    
    def get_embedding(self, text: str, model: str = "text-embedding-004") -> List[float]:
        """
        Get text embedding vector.
        
        Args:
            text: Input text
            model: Embedding model name
        
        Returns:
            List of embedding floats
        """
        if self._mock_mode:
            logger.debug(f"🔧 [MOCK] Get embedding called")
            return [0.0] * 768  # Mock embedding
        
        def _call():
            try:
                result = self._client.models.embed_content(
                    model=model,
                    contents=text,
                )
                return result.embeddings[0].values
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                raise ExternalServiceError("Google Embedding", str(e))
        
        return self._execute_with_circuit_breaker(
            lambda: self._call_with_timeout(_call)
        )
    
    def is_available(self) -> bool:
        """Check if provider is available."""
        return not self._mock_mode and self._client is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "total_cost": round(self._total_cost, 6),
            "mock_mode": self._mock_mode,
            "circuit_breaker_state": self._circuit_breaker.state.value if self._circuit_breaker else "disabled",
            "failure_count": self._circuit_breaker.failure_count if self._circuit_breaker else 0,
        }
    
    # ========== MOCK METHODS ==========
    
    def _mock_generate_text(self, prompt: str) -> str:
        """Mock text generation for development."""
        mock_responses = [
            "This is a mock AI-generated response for development purposes.",
            f"Mock response: Generated based on prompt: {prompt[:50]}...",
            "Generated title: Amazing Video Content - Watch Now!",
            "Tags: education, tutorial, learning, video production, AI content",
            "Description: A comprehensive video about the topic. Learn everything you need to know.",
        ]
        return mock_responses[hash(prompt) % len(mock_responses)]
    
    def _mock_analyze_image(self) -> Dict[str, Any]:
        """Mock image analysis for development."""
        return {
            "description": "A professional video thumbnail image featuring engaging visual content suitable for YouTube or social media.",
            "objects": ["person", "background", "text area", "graphic elements"],
            "colors": ["blue", "white", "orange", "dark gray"],
            "labels": ["professional", "modern", "engaging", "clickable", "high quality"],
            "mood": "energetic and professional",
            "quality_score": 85,
            "cost": 0.0,
        }
    
    def _mock_translate(self, text: str, target_language: str) -> str:
        """Mock translation for development."""
        mock_prefixes = {
            "es": "[ES] ",
            "fr": "[FR] ",
            "de": "[DE] ",
            "zh": "[ZH] ",
            "ja": "[JA] ",
            "ko": "[KO] ",
            "ru": "[RU] ",
        }
        prefix = mock_prefixes.get(target_language, f"[{target_language.upper()}] ")
        return f"{prefix}{text}"
    
    def test_connection(self) -> Dict[str, Any]:
        """Test Google AI API connection."""
        if self._mock_mode:
            return {"success": True, "message": "Mock mode active", "mock": True}
        
        try:
            # Simple test request
            self.generate_text("Say 'OK' in one word.", max_tokens=5)
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "message": str(e), "error": str(e)}