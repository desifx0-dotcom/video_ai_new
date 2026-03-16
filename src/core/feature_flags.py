"""
Feature flag management system.
"""
import os
from typing import Dict, Any, Optional
import yaml
from pathlib import Path

from .exceptions import ConfigurationError

class FeatureFlags:
    """Feature flag manager."""
    
    _instance = None
    _flags: Dict[str, bool] = {}
    _config_file: Optional[Path] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FeatureFlags, cls).__new__(cls)
            cls._instance._load_flags()
        return cls._instance
    
    def _load_flags(self):
        """Load feature flags from environment and config file."""
        # Default flags from constants
        from .constants import FEATURE_FLAGS
        self._flags = FEATURE_FLAGS.copy()
        
        # Load from config file if it exists
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'
        self._config_file = config_dir / 'feature_flags.yaml'
        
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r') as f:
                    config_flags = yaml.safe_load(f) or {}
                
                # Update flags from config file
                for key, value in config_flags.items():
                    if isinstance(value, bool):
                        self._flags[key] = value
            except Exception as e:
                raise ConfigurationError(f"Failed to load feature flags: {e}")
        
        # Override with environment variables
        for key in self._flags.keys():
            env_key = f"FEATURE_{key}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                self._flags[key] = env_value.lower() in ['true', '1', 'yes', 'y']
    
    def is_enabled(self, feature: str, user_id: Optional[str] = None, 
                  tier: Optional[str] = None) -> bool:
        """
        Check if a feature is enabled.
        
        Args:
            feature: Feature flag name
            user_id: Optional user ID for user-specific flags
            tier: Optional user tier for tier-specific flags
        
        Returns:
            bool: True if feature is enabled
        """
        # Check global flag
        if feature not in self._flags:
            return False
        
        flag_value = self._flags[feature]
        
        # If it's a simple boolean, return it
        if isinstance(flag_value, bool):
            return flag_value
        
        # If it's a dictionary, check for user/tier-specific rules
        if isinstance(flag_value, dict):
            # Check user-specific flag
            if user_id and flag_value.get("users"):
                if user_id in flag_value["users"]:
                    return flag_value["users"][user_id]
            
            # Check tier-specific flag
            if tier and flag_value.get("tiers"):
                if tier in flag_value["tiers"]:
                    return flag_value["tiers"][tier]
            
            # Return default value if specified
            if "default" in flag_value:
                return flag_value["default"]
            
            return False
        
        # If it's not a boolean or dict, convert to boolean
        return bool(flag_value)
    
    def enable(self, feature: str, for_user: Optional[str] = None, 
               for_tier: Optional[str] = None):
        """Enable a feature flag."""
        if for_user:
            if feature not in self._flags:
                self._flags[feature] = {"users": {}}
            elif not isinstance(self._flags[feature], dict):
                self._flags[feature] = {"default": self._flags[feature], "users": {}}
            
            if "users" not in self._flags[feature]:
                self._flags[feature]["users"] = {}
            
            self._flags[feature]["users"][for_user] = True
        
        elif for_tier:
            if feature not in self._flags:
                self._flags[feature] = {"tiers": {}}
            elif not isinstance(self._flags[feature], dict):
                self._flags[feature] = {"default": self._flags[feature], "tiers": {}}
            
            if "tiers" not in self._flags[feature]:
                self._flags[feature]["tiers"] = {}
            
            self._flags[feature]["tiers"][for_tier] = True
        
        else:
            self._flags[feature] = True
        
        self._save_flags()
    
    def disable(self, feature: str, for_user: Optional[str] = None,
                for_tier: Optional[str] = None):
        """Disable a feature flag."""
        if for_user:
            if feature in self._flags and isinstance(self._flags[feature], dict):
                if "users" in self._flags[feature]:
                    self._flags[feature]["users"][for_user] = False
        
        elif for_tier:
            if feature in self._flags and isinstance(self._flags[feature], dict):
                if "tiers" in self._flags[feature]:
                    self._flags[feature]["tiers"][for_tier] = False
        
        else:
            self._flags[feature] = False
        
        self._save_flags()
    
    def toggle(self, feature: str, for_user: Optional[str] = None,
               for_tier: Optional[str] = None):
        """Toggle a feature flag."""
        current = self.is_enabled(feature, for_user, for_tier)
        
        if for_user:
            if current:
                self.disable(feature, for_user=for_user)
            else:
                self.enable(feature, for_user=for_user)
        
        elif for_tier:
            if current:
                self.disable(feature, for_tier=for_tier)
            else:
                self.enable(feature, for_tier=for_tier)
        
        else:
            self._flags[feature] = not current
            self._save_flags()
    
    def set_percentage(self, feature: str, percentage: int):
        """
        Enable a feature for a percentage of users.
        
        Args:
            feature: Feature flag name
            percentage: Percentage of users (0-100) who should have the feature enabled
        """
        if not 0 <= percentage <= 100:
            raise ValueError("Percentage must be between 0 and 100")
        
        self._flags[feature] = {
            "percentage": percentage,
            "default": False
        }
        self._save_flags()
    
    def is_enabled_for_percentage(self, feature: str, user_id: str) -> bool:
        """
        Check if feature is enabled for a specific user based on percentage rollout.
        
        Args:
            feature: Feature flag name
            user_id: User ID to check
        
        Returns:
            bool: True if feature is enabled for this user
        """
        if feature not in self._flags:
            return False
        
        flag_value = self._flags[feature]
        
        if not isinstance(flag_value, dict) or "percentage" not in flag_value:
            return False
        
        # Use user_id to deterministically decide if feature is enabled
        # This ensures the same user always gets the same result
        import hashlib
        hash_obj = hashlib.md5(f"{feature}:{user_id}".encode())
        hash_int = int(hash_obj.hexdigest(), 16)
        user_percentage = hash_int % 100
        
        return user_percentage < flag_value["percentage"]
    
    def get_all_flags(self, user_id: Optional[str] = None, 
                     tier: Optional[str] = None) -> Dict[str, bool]:
        """Get all feature flags for a user."""
        flags = {}
        
        for feature in self._flags.keys():
            flags[feature] = self.is_enabled(feature, user_id, tier)
        
        return flags
    
    def _save_flags(self):
        """Save feature flags to config file."""
        if self._config_file:
            try:
                # Create config directory if it doesn't exist
                self._config_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Save to YAML
                with open(self._config_file, 'w') as f:
                    yaml.dump(self._flags, f, default_flow_style=False)
            except Exception as e:
                raise ConfigurationError(f"Failed to save feature flags: {e}")
    
    def reload(self):
        """Reload feature flags from config file."""
        self._load_flags()

