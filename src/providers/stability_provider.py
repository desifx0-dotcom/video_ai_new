"""
Stability AI provider for image generation.
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
    """Stability AI provider for image generation."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('STABILITY_API_KEY')
        
        if not self.api_key:
            raise ExternalServiceError("StabilityAI", "API key not configured")
        
        self.base_url = "https://api.stability.ai/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
    
    def generate_image(
        self,
        prompt: str,
        model: str = "sd-3.5-medium",
        steps: int = 30,
        cfg_scale: float = 7.0,
        width: int = 1024,
        height: int = 1024,
        negative_prompt: Optional[str] = None,
        style_preset: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Generate image using Stability AI.
        
        Args:
            prompt: Text prompt for image generation
            model: Model to use
            steps: Number of diffusion steps
            cfg_scale: Guidance scale
            width: Image width
            height: Image height
            negative_prompt: Negative prompt
            style_preset: Style preset
            **kwargs: Additional parameters
        
        Returns:
            Image bytes
        """
        try:
            # Map model names to API endpoints
            model_endpoints = {
                'sd-3.5-medium': 'stable-diffusion-v3-medium',
                'sd-xl': 'stable-diffusion-xl-1024-v1-0',
                'sd-3.6-turbo': 'stable-diffusion-3.5-turbo'
            }
            
            endpoint = model_endpoints.get(model, 'stable-diffusion-v3-medium')
            
            url = f"{self.base_url}/generation/{endpoint}/text-to-image"
            
            # Prepare request data
            data = {
                "text_prompts": [
                    {
                        "text": prompt,
                        "weight": 1.0
                    }
                ],
                "cfg_scale": cfg_scale,
                "height": height,
                "width": width,
                "samples": 1,
                "steps": steps,
                **kwargs
            }
            
            if negative_prompt:
                data["text_prompts"].append({
                    "text": negative_prompt,
                    "weight": -1.0
                })
            
            if style_preset:
                data["style_preset"] = style_preset
            
            # Make request
            response = requests.post(
                url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"Stability AI API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise ExternalServiceError("StabilityAI", error_msg)
            
            # Parse response
            response_json = response.json()
            
            if not response_json.get("artifacts"):
                raise ExternalServiceError("StabilityAI", "No image generated")
            
            # Get first image
            image_data = base64.b64decode(response_json["artifacts"][0]["base64"])
            
            return image_data
            
        except requests.exceptions.Timeout:
            logger.error("Stability AI request timeout")
            raise ExternalServiceError("StabilityAI", "Request timeout")
        except Exception as e:
            logger.error(f"Stability AI image generation failed: {str(e)}")
            raise ExternalServiceError("StabilityAI", str(e))
    
    def upscale_image(
        self,
        image_bytes: bytes,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> bytes:
        """
        Upscale image using Stability AI.
        
        Args:
            image_bytes: Original image bytes
            width: Target width
            height: Target height
        
        Returns:
            Upscaled image bytes
        """
        try:
            url = f"{self.base_url}/image-to-image/upscale"
            
            # Encode image
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            data = {
                "image": image_b64,
                "width": width or 2048,
                "height": height or 2048
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"Stability AI upscale error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise ExternalServiceError("StabilityAI", error_msg)
            
            response_json = response.json()
            
            if not response_json.get("artifacts"):
                raise ExternalServiceError("StabilityAI", "No upscaled image generated")
            
            upscaled_data = base64.b64decode(response_json["artifacts"][0]["base64"])
            
            return upscaled_data
            
        except Exception as e:
            logger.error(f"Stability AI upscale failed: {str(e)}")
            raise ExternalServiceError("StabilityAI", str(e))
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available Stability AI models."""
        try:
            url = f"{self.base_url}/engines/list"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                return []
            
            engines = response.json()
            
            available_models = []
            for engine in engines:
                available_models.append({
                    'id': engine.get('id'),
                    'name': engine.get('name'),
                    'description': engine.get('description'),
                    'type': engine.get('type')
                })
            
            return available_models
            
        except Exception as e:
            logger.error(f"Failed to fetch Stability AI models: {str(e)}")
            return []
    
    def get_balance(self) -> Dict[str, Any]:
        """Get API balance/credits."""
        try:
            url = f"{self.base_url}/user/balance"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                return {'error': 'Failed to get balance'}
            
            balance_data = response.json()
            
            return {
                'credits': balance_data.get('credits', 0),
                'credits_used': balance_data.get('credits_used', 0),
                'rate_limits': balance_data.get('rate_limits', {})
            }
            
        except Exception as e:
            logger.error(f"Failed to get Stability AI balance: {str(e)}")
            return {'error': str(e)}
    
    def estimate_cost(
        self,
        steps: int,
        width: int,
        height: int,
        model: str = "sd-3.5-medium"
    ) -> float:
        """Estimate cost for image generation."""
        # Stability AI pricing (as of 2024)
        # Approximate costs per step
        cost_per_step = {
            'sd-3.5-medium': 0.0001,      # $0.0001 per step
            'sd-xl': 0.0002,              # $0.0002 per step
            'sd-3.6-turbo': 0.0003        # $0.0003 per step
        }
        
        base_cost = steps * cost_per_step.get(model, 0.0001)
        
        # Adjust for resolution
        resolution_multiplier = (width * height) / (1024 * 1024)  # Relative to 1024x1024
        
        return base_cost * resolution_multiplier
    
    def test_connection(self) -> bool:
        """Test Stability AI API connection."""
        try:
            # Try to get balance
            balance = self.get_balance()
            return 'credits' in balance
        except Exception as e:
            logger.error(f"Stability AI connection test failed: {str(e)}")
            return False