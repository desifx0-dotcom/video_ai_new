"""
Stability AI provider for image generation with mock mode support.
Updated with correct model endpoints and all required methods.
"""

import os
import logging
import base64
from typing import Dict, Any, Optional, List
import requests
import time

from core.exceptions import ExternalServiceError
from core.domain.value_objects.tier import Tier

logger = logging.getLogger(__name__)


class StabilityProvider:
    """Stability AI provider for image generation with mock mode."""

    # Correct model name mapping for API endpoints
    MODEL_ENDPOINTS = {
        "sdxl-turbo": "stable-diffusion-xl-1024-v1-0",  # SDXL Turbo uses same endpoint
        "sdxl": "stable-diffusion-xl-1024-v1-0",
        "ultra": "stable-diffusion-3-ultra",
        "core": "stable-image-core/sd3.5",
    }

    # Step limits per model
    STEP_LIMITS = {
        "sdxl-turbo": {
            "min": 4,
            "max": 8,
            "default": 8,
            "note": "Turbo models have max 8 steps",
        },
        "sdxl": {"min": 10, "max": 40, "default": 20},
        "ultra": {"min": 20, "max": 60, "default": 40},
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("STABILITY_API_KEY")

        # Clean up any whitespace
        if self.api_key:
            self.api_key = self.api_key.strip()

        # Check for explicit mock mode from environment
        self._mock_mode = os.getenv("STABILITY_MOCK_MODE", "false").lower() == "true"

        # If not explicitly in mock mode, try to use real API
        if not self._mock_mode:
            # Check if we have a valid-looking API key
            if not self.api_key:
                print("⚠️ Stability AI API key missing, using mock mode")
                self._mock_mode = True
            elif len(self.api_key) < 20:
                print(
                    f"⚠️ Stability AI API key too short ({len(self.api_key)} chars), using mock mode"
                )
                self._mock_mode = True
            elif self.api_key == "mock-key" or self.api_key == "sk-test-key":
                print("⚠️ Stability AI using test key, using mock mode")
                self._mock_mode = True
            else:
                # Valid API key, initialize real client
                self.base_url = "https://api.stability.ai/v1"
                self.headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                }
                print(
                    f"✅ Stability AI client initialized (key length: {len(self.api_key)})"
                )

        if self._mock_mode:
            print("🔧 [MOCK] Using mock Stability AI (no real API calls)")

    def generate_image(
        self,
        prompt: str,
        model: str = "sdxl",
        steps: int = 20,
        cfg_scale: float = 7.0,
        width: int = 1280,
        height: int = 720,
        negative_prompt: Optional[str] = None,
        style_preset: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """Generate image using Stability AI."""

        if self._mock_mode:
            print(
                f"🎨 [MOCK] Stability AI generating image with prompt: {prompt[:50]}..."
            )
            print(f"   Model: {model}, Steps: {steps}, Size: {width}x{height}")
            return self._get_mock_image()

        try:
            # Get step limits for this model
            step_limits = self.STEP_LIMITS.get(
                model, {"min": 10, "max": 40, "default": 20}
            )

            # Clamp steps to valid range
            if steps < step_limits["min"]:
                logger.warning(
                    f"Steps ({steps}) below minimum {step_limits['min']}, setting to {step_limits['min']}"
                )
                steps = step_limits["min"]
            if steps > step_limits["max"]:
                logger.warning(
                    f"Steps ({steps}) above maximum {step_limits['max']}, setting to {step_limits['max']}"
                )
                steps = step_limits["max"]

            # Ensure dimensions are valid
            width = max(512, min(2048, width))
            height = max(512, min(2048, height))

            # For SDXL, ensure dimensions are multiples of 64
            if model in ["sdxl-turbo", "sdxl"]:
                width = ((width + 63) // 64) * 64
                height = ((height + 63) // 64) * 64

            # Map model name to API endpoint
            endpoint = self.MODEL_ENDPOINTS.get(model, "stable-diffusion-xl-1024-v1-0")
            url = f"{self.base_url}/generation/{endpoint}/text-to-image"

            logger.info(
                f"Generating image: model={model}, steps={steps}, size={width}x{height}"
            )

            # Prepare request data
            data = {
                "text_prompts": [{"text": prompt, "weight": 1.0}],
                "cfg_scale": cfg_scale,
                "height": height,
                "width": width,
                "samples": 1,
                "steps": steps,
                **kwargs,
            }

            if negative_prompt:
                data["text_prompts"].append({"text": negative_prompt, "weight": -1.0})

            if style_preset:
                data["style_preset"] = style_preset

            response = requests.post(url, headers=self.headers, json=data, timeout=60)

            if response.status_code != 200:
                error_msg = (
                    f"Stability AI API error: {response.status_code} - {response.text}"
                )
                logger.error(error_msg)

                # Don't fall back to mock mode on API errors - raise exception
                raise ExternalServiceError("StabilityAI", error_msg)

            response_json = response.json()

            if not response_json.get("artifacts"):
                raise ExternalServiceError("StabilityAI", "No image generated")

            image_data = base64.b64decode(response_json["artifacts"][0]["base64"])
            logger.info(f"✅ Image generated successfully ({len(image_data)} bytes)")
            return image_data

        except requests.exceptions.Timeout:
            logger.error("Stability AI request timeout")
            raise ExternalServiceError("StabilityAI", "Request timeout")
        except Exception as e:
            logger.error(f"Stability AI image generation failed: {str(e)}")
            raise ExternalServiceError("StabilityAI", str(e))

    def _get_mock_image(self) -> bytes:
        """Generate a mock image for development."""
        import base64

        # 1x1 transparent PNG
        mock_png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        return base64.b64decode(mock_png_base64)

    def upscale_image(
        self,
        image_bytes: bytes,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bytes:
        """Upscale image using Stability AI."""
        if self._mock_mode:
            print(f"🖼️ [MOCK] Stability AI upscaling image to {width}x{height}")
            return image_bytes

        try:
            url = f"{self.base_url}/image-to-image/upscale"
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            target_width = ((width or 2048) + 63) // 64 * 64 if width else 2048
            target_height = ((height or 2048) + 63) // 64 * 64 if height else 2048

            target_width = max(512, min(2048, target_width))
            target_height = max(512, min(2048, target_height))

            data = {
                "image": image_b64,
                "width": target_width,
                "height": target_height,
            }

            response = requests.post(url, headers=self.headers, json=data, timeout=30)

            if response.status_code != 200:
                error_msg = f"Stability AI upscale error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise ExternalServiceError("StabilityAI", error_msg)

            response_json = response.json()

            if not response_json.get("artifacts"):
                raise ExternalServiceError("StabilityAI", "No upscaled image generated")

            upscaled_data = base64.b64decode(response_json["artifacts"][0]["base64"])
            logger.info(f"✅ Image upscaled successfully ({len(upscaled_data)} bytes)")
            return upscaled_data

        except Exception as e:
            logger.error(f"Stability AI upscale failed: {str(e)}")
            if not self._mock_mode:
                logger.warning("Falling back to original image")
            return image_bytes

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available Stability AI models."""
        if self._mock_mode:
            return [
                {
                    "id": "sdxl-turbo",
                    "name": "SDXL Turbo",
                    "type": "text-to-image",
                    "description": "Fast and cheap",
                },
                {
                    "id": "sdxl",
                    "name": "SDXL",
                    "type": "text-to-image",
                    "description": "High quality",
                },
                {
                    "id": "ultra",
                    "name": "SD3 Ultra",
                    "type": "text-to-image",
                    "description": "Best quality",
                },
            ]

        try:
            url = f"{self.base_url}/engines/list"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                return []

            engines = response.json()
            available_models = []
            for engine in engines:
                available_models.append(
                    {
                        "id": engine.get("id"),
                        "name": engine.get("name"),
                        "description": engine.get("description"),
                        "type": engine.get("type"),
                    }
                )
            return available_models

        except Exception as e:
            logger.error(f"Failed to fetch Stability AI models: {str(e)}")
            return []

    def get_balance(self) -> Dict[str, Any]:
        """Get API balance/credits."""
        if self._mock_mode:
            return {"credits": 999999, "credits_used": 0, "mock_mode": True}

        try:
            url = f"{self.base_url}/user/balance"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                return {"error": "Failed to get balance"}

            balance_data = response.json()
            return {
                "credits": balance_data.get("credits", 0),
                "credits_used": balance_data.get("credits_used", 0),
                "rate_limits": balance_data.get("rate_limits", {}),
            }

        except Exception as e:
            logger.error(f"Failed to get Stability AI balance: {str(e)}")
            return {"error": str(e)}

    def estimate_cost(
        self, steps: int, width: int, height: int, model: str = "sdxl"
    ) -> float:
        """Estimate cost for image generation."""
        cost_per_step = {
            "sdxl-turbo": 0.00005,
            "sdxl": 0.0002,
            "ultra": 0.0005,
        }
        base_cost = steps * cost_per_step.get(model, 0.0001)
        resolution_multiplier = (width * height) / (1024 * 1024)
        return base_cost * resolution_multiplier

    def test_connection(self) -> bool:
        """Test Stability AI API connection."""
        if self._mock_mode:
            return True

        try:
            balance = self.get_balance()
            return "credits" in balance
        except Exception as e:
            logger.error(f"Stability AI connection test failed: {str(e)}")
            return False