# Global feature flags instance
feature_flags = FeatureFlags()

# Decorator for feature-flagged functions
def feature_flag(feature_name: str, fallback_value=None):
    """
    Decorator to enable/disable functions based on feature flags.
    
    Args:
        feature_name: Name of the feature flag
        fallback_value: Value to return if feature is disabled
    
    Returns:
        Decorator function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Try to extract user_id and tier from arguments
            user_id = None
            tier = None
            
            # Look for user_id in kwargs or first argument
            if 'user_id' in kwargs:
                user_id = kwargs['user_id']
            elif args and hasattr(args[0], 'user_id'):
                user_id = args[0].user_id
            
            # Look for tier in kwargs or user object
            if 'tier' in kwargs:
                tier = kwargs['tier']
            elif user_id:
                # In a real implementation, you would fetch the user's tier
                pass
            
            # Check if feature is enabled
            if feature_flags.is_enabled(feature_name, user_id, tier):
                return func(*args, **kwargs)
            elif fallback_value is not None:
                return fallback_value
            else:
                raise ConfigurationError(f"Feature '{feature_name}' is disabled")
        
        return wrapper
    
    return decorator

# Context manager for temporary feature flags
class TemporaryFeatureFlag:
    """Context manager for temporarily enabling/disabling feature flags."""
    
    def __init__(self, feature: str, enabled: bool = True, 
                 for_user: Optional[str] = None, for_tier: Optional[str] = None):
        self.feature = feature
        self.enabled = enabled
        self.for_user = for_user
        self.for_tier = for_tier
        self.original_value = None
    
    def __enter__(self):
        # Store original value
        if self.for_user:
            self.original_value = feature_flags.is_enabled(self.feature, self.for_user)
        elif self.for_tier:
            self.original_value = feature_flags.is_enabled(self.feature, tier=self.for_tier)
        else:
            self.original_value = feature_flags.is_enabled(self.feature)
        
        # Set new value
        if self.enabled:
            feature_flags.enable(self.feature, self.for_user, self.for_tier)
        else:
            feature_flags.disable(self.feature, self.for_user, self.for_tier)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original value
        if self.original_value:
            feature_flags.enable(self.feature, self.for_user, self.for_tier)
        else:
            feature_flags.disable(self.feature, self.for_user, self.for_tier)