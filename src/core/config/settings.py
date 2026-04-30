"""
Settings loader for the application.
"""

import os
from typing import Dict, Any
import yaml
import json
from pathlib import Path


class Settings:
    """Application settings manager."""

    _instance = None
    _settings = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance._load_settings()
        return cls._instance

    def _load_settings(self):
        """Load settings from config files."""
        config_dir = Path(__file__).parent.parent.parent.parent.parent / "config"

        # Default tier configuration
        default_tiers = {
            "free": {
                "videos_per_month": 3,
                "credits_per_month": 3,
                "max_duration": 180,  # in minutes
            },
            "starter": {
                "videos_per_month": 30,
                "credits_per_month": 30,
                "max_duration": 900,
            },
            "pro": {
                "videos_per_month": 75,
                "credits_per_month": 75,
                "max_duration": 2700,
            },
            "plus": {
                "videos_per_month": 250,
                "credits_per_month": 250,
                "max_duration": 5400,
            },
            "enterprise": {
                "videos_per_month": None,
                "credits_per_month": None,
                "max_duration": 18000,
            },
        }
        # Load tier configuration
        tier_config_path = config_dir / "tier_config.yaml"
        if tier_config_path.exists():
            try:
                with open(tier_config_path, "r") as f:
                    self._settings["tiers"] = yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Failed to load tier config: {e}")
                self._settings["tiers"] = default_tiers
        else:
            self._settings["tiers"] = default_tiers

        # Load video quality settings
        quality_config_path = config_dir / "video_quality.yaml"
        if quality_config_path.exists():
            with open(quality_config_path, "r") as f:
                self._settings["quality"] = yaml.safe_load(f)

        # Load AI model configurations
        ai_config_path = config_dir / "ai_models.yaml"
        if ai_config_path.exists():
            with open(ai_config_path, "r") as f:
                self._settings["ai_models"] = yaml.safe_load(f)

        # Load video styles
        styles_path = config_dir / "video_styles.json"
        if styles_path.exists():
            with open(styles_path, "r") as f:
                self._settings["styles"] = json.load(f)

        # Load languages
        languages_path = config_dir / "languages.json"
        if languages_path.exists():
            with open(languages_path, "r") as f:
                self._settings["languages"] = json.load(f)

        # Load rate limits
        rate_limits_path = config_dir / "rate_limits.yaml"
        if rate_limits_path.exists():
            with open(rate_limits_path, "r") as f:
                self._settings["rate_limits"] = yaml.safe_load(f)

    def get(self, key: str, default=None) -> Any:
        """Get a setting value."""
        keys = key.split(".")
        value = self._settings

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """Set a setting value."""
        keys = key.split(".")
        settings = self._settings

        for i, k in enumerate(keys[:-1]):
            if k not in settings:
                settings[k] = {}
            settings = settings[k]

        settings[keys[-1]] = value

    @property
    def tiers(self) -> Dict:
        """Get tier configurations."""
        return self.get("tiers", {})

    @property
    def quality_settings(self) -> Dict:
        """Get video quality settings."""
        return self.get("quality", {})

    @property
    def ai_models(self) -> Dict:
        """Get AI model configurations."""
        return self.get("ai_models", {})

    @property
    def styles(self) -> Dict:
        """Get video styles."""
        return self.get("styles", {})

    @property
    def languages(self) -> Dict:
        """Get language configurations."""
        return self.get("languages", {})

    @property
    def rate_limits(self) -> Dict:
        """Get rate limit configurations."""
        return self.get("rate_limits", {})


def load_settings() -> Dict[str, Any]:
    """Load all settings."""
    return Settings()._settings


# Global settings instance
settings = Settings()
