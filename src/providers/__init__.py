"""
External service providers package.
"""
from .openai_provider import OpenAIProvider
from .google_provider import GoogleProvider
from .stability_provider import StabilityProvider
from .stripe_provider import StripeProvider
from .ffmpeg_provider import FFmpegProvider
from .firebase_provider import FirebaseProvider
from .redis_provider import RedisProvider
from .email_provider import EmailProvider

__all__ = [
    'OpenAIProvider',
    'GoogleProvider',
    'StabilityProvider',
    'StripeProvider',
    'FFmpegProvider',
    'FirebaseProvider',
    'RedisProvider',
    'EmailProvider',
]

# Provider registry for dynamic provider selection
PROVIDER_REGISTRY = {
    'openai': OpenAIProvider,
    'google': GoogleProvider,
    'stability': StabilityProvider,
    'stripe': StripeProvider,
    'ffmpeg': FFmpegProvider,
    'firebase': FirebaseProvider,
    'redis': RedisProvider,
    'email': EmailProvider,
}

def get_provider(provider_type: str, config: dict = None):
    """
    Get a provider instance by type.
    
    Args:
        provider_type: Type of provider (openai, google, etc.)
        config: Provider configuration
        
    Returns:
        Provider instance
        
    Raises:
        ValueError: If provider type is not supported
    """
    provider_class = PROVIDER_REGISTRY.get(provider_type.lower())
    if not provider_class:
        raise ValueError(f"Unsupported provider type: {provider_type}")
    
    return provider_class(config or {})

class ProviderFactory:
    """Factory for creating and managing providers."""
    
    def __init__(self, app_config: dict = None):
        self.app_config = app_config or {}
        self._providers = {}
    
    def get(self, provider_type: str, config: dict = None):
        """Get or create a provider instance."""
        if provider_type not in self._providers:
            # Merge app config with provider-specific config
            provider_config = self.app_config.get(f'{provider_type.upper()}_CONFIG', {})
            if config:
                provider_config.update(config)
            
            self._providers[provider_type] = get_provider(provider_type, provider_config)
        
        return self._providers[provider_type]
    
    def register(self, provider_type: str, provider_class):
        """Register a custom provider class."""
        PROVIDER_REGISTRY[provider_type.lower()] = provider_class
        # Clear cached provider if it exists
        if provider_type in self._providers:
            del self._providers[provider_type]
    
    def clear_cache(self):
        """Clear cached provider instances."""
        self._providers.clear()

# Global provider factory instance
provider_factory = ProviderFactory()