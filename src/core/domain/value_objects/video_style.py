"""
Video style value object.
"""
from dataclasses import dataclass
from typing import Dict, Any, List
from enum import Enum

class StyleCategory(str, Enum):
    """Video style categories."""
    BASIC = "basic"
    CINEMATIC = "cinematic"
    GAMING = "gaming"
    EDUCATIONAL = "educational"
    SOCIAL_MEDIA = "social_media"
    PROFESSIONAL = "professional"
    ARTISTIC = "artistic"
    CUSTOM = "custom"

@dataclass(frozen=True)
class VideoStyle:
    """Video style value object."""
    
    id: str
    name: str
    category: StyleCategory
    description: str
    preview_image: str
    
    # Processing parameters
    ffmpeg_filters: List[str]
    color_grading: Dict[str, Any]
    transitions: List[str]
    text_overlay: Dict[str, Any]
    
    # AI parameters
    prompt_template: str
    negative_prompt: str
    style_weight: float  # 0.0 to 1.0
    
    # Tier restrictions
    available_tiers: List[str]  # free, starter, pro, plus
    requires_gpu: bool
    
    # Metadata
    created_by: str  # system or user_id
    is_public: bool
    usage_count: int = 0
    
    @classmethod
    def from_config(cls, style_id: str, config: Dict[str, Any]) -> 'VideoStyle':
        """Create VideoStyle from configuration dictionary."""
        return cls(
            id=style_id,
            name=config.get('name', 'Unnamed Style'),
            category=StyleCategory(config.get('category', 'basic')),
            description=config.get('description', ''),
            preview_image=config.get('preview_image', ''),
            
            ffmpeg_filters=config.get('ffmpeg_filters', []),
            color_grading=config.get('color_grading', {}),
            transitions=config.get('transitions', []),
            text_overlay=config.get('text_overlay', {}),
            
            prompt_template=config.get('prompt_template', ''),
            negative_prompt=config.get('negative_prompt', ''),
            style_weight=config.get('style_weight', 0.5),
            
            available_tiers=config.get('available_tiers', ['free', 'starter', 'pro', 'plus']),
            requires_gpu=config.get('requires_gpu', False),
            
            created_by=config.get('created_by', 'system'),
            is_public=config.get('is_public', True)
        )
    
    def is_available_for_tier(self, tier: str) -> bool:
        """Check if style is available for given tier."""
        return tier in self.available_tiers
    
    def get_ffmpeg_command(self, input_file: str, output_file: str) -> List[str]:
        """Generate FFmpeg command for applying this style."""
        base_cmd = ['ffmpeg', '-i', input_file]
        
        # Add filters
        if self.ffmpeg_filters:
            filter_complex = ','.join(self.ffmpeg_filters)
            base_cmd.extend(['-filter_complex', filter_complex])
        
        # Add color grading if specified
        if self.color_grading:
            # Convert color grading to FFmpeg filter
            color_filter = self._create_color_filter()
            if color_filter:
                if '-filter_complex' in base_cmd:
                    # Append to existing filter complex
                    idx = base_cmd.index('-filter_complex')
                    base_cmd[idx + 1] = f"{base_cmd[idx + 1]},{color_filter}"
                else:
                    base_cmd.extend(['-filter_complex', color_filter])
        
        # Add output settings
        base_cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '18',
            '-c:a', 'aac',
            '-b:a', '192k',
            output_file
        ])
        
        return base_cmd
    
    def _create_color_filter(self) -> str:
        """Create FFmpeg color filter from color_grading dict."""
        filters = []
        
        if 'brightness' in self.color_grading:
            filters.append(f"eq=brightness={self.color_grading['brightness']}")
        
        if 'contrast' in self.color_grading:
            filters.append(f"eq=contrast={self.color_grading['contrast']}")
        
        if 'saturation' in self.color_grading:
            filters.append(f"eq=saturation={self.color_grading['saturation']}")
        
        if 'gamma' in self.color_grading:
            filters.append(f"eq=gamma={self.color_grading['gamma']}")
        
        if 'hue' in self.color_grading:
            filters.append(f"hue=h={self.color_grading['hue']}")
        
        if filters:
            return ','.join(filters)
        
        return ''
    
    def get_ai_prompt(self, video_description: str) -> str:
        """Generate AI prompt based on video description."""
        return self.prompt_template.format(
            description=video_description,
            style=self.name
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category.value,
            'description': self.description,
            'preview_image': self.preview_image,
            'available_tiers': self.available_tiers,
            'requires_gpu': self.requires_gpu,
            'is_public': self.is_public,
            'usage_count': self.usage_count
        }