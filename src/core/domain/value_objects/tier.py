"""
Tier value object with business rules.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum

class Tier(str, Enum):
    """Subscription tiers."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    PLUS = "plus"
    ENTERPRISE = "enterprise"

@dataclass(frozen=True)
class TierSpec:
    """Tier specification value object."""
    
    name: Tier
    price_monthly: float  # USD per month
    price_yearly: float   # USD per year (with discount)
    
    # Video limits
    videos_per_month: Optional[int]  # None = unlimited
    max_video_length: int  # in seconds
    
    # Video quality
    max_quality: str  # 720p, 1080p, 4k, 4k+hdr
    ffmpeg_preset: str  # ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    
    # AI features
    ai_thumbnails_count: int
    ai_thumbnail_steps: int  # 20, 30, 40, 50
    extracted_thumbnails_count: int
    video_styles_available: list
    text_generation_model: str  # gemini-flash, gemini-pro, gpt-3.5, gpt-4
    silent_video_analysis_frames: int
    
    # Processing
    priority: int  # 1-10, higher = higher priority
    retention_days: int
    max_fps: int
    
    # Translation
    translation_enabled: bool
    batch_translation: bool
    
    # Support
    email_support: bool
    priority_support: bool
    dedicated_support: bool
    
    @classmethod
    def from_config(cls, tier_name: Tier, config: Dict[str, Any]) -> 'TierSpec':
        """Create TierSpec from configuration dictionary."""
        return cls(
            name=tier_name,
            price_monthly=config.get('price_monthly', 0),
            price_yearly=config.get('price_yearly', 0),
            videos_per_month=config.get('videos_per_month'),
            max_video_length=config.get('max_video_length', 180),  # 3 minutes default
            
            max_quality=config.get('max_quality', '720p'),
            ffmpeg_preset=config.get('ffmpeg_preset', 'ultrafast'),
            
            ai_thumbnails_count=config.get('ai_thumbnails_count', 1),
            ai_thumbnail_steps=config.get('ai_thumbnail_steps', 20),
            extracted_thumbnails_count=config.get('extracted_thumbnails_count', 5),
            video_styles_available=config.get('video_styles_available', []),
            text_generation_model=config.get('text_generation_model', 'gemini-flash'),
            silent_video_analysis_frames=config.get('silent_video_analysis_frames', 0),
            
            priority=config.get('priority', 1),
            retention_days=config.get('retention_days', 1),
            max_fps=config.get('max_fps', 30),
            
            translation_enabled=config.get('translation_enabled', True),
            batch_translation=config.get('batch_translation', False),
            
            email_support=config.get('email_support', False),
            priority_support=config.get('priority_support', False),
            dedicated_support=config.get('dedicated_support', False)
        )
    
    def can_process_video(self, video_length: int, videos_processed_this_month: int) -> bool:
        """Check if tier can process a video of given length."""
        # Check video length
        if video_length > self.max_video_length:
            return False
        
        # Check monthly limit
        if self.videos_per_month is not None:
            if videos_processed_this_month >= self.videos_per_month:
                return False
        
        return True
    
    def get_quality_preset(self) -> Dict[str, Any]:
        """Get FFmpeg quality preset for this tier."""
        presets = {
            'ultrafast': {'crf': 28, 'preset': 'ultrafast'},
            'superfast': {'crf': 26, 'preset': 'superfast'},
            'veryfast': {'crf': 24, 'preset': 'veryfast'},
            'faster': {'crf': 22, 'preset': 'faster'},
            'fast': {'crf': 20, 'preset': 'fast'},
            'medium': {'crf': 18, 'preset': 'medium'},
            'slow': {'crf': 16, 'preset': 'slow'},
            'slower': {'crf': 14, 'preset': 'slower'},
            'veryslow': {'crf': 12, 'preset': 'veryslow'},
        }
        return presets.get(self.ffmpeg_preset, presets['ultrafast'])
    
    def get_video_bitrate(self) -> int:
        """Get recommended video bitrate for this tier's quality."""
        bitrates = {
            '720p': 2000000,   # 2 Mbps
            '1080p': 5000000,  # 5 Mbps
            '4k': 15000000,    # 15 Mbps
            '4k+hdr': 25000000 # 25 Mbps
        }
        return bitrates.get(self.max_quality.lower(), 2000000)
    
    def get_ai_model_cost(self, service: str) -> float:
        """Get estimated cost per request for AI services."""
        # These are approximate costs
        costs = {
            'transcription': 0.006 / 60,  # $0.006 per minute
            'gemini-flash': 0.00006,
            'gemini-pro': 0.00025,
            'gpt-3.5': 0.00015,
            'gpt-4': 0.0015,
            'sd-20-steps': 0.002,
            'sd-30-steps': 0.003,
            'sd-40-steps': 0.004,
            'sd-50-steps': 0.005,
            'sd-xl-40-steps': 0.008,
            'sd-3.6-turbo-50-steps': 0.012,
        }
        
        if service == 'thumbnail':
            steps_key = f'sd-{self.ai_thumbnail_steps}-steps'
            if self.ai_thumbnail_steps == 40 and 'xl' in self.max_quality.lower():
                steps_key = 'sd-xl-40-steps'
            elif self.ai_thumbnail_steps == 50 and 'turbo' in self.max_quality.lower():
                steps_key = 'sd-3.6-turbo-50-steps'
            return costs.get(steps_key, 0.003)
        
        return costs.get(service, 0.0)
    
    def get_yearly_savings(self) -> float:
        """Get yearly savings percentage."""
        if self.price_yearly == 0:
            return 0
        monthly_total = self.price_monthly * 12
        savings = monthly_total - self.price_yearly
        return (savings / monthly_total) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'name': self.name.value,
            'price_monthly': self.price_monthly,
            'price_yearly': self.price_yearly,
            'yearly_savings': self.get_yearly_savings(),
            'videos_per_month': self.videos_per_month,
            'max_video_length': self.max_video_length,
            'max_quality': self.max_quality,
            'ai_thumbnails_count': self.ai_thumbnails_count,
            'extracted_thumbnails_count': self.extracted_thumbnails_count,
            'video_styles_available': self.video_styles_available,
            'retention_days': self.retention_days,
            'priority': self.priority,
            'translation_enabled': self.translation_enabled,
            'batch_translation': self.batch_translation,
            'email_support': self.email_support,
            'priority_support': self.priority_support,
            'dedicated_support': self.dedicated_support
        }