"""
Video style application service.
"""
import os
import json
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError, ConfigurationError
from providers.ffmpeg_provider import FFmpegProvider

logger = logging.getLogger(__name__)

class StyleService:
    """Video style application service."""
    
    def __init__(self):
        self.ffmpeg = FFmpegProvider()
        self._styles = self._load_styles()
    
    def _load_styles(self) -> Dict[str, Dict[str, Any]]:
        """Load video styles from configuration."""
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'
        styles_path = config_dir / 'video_styles.json'
        
        if not styles_path.exists():
            # Create default styles
            default_styles = self._create_default_styles()
            self._save_styles(default_styles)
            return default_styles
        
        try:
            with open(styles_path, 'r') as f:
                styles = json.load(f)
            return styles
        except Exception as e:
            raise ConfigurationError(f"Failed to load video styles: {e}")
    
    def _save_styles(self, styles: Dict[str, Dict[str, Any]]):
        """Save video styles to configuration."""
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'
        styles_path = config_dir / 'video_styles.json'
        
        # Create config directory if it doesn't exist
        styles_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(styles_path, 'w') as f:
            json.dump(styles, f, indent=2)
    
    def _create_default_styles(self) -> Dict[str, Dict[str, Any]]:
        """Create default video styles."""
        return {
            "cinematic": {
                "name": "Cinematic",
                "category": "basic",
                "description": "Movie-like look with enhanced contrast and color grading",
                "ffmpeg_filters": [
                    "eq=brightness=0.05:contrast=1.1:saturation=1.2",
                    "colorbalance=rs=0.1:gs=0.0:bs=-0.1",
                    "unsharp=5:5:0.5:5:5:0.5"
                ],
                "color_grading": {
                    "brightness": 0.05,
                    "contrast": 1.1,
                    "saturation": 1.2,
                    "gamma": 1.0,
                    "hue": 0.0
                },
                "transitions": ["fade"],
                "text_overlay": {
                    "enabled": False
                },
                "prompt_template": "cinematic movie film look, dramatic lighting, professional color grading",
                "negative_prompt": "flat, dull, amateur, low contrast",
                "style_weight": 0.7,
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
                "created_by": "system",
                "is_public": True,
                "usage_count": 0
            },
            "bright": {
                "name": "Bright & Vibrant",
                "category": "basic",
                "description": "Bright, colorful look perfect for social media",
                "ffmpeg_filters": [
                    "eq=brightness=0.1:contrast=1.05:saturation=1.3",
                    "hue=s=1.1"
                ],
                "color_grading": {
                    "brightness": 0.1,
                    "contrast": 1.05,
                    "saturation": 1.3,
                    "gamma": 0.9,
                    "hue": 0.0
                },
                "transitions": ["slide"],
                "text_overlay": {
                    "enabled": False
                },
                "prompt_template": "bright vibrant colorful, social media style, high saturation, eye-catching",
                "negative_prompt": "dark, dull, muted, desaturated",
                "style_weight": 0.6,
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
                "created_by": "system",
                "is_public": True,
                "usage_count": 0
            },
            "gaming": {
                "name": "Gaming",
                "category": "gaming",
                "description": "High-energy gaming style with vibrant colors and effects",
                "ffmpeg_filters": [
                    "eq=brightness=0.15:contrast=1.2:saturation=1.4",
                    "hue=h=10",
                    "edgedetect=low=0.1:high=0.3",
                    "glow=strength=0.5"
                ],
                "color_grading": {
                    "brightness": 0.15,
                    "contrast": 1.2,
                    "saturation": 1.4,
                    "gamma": 0.8,
                    "hue": 10.0
                },
                "transitions": ["zoom", "glitch"],
                "text_overlay": {
                    "enabled": True,
                    "text": "GAMING",
                    "font": "Impact",
                    "color": "#ff0000",
                    "size": 48,
                    "position": "top"
                },
                "prompt_template": "gaming stream highlight, energetic, vibrant colors, digital effects",
                "negative_prompt": "calm, slow, cinematic, realistic",
                "style_weight": 0.8,
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
                "requires_gpu": True,
                "created_by": "system",
                "is_public": True,
                "usage_count": 0
            },
            "educational": {
                "name": "Educational",
                "category": "educational",
                "description": "Clean, professional look for educational content",
                "ffmpeg_filters": [
                    "eq=brightness=0.08:contrast=1.15:saturation=1.0",
                    "unsharp=3:3:0.25:3:3:0.25"
                ],
                "color_grading": {
                    "brightness": 0.08,
                    "contrast": 1.15,
                    "saturation": 1.0,
                    "gamma": 1.0,
                    "hue": 0.0
                },
                "transitions": ["fade"],
                "text_overlay": {
                    "enabled": True,
                    "text": "EDUCATIONAL",
                    "font": "Arial",
                    "color": "#000000",
                    "size": 36,
                    "position": "bottom"
                },
                "prompt_template": "educational tutorial, clean professional, well-lit, informative",
                "negative_prompt": "artistic, cinematic, gaming, entertainment",
                "style_weight": 0.5,
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
                "created_by": "system",
                "is_public": True,
                "usage_count": 0
            },
            "vlog": {
                "name": "Vlog",
                "category": "social_media",
                "description": "Casual, personal vlog style with warm tones",
                "ffmpeg_filters": [
                    "eq=brightness=0.07:contrast=1.05:saturation=1.1",
                    "colorbalance=rs=0.05:gs=0.0:bs=-0.05",
                    "hue=s=1.05"
                ],
                "color_grading": {
                    "brightness": 0.07,
                    "contrast": 1.05,
                    "saturation": 1.1,
                    "gamma": 0.95,
                    "hue": 0.0
                },
                "transitions": ["fade", "slide"],
                "text_overlay": {
                    "enabled": False
                },
                "prompt_template": "vlog personal vlogger, casual, warm tones, authentic, relatable",
                "negative_prompt": "corporate, professional, cold, sterile",
                "style_weight": 0.6,
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
                "created_by": "system",
                "is_public": True,
                "usage_count": 0
            }
        }
    
    def apply_styles(
        self,
        video_path: str,
        style_names: List[str],
        tier: Tier
    ) -> Dict[str, Any]:
        """
        Apply video styles to video.
        
        Args:
            video_path: Path to video file
            style_names: List of style names to apply
            tier: User tier for style availability
        
        Returns:
            Processing result
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")
        
        # Filter styles based on tier availability
        available_styles = []
        for style_name in style_names:
            style = self.get_style(style_name)
            if style and self.is_style_available(style_name, tier):
                available_styles.append(style)
        
        if not available_styles:
            # No styles to apply
            return {
                'path': video_path,
                'applied_styles': [],
                'cost': 0.0,
                'success': True
            }
        
        # Create temporary output file
        temp_dir = tempfile.mkdtemp(prefix="video_ai_styles_")
        output_filename = f"styled_{Path(video_path).stem}.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        try:
            # Apply styles sequentially
            current_input = video_path
            applied_styles = []
            total_cost = 0.0
            
            for style in available_styles:
                temp_output = os.path.join(temp_dir, f"temp_{style['name']}.mp4")
                
                # Apply style
                success = self._apply_single_style(
                    input_path=current_input,
                    output_path=temp_output,
                    style=style
                )
                
                if success:
                    applied_styles.append(style['name'])
                    total_cost += self._calculate_style_cost(style, tier)
                    
                    # Update current input for next style
                    if os.path.exists(current_input) and current_input != video_path:
                        os.remove(current_input)  # Cleanup intermediate file
                    
                    current_input = temp_output
            
            # Rename final output
            os.rename(current_input, output_path)
            
            # Update style usage count
            for style_name in applied_styles:
                self._increment_style_usage(style_name)
            
            return {
                'path': output_path,
                'applied_styles': applied_styles,
                'cost': total_cost,
                'success': True,
                'output_dir': temp_dir
            }
            
        except Exception as e:
            # Cleanup on error
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            raise ProcessingError(f"Style application failed: {str(e)}", step="style_application")
    
    def _apply_single_style(
        self,
        input_path: str,
        output_path: str,
        style: Dict[str, Any]
    ) -> bool:
        """Apply a single style to video."""
        # Build FFmpeg command
        cmd = ['ffmpeg', '-i', input_path, '-y']
        
        # Add video filters
        filters = style.get('ffmpeg_filters', [])
        if filters:
            filter_string = ','.join(filters)
            cmd.extend(['-vf', filter_string])
        
        # Add color grading if specified
        color_grading = style.get('color_grading', {})
        if color_grading:
            color_filters = []
            
            if 'brightness' in color_grading:
                color_filters.append(f"eq=brightness={color_grading['brightness']}")
            
            if 'contrast' in color_grading:
                color_filters.append(f"eq=contrast={color_grading['contrast']}")
            
            if 'saturation' in color_grading:
                color_filters.append(f"eq=saturation={color_grading['saturation']}")
            
            if 'gamma' in color_grading:
                color_filters.append(f"eq=gamma={color_grading['gamma']}")
            
            if 'hue' in color_grading:
                color_filters.append(f"hue=h={color_grading['hue']}")
            
            if color_filters:
                if '-vf' in cmd:
                    # Append to existing filter
                    idx = cmd.index('-vf')
                    cmd[idx + 1] = f"{cmd[idx + 1]},{','.join(color_filters)}"
                else:
                    cmd.extend(['-vf', ','.join(color_filters)])
        
        # Add text overlay if enabled
        text_overlay = style.get('text_overlay', {})
        if text_overlay.get('enabled', False):
            text = text_overlay.get('text', '')
            font = text_overlay.get('font', 'Arial')
            color = text_overlay.get('color', 'white')
            size = text_overlay.get('size', 24)
            position = text_overlay.get('position', 'top')
            
            # Convert position to drawtext coordinates
            if position == 'top':
                x = '(w-text_w)/2'
                y = '20'
            elif position == 'bottom':
                x = '(w-text_w)/2'
                y = 'h-text_h-20'
            else:  # center
                x = '(w-text_w)/2'
                y = '(h-text_h)/2'
            
            drawtext_filter = f"drawtext=text='{text}':fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf:fontcolor={color}:fontsize={size}:x={x}:y={y}"
            
            if '-vf' in cmd:
                idx = cmd.index('-vf')
                cmd[idx + 1] = f"{cmd[idx + 1]},{drawtext_filter}"
            else:
                cmd.extend(['-vf', drawtext_filter])
        
        # Add output settings
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '18',
            '-c:a', 'copy',  # Keep original audio
            output_path
        ])
        
        # Execute command
        logger.info(f"Applying style {style['name']} with command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Style application failed: {result.stderr}")
            return False
        
        return True
    
    def get_style(self, style_name: str) -> Optional[Dict[str, Any]]:
        """Get style by name."""
        return self._styles.get(style_name)
    
    def get_all_styles(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all styles, optionally filtered by category."""
        if category:
            return [
                style for style in self._styles.values()
                if style.get('category') == category
            ]
        else:
            return list(self._styles.values())
    
    def get_styles_for_tier(self, tier: Tier) -> List[Dict[str, Any]]:
        """Get styles available for user tier."""
        tier_str = tier.value.lower()
        
        return [
            style for style in self._styles.values()
            if tier_str in style.get('available_tiers', [])
        ]
    
    def is_style_available(self, style_name: str, tier: Tier) -> bool:
        """Check if style is available for user tier."""
        style = self.get_style(style_name)
        if not style:
            return False
        
        tier_str = tier.value.lower()
        return tier_str in style.get('available_tiers', [])
    
    def _calculate_style_cost(self, style: Dict[str, Any], tier: Tier) -> float:
        """Calculate cost for applying a style."""
        # Base cost per style
        base_cost = 0.001  # $0.001 per style application
        
        # Adjust based on complexity
        complexity_factors = {
            'basic': 1.0,
            'cinematic': 1.2,
            'gaming': 1.5,
            'educational': 1.0,
            'social_media': 1.1,
            'professional': 1.3,
            'artistic': 1.8,
            'custom': 2.0
        }
        
        category = style.get('category', 'basic')
        complexity = complexity_factors.get(category, 1.0)
        
        # GPU requirement adds cost
        if style.get('requires_gpu', False):
            complexity *= 1.5
        
        # Calculate cost
        cost = base_cost * complexity
        
        # Apply tier adjustments
        tier_multipliers = {
            Tier.FREE: 1.0,
            Tier.STARTER: 1.0,
            Tier.PRO: 1.0,
            Tier.PLUS: 1.0,
            Tier.ENTERPRISE: 1.0
        }
        
        multiplier = tier_multipliers.get(tier, 1.0)
        
        return cost * multiplier
    
    def _increment_style_usage(self, style_name: str):
        """Increment style usage count."""
        if style_name in self._styles:
            self._styles[style_name]['usage_count'] = self._styles[style_name].get('usage_count', 0) + 1
            self._save_styles(self._styles)
    
    def create_custom_style(
        self,
        name: str,
        category: str,
        description: str,
        ffmpeg_filters: List[str],
        color_grading: Dict[str, float],
        created_by: str,
        available_tiers: List[str] = None
    ) -> Dict[str, Any]:
        """Create a custom video style."""
        if name in self._styles:
            raise ProcessingError(f"Style '{name}' already exists")
        
        if available_tiers is None:
            available_tiers = ['pro', 'plus', 'enterprise']
        
        custom_style = {
            'name': name,
            'category': category,
            'description': description,
            'ffmpeg_filters': ffmpeg_filters,
            'color_grading': color_grading,
            'transitions': [],
            'text_overlay': {
                'enabled': False
            },
            'prompt_template': f"custom {category} style: {description}",
            'negative_prompt': '',
            'style_weight': 0.5,
            'available_tiers': available_tiers,
            'requires_gpu': False,
            'created_by': created_by,
            'is_public': False,
            'usage_count': 0
        }
        
        self._styles[name] = custom_style
        self._save_styles(self._styles)
        
        return custom_style
    
    def get_popular_styles(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get most popular styles by usage count."""
        all_styles = self.get_all_styles()
        sorted_styles = sorted(all_styles, key=lambda x: x.get('usage_count', 0), reverse=True)
        return sorted_styles[:limit]