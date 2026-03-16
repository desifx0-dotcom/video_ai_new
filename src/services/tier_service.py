"""
Tier management service.
"""
from typing import Dict, Any, List, Optional
import yaml
from pathlib import Path

from core.domain.value_objects.tier import Tier, TierSpec
from core.exceptions import ConfigurationError

class TierService:
    """Tier management service."""
    
    def __init__(self):
        self._tiers: Dict[Tier, TierSpec] = {}
        self._load_tiers()
    
    def _load_tiers(self):
        """Load tier configurations from config file."""
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'
        tier_config_path = config_dir / 'tier_config.yaml'
        
        if not tier_config_path.exists():
            # Create default tier configuration
            self._create_default_tiers()
            return
        
        try:
            with open(tier_config_path, 'r') as f:
                tier_configs = yaml.safe_load(f) or {}
            
            for tier_name, config in tier_configs.items():
                try:
                    tier = Tier(tier_name.lower())
                    tier_spec = TierSpec.from_config(tier, config)
                    self._tiers[tier] = tier_spec
                except ValueError:
                    # Skip invalid tier names
                    continue
        
        except Exception as e:
            raise ConfigurationError(f"Failed to load tier configurations: {e}")
    
    def _create_default_tiers(self):
        """Create default tier configurations."""
        default_configs = {
            "free": {
                "price_monthly": 0,
                "price_yearly": 0,
                "videos_per_month": 3,
                "max_video_length": 180,  # 3 minutes
                "max_quality": "720p",
                "ffmpeg_preset": "ultrafast",
                "ai_thumbnails_count": 1,
                "ai_thumbnail_steps": 20,
                "extracted_thumbnails_count": 5,
                "video_styles_available": ["cinematic", "bright", "vibrant"],
                "text_generation_model": "gemini-flash",
                "silent_video_analysis_frames": 0,
                "priority": 1,
                "retention_days": 1,
                "max_fps": 30,
                "translation_enabled": True,
                "batch_translation": False,
                "email_support": False,
                "priority_support": False,
                "dedicated_support": False
            },
            "starter": {
                "price_monthly": 24,
                "price_yearly": 240,  # $20/month equivalent
                "videos_per_month": 50,
                "max_video_length": 1800,  # 30 minutes
                "max_quality": "1080p",
                "ffmpeg_preset": "medium",
                "ai_thumbnails_count": 3,
                "ai_thumbnail_steps": 30,
                "extracted_thumbnails_count": 8,
                "video_styles_available": ["all"],
                "text_generation_model": "gemini-flash",
                "silent_video_analysis_frames": 2,
                "priority": 3,
                "retention_days": 7,
                "max_fps": 30,
                "translation_enabled": True,
                "batch_translation": False,
                "email_support": True,
                "priority_support": False,
                "dedicated_support": False
            },
            "pro": {
                "price_monthly": 79,
                "price_yearly": 790,  # $65.83/month equivalent
                "videos_per_month": 100,
                "max_video_length": 3600,  # 60 minutes
                "max_quality": "4k",
                "ffmpeg_preset": "slow",
                "ai_thumbnails_count": 5,
                "ai_thumbnail_steps": 40,
                "extracted_thumbnails_count": 15,
                "video_styles_available": ["all"],
                "text_generation_model": "gemini-pro",
                "silent_video_analysis_frames": 3,
                "priority": 5,
                "retention_days": 30,
                "max_fps": 60,
                "translation_enabled": True,
                "batch_translation": True,
                "email_support": True,
                "priority_support": True,
                "dedicated_support": False
            },
            "plus": {
                "price_monthly": 250,
                "price_yearly": 2500,  # $208.33/month equivalent
                "videos_per_month": 500,
                "max_video_length": 7200,  # 120 minutes
                "max_quality": "4k+hdr",
                "ffmpeg_preset": "veryslow",
                "ai_thumbnails_count": 10,
                "ai_thumbnail_steps": 50,
                "extracted_thumbnails_count": 25,
                "video_styles_available": ["all", "custom"],
                "text_generation_model": "gpt-4-turbo",
                "silent_video_analysis_frames": 5,
                "priority": 10,
                "retention_days": 90,
                "max_fps": 60,
                "translation_enabled": True,
                "batch_translation": True,
                "email_support": True,
                "priority_support": True,
                "dedicated_support": True
            },
            "enterprise": {
                "price_monthly": 999,
                "price_yearly": 9990,  # $832.50/month equivalent
                "videos_per_month": None,  # Unlimited
                "max_video_length": 18000,  # 300 minutes (5 hours)
                "max_quality": "4k+hdr",
                "ffmpeg_preset": "veryslow",
                "ai_thumbnails_count": 20,
                "ai_thumbnail_steps": 50,
                "extracted_thumbnails_count": 50,
                "video_styles_available": ["all", "custom"],
                "text_generation_model": "gpt-4-turbo",
                "silent_video_analysis_frames": 10,
                "priority": 20,
                "retention_days": 365,
                "max_fps": 120,
                "translation_enabled": True,
                "batch_translation": True,
                "email_support": True,
                "priority_support": True,
                "dedicated_support": True
            }
        }
        
        for tier_name, config in default_configs.items():
            try:
                tier = Tier(tier_name.lower())
                tier_spec = TierSpec.from_config(tier, config)
                self._tiers[tier] = tier_spec
            except ValueError:
                continue
        
        # Save default config to file
        self._save_tiers()
    
    def _save_tiers(self):
        """Save tier configurations to config file."""
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'
        tier_config_path = config_dir / 'tier_config.yaml'
        
        # Create config directory if it doesn't exist
        tier_config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert tiers to dictionary
        tier_configs = {}
        for tier, spec in self._tiers.items():
            tier_configs[tier.value] = {
                "price_monthly": spec.price_monthly,
                "price_yearly": spec.price_yearly,
                "videos_per_month": spec.videos_per_month,
                "max_video_length": spec.max_video_length,
                "max_quality": spec.max_quality,
                "ffmpeg_preset": spec.ffmpeg_preset,
                "ai_thumbnails_count": spec.ai_thumbnails_count,
                "ai_thumbnail_steps": spec.ai_thumbnail_steps,
                "extracted_thumbnails_count": spec.extracted_thumbnails_count,
                "video_styles_available": spec.video_styles_available,
                "text_generation_model": spec.text_generation_model,
                "silent_video_analysis_frames": spec.silent_video_analysis_frames,
                "priority": spec.priority,
                "retention_days": spec.retention_days,
                "max_fps": spec.max_fps,
                "translation_enabled": spec.translation_enabled,
                "batch_translation": spec.batch_translation,
                "email_support": spec.email_support,
                "priority_support": spec.priority_support,
                "dedicated_support": spec.dedicated_support
            }
        
        # Save to YAML file
        with open(tier_config_path, 'w') as f:
            yaml.dump(tier_configs, f, default_flow_style=False)
    
    def get_tier(self, tier_name: Tier) -> Optional[TierSpec]:
        """Get tier specification by name."""
        return self._tiers.get(tier_name)
    
    def get_all_tiers(self) -> List[TierSpec]:
        """Get all tier specifications."""
        return list(self._tiers.values())
    
    def get_tier_for_user(self, user_tier: Tier) -> Optional[TierSpec]:
        """Get tier specification for user."""
        return self.get_tier(user_tier)
    
    def can_process_video(self, user_tier: Tier, video_length: int, 
                         videos_processed_this_month: int) -> bool:
        """Check if user can process a video based on tier limits."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return False
        
        return tier_spec.can_process_video(video_length, videos_processed_this_month)
    
    def get_max_video_length(self, user_tier: Tier) -> int:
        """Get maximum video length for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 180  # Default 3 minutes
        
        return tier_spec.max_video_length
    
    def get_max_quality(self, user_tier: Tier) -> str:
        """Get maximum video quality for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return "720p"
        
        return tier_spec.max_quality
    
    def get_ai_thumbnails_count(self, user_tier: Tier) -> int:
        """Get number of AI thumbnails for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 1
        
        return tier_spec.ai_thumbnails_count
    
    def get_extracted_thumbnails_count(self, user_tier: Tier) -> int:
        """Get number of extracted thumbnails for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 5
        
        return tier_spec.extracted_thumbnails_count
    
    def get_retention_days(self, user_tier: Tier) -> int:
        """Get video retention period for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 1
        
        return tier_spec.retention_days
    
    def get_priority(self, user_tier: Tier) -> int:
        """Get processing priority for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 1
        
        return tier_spec.priority
    
    def get_video_styles(self, user_tier: Tier) -> List[str]:
        """Get available video styles for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return ["cinematic", "bright", "vibrant"]
        
        return tier_spec.video_styles_available
    
    def get_text_model(self, user_tier: Tier) -> str:
        """Get text generation model for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return "gemini-flash"
        
        return tier_spec.text_generation_model
    
    def get_silent_analysis_frames(self, user_tier: Tier) -> int:
        """Get number of frames for silent video analysis."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 0
        
        return tier_spec.silent_video_analysis_frames
    
    def get_price(self, user_tier: Tier, yearly: bool = False) -> float:
        """Get price for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 0
        
        return tier_spec.price_yearly if yearly else tier_spec.price_monthly
    
    def get_yearly_savings(self, user_tier: Tier) -> float:
        """Get yearly savings percentage for tier."""
        tier_spec = self.get_tier(user_tier)
        if not tier_spec:
            return 0
        
        return tier_spec.get_yearly_savings()
    
    def get_tier_comparison(self) -> List[Dict[str, Any]]:
        """Get comparison of all tiers for display."""
        comparison = []
        
        for tier_spec in self.get_all_tiers():
            comparison.append({
                "name": tier_spec.name.value,
                "price_monthly": tier_spec.price_monthly,
                "price_yearly": tier_spec.price_yearly,
                "yearly_savings": tier_spec.get_yearly_savings(),
                "videos_per_month": tier_spec.videos_per_month,
                "max_video_length": tier_spec.max_video_length,
                "max_quality": tier_spec.max_quality,
                "ai_thumbnails_count": tier_spec.ai_thumbnails_count,
                "extracted_thumbnails_count": tier_spec.extracted_thumbnails_count,
                "video_styles_available": len(tier_spec.video_styles_available),
                "retention_days": tier_spec.retention_days,
                "priority": tier_spec.priority,
                "translation_enabled": tier_spec.translation_enabled,
                "batch_translation": tier_spec.batch_translation,
                "email_support": tier_spec.email_support,
                "priority_support": tier_spec.priority_support,
                "dedicated_support": tier_spec.dedicated_support
            })
        
        return comparison
    
    def update_tier(self, tier_name: Tier, updates: Dict[str, Any]) -> bool:
        """Update tier configuration."""
        tier_spec = self.get_tier(tier_name)
        if not tier_spec:
            return False
        
        # Create updated tier spec
        current_config = {
            "price_monthly": tier_spec.price_monthly,
            "price_yearly": tier_spec.price_yearly,
            "videos_per_month": tier_spec.videos_per_month,
            "max_video_length": tier_spec.max_video_length,
            "max_quality": tier_spec.max_quality,
            "ffmpeg_preset": tier_spec.ffmpeg_preset,
            "ai_thumbnails_count": tier_spec.ai_thumbnails_count,
            "ai_thumbnail_steps": tier_spec.ai_thumbnail_steps,
            "extracted_thumbnails_count": tier_spec.extracted_thumbnails_count,
            "video_styles_available": tier_spec.video_styles_available,
            "text_generation_model": tier_spec.text_generation_model,
            "silent_video_analysis_frames": tier_spec.silent_video_analysis_frames,
            "priority": tier_spec.priority,
            "retention_days": tier_spec.retention_days,
            "max_fps": tier_spec.max_fps,
            "translation_enabled": tier_spec.translation_enabled,
            "batch_translation": tier_spec.batch_translation,
            "email_support": tier_spec.email_support,
            "priority_support": tier_spec.priority_support,
            "dedicated_support": tier_spec.dedicated_support
        }
        
        # Apply updates
        current_config.update(updates)
        
        # Create new tier spec
        updated_tier_spec = TierSpec.from_config(tier_name, current_config)
        self._tiers[tier_name] = updated_tier_spec
        
        # Save to file
        self._save_tiers()
        
        return True