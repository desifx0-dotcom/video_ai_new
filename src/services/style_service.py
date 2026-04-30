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
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        styles_path = config_dir / "video_styles.json"

        if not styles_path.exists():
            # Create default styles
            default_styles = self._create_default_styles()
            self._save_styles(default_styles)
            return default_styles

        try:
            with open(styles_path, "r") as f:
                styles = json.load(f)
            return styles
        except Exception as e:
            raise ConfigurationError(f"Failed to load video styles: {e}")

    def _save_styles(self, styles: Dict[str, Dict[str, Any]]):
        """Save video styles to configuration."""
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        styles_path = config_dir / "video_styles.json"

        # Create config directory if it doesn't exist
        styles_path.parent.mkdir(parents=True, exist_ok=True)

        with open(styles_path, "w") as f:
            json.dump(styles, f, indent=2)

    def _create_default_styles(self) -> Dict[str, Dict[str, Any]]:
        """Create default video styles."""
        return {
            # Basic styles (Free tier)
            "cinematic": {
                "name": "Cinematic",
                "category": "basic",
                "description": "Movie-like look with enhanced contrast and color grading",
                "ffmpeg_filters": [
                    "eq=brightness=0.05:contrast=1.1:saturation=1.2",
                    "colorbalance=rs=0.1:gs=0.0:bs=-0.1",
                    "unsharp=5:5:0.5:5:5:0.5",
                ],
                "color_grading": {
                    "brightness": 0.05,
                    "contrast": 1.1,
                    "saturation": 1.2,
                    "gamma": 1.0,
                    "hue": 0.0,
                },
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "bright": {
                "name": "Bright & Vibrant",
                "category": "basic",
                "description": "Bright, colorful look perfect for social media",
                "ffmpeg_filters": [
                    "eq=brightness=0.1:contrast=1.05:saturation=1.3",
                    "hue=s=1.1",
                ],
                "color_grading": {
                    "brightness": 0.1,
                    "contrast": 1.05,
                    "saturation": 1.3,
                    "gamma": 0.9,
                    "hue": 0.0,
                },
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "educational": {
                "name": "Educational",
                "category": "basic",
                "description": "Clean, professional look for educational content",
                "ffmpeg_filters": [
                    "eq=brightness=0.08:contrast=1.15:saturation=1.0",
                    "unsharp=3:3:0.25:3:3:0.25",
                ],
                "color_grading": {
                    "brightness": 0.08,
                    "contrast": 1.15,
                    "saturation": 1.0,
                    "gamma": 1.0,
                    "hue": 0.0,
                },
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            # Starter tier styles
            "gaming": {
                "name": "Gaming",
                "category": "gaming",
                "description": "High-energy gaming style with vibrant colors and effects",
                "ffmpeg_filters": [
                    "eq=brightness=0.15:contrast=1.2:saturation=1.4",
                    "hue=h=10",
                    "edgedetect=low=0.1:high=0.3",
                ],
                "color_grading": {
                    "brightness": 0.15,
                    "contrast": 1.2,
                    "saturation": 1.4,
                    "gamma": 0.8,
                    "hue": 10.0,
                },
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
                "requires_gpu": True,
            },
            "vlog": {
                "name": "Vlog",
                "category": "social_media",
                "description": "Casual, personal vlog style with warm tones",
                "ffmpeg_filters": [
                    "eq=brightness=0.07:contrast=1.05:saturation=1.1",
                    "colorbalance=rs=0.05:gs=0.0:bs=-0.05",
                ],
                "color_grading": {
                    "brightness": 0.07,
                    "contrast": 1.05,
                    "saturation": 1.1,
                    "gamma": 0.95,
                    "hue": 0.0,
                },
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "travel": {
                "name": "Travel",
                "category": "lifestyle",
                "description": "Warm, inviting look for travel content",
                "ffmpeg_filters": [
                    "eq=brightness=0.08:contrast=1.1:saturation=1.15",
                    "colorbalance=rs=0.08:gs=0.02:bs=-0.05",
                ],
                "color_grading": {
                    "brightness": 0.08,
                    "contrast": 1.1,
                    "saturation": 1.15,
                    "gamma": 0.95,
                    "hue": 5.0,
                },
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            # Pro tier styles
            "professional": {
                "name": "Professional",
                "category": "professional",
                "description": "Clean, corporate look for business content",
                "ffmpeg_filters": [
                    "eq=brightness=0.02:contrast=1.05:saturation=1.0",
                    "unsharp=5:5:0.3:5:5:0.3",
                ],
                "color_grading": {
                    "brightness": 0.02,
                    "contrast": 1.05,
                    "saturation": 1.0,
                    "gamma": 1.0,
                    "hue": 0.0,
                },
                "available_tiers": ["pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "documentary": {
                "name": "Documentary",
                "category": "professional",
                "description": "Authentic, natural look for documentary content",
                "ffmpeg_filters": [
                    "eq=brightness=0.03:contrast=1.02:saturation=0.95",
                    "noise=alls=10:allf=t",
                ],
                "color_grading": {
                    "brightness": 0.03,
                    "contrast": 1.02,
                    "saturation": 0.95,
                    "gamma": 1.02,
                    "hue": 0.0,
                },
                "available_tiers": ["pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "wedding": {
                "name": "Wedding",
                "category": "professional",
                "description": "Romantic, soft look for wedding videos",
                "ffmpeg_filters": [
                    "eq=brightness=0.05:contrast=1.02:saturation=1.08",
                    "gblur=sigma=0.5",
                ],
                "color_grading": {
                    "brightness": 0.05,
                    "contrast": 1.02,
                    "saturation": 1.08,
                    "gamma": 0.98,
                    "hue": 2.0,
                },
                "available_tiers": ["pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "corporate": {
                "name": "Corporate",
                "category": "professional",
                "description": "Polished, trustworthy look for business",
                "ffmpeg_filters": [
                    "eq=brightness=0.01:contrast=1.03:saturation=0.98",
                    "unsharp=3:3:0.5",
                ],
                "color_grading": {
                    "brightness": 0.01,
                    "contrast": 1.03,
                    "saturation": 0.98,
                    "gamma": 1.0,
                    "hue": 0.0,
                },
                "available_tiers": ["pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            "real_estate": {
                "name": "Real Estate",
                "category": "commercial",
                "description": "Bright, spacious look for property videos",
                "ffmpeg_filters": ["eq=brightness=0.1:contrast=1.05:saturation=1.1"],
                "color_grading": {
                    "brightness": 0.1,
                    "contrast": 1.05,
                    "saturation": 1.1,
                    "gamma": 0.9,
                    "hue": 0.0,
                },
                "available_tiers": ["pro", "plus", "enterprise"],
                "requires_gpu": False,
            },
            # Premium styles (Plus tier)
            "cinematic_pro": {
                "name": "Cinematic Pro",
                "category": "premium",
                "description": "Advanced cinematic look with film grain",
                "ffmpeg_filters": [
                    "eq=brightness=0.05:contrast=1.15:saturation=1.2",
                    "colorbalance=rs=0.12:gs=0.03:bs=-0.08",
                    "unsharp=7:7:0.8:7:7:0.8",
                    "noise=alls=5:allf=t",
                ],
                "color_grading": {
                    "brightness": 0.05,
                    "contrast": 1.15,
                    "saturation": 1.2,
                    "gamma": 0.98,
                    "hue": 3.0,
                },
                "available_tiers": ["plus", "enterprise"],
                "requires_gpu": True,
            },
            "artistic": {
                "name": "Artistic",
                "category": "premium",
                "description": "Creative, artistic effect with vibrant colors",
                "ffmpeg_filters": [
                    "eq=brightness=0.1:contrast=1.2:saturation=1.3",
                    "curves=preset=vintage",
                    "hue=s=1.2",
                ],
                "color_grading": {
                    "brightness": 0.1,
                    "contrast": 1.2,
                    "saturation": 1.3,
                    "gamma": 0.9,
                    "hue": 15.0,
                },
                "available_tiers": ["plus", "enterprise"],
                "requires_gpu": True,
            },
            "retro": {
                "name": "Retro",
                "category": "premium",
                "description": "80s retro style with film effects",
                "ffmpeg_filters": [
                    "eq=brightness=0.05:contrast=1.1:saturation=1.15",
                    "colorbalance=rs=0.15:gs=0.05:bs=-0.1",
                    "noise=alls=15:allf=t",
                ],
                "color_grading": {
                    "brightness": 0.05,
                    "contrast": 1.1,
                    "saturation": 1.15,
                    "gamma": 1.02,
                    "hue": 10.0,
                },
                "available_tiers": ["plus", "enterprise"],
                "requires_gpu": False,
            },
            "futuristic": {
                "name": "Futuristic",
                "category": "premium",
                "description": "Cyberpunk, sci-fi aesthetic",
                "ffmpeg_filters": [
                    "eq=brightness=0.05:contrast=1.2:saturation=1.25",
                    "colorbalance=rs=0.2:gs=-0.1:bs=0.3",
                    "hue=h=20",
                ],
                "color_grading": {
                    "brightness": 0.05,
                    "contrast": 1.2,
                    "saturation": 1.25,
                    "gamma": 0.95,
                    "hue": 20.0,
                },
                "available_tiers": ["plus", "enterprise"],
                "requires_gpu": True,
            },
        }

    def apply_styles(
        self, video_path: str, style_names: List[str], tier: Tier
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

        # 🔥 LOG the received tier
        logger.info(f"🎨 Applying styles: {style_names}")
        logger.info(f"🎨 User tier received: {tier}")
        logger.info(f"🎨 Tier type: {type(tier)}")

        # Convert string to Tier enum if needed
        if isinstance(tier, str):
            from core.domain.entities.user import Tier

            tier = Tier(tier.lower())
            logger.info(f"🎨 Converted tier to: {tier}")

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
                "path": video_path,
                "applied_styles": [],
                "cost": 0.0,
                "success": True,
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
                    input_path=current_input, output_path=temp_output, style=style
                )

                if success:
                    applied_styles.append(style["name"])
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
                "path": output_path,
                "applied_styles": applied_styles,
                "cost": total_cost,
                "success": True,
                "output_dir": temp_dir,
            }

        except Exception as e:
            # Cleanup on error
            if os.path.exists(temp_dir):
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

            raise ProcessingError(
                f"Style application failed: {str(e)}", step="style_application"
            )

    def _apply_single_style(
        self, input_path: str, output_path: str, style: Dict[str, Any]
    ) -> bool:
        """Apply a single style to video."""
        # Build FFmpeg command
        cmd = ["ffmpeg", "-i", input_path, "-y"]

        # Add video filters
        filters = style.get("ffmpeg_filters", [])
        if filters:
            filter_string = ",".join(filters)
            cmd.extend(["-vf", filter_string])

        # Add color grading if specified
        color_grading = style.get("color_grading", {})
        if color_grading:
            color_filters = []

            if "brightness" in color_grading:
                color_filters.append(f"eq=brightness={color_grading['brightness']}")

            if "contrast" in color_grading:
                color_filters.append(f"eq=contrast={color_grading['contrast']}")

            if "saturation" in color_grading:
                color_filters.append(f"eq=saturation={color_grading['saturation']}")

            if "gamma" in color_grading:
                color_filters.append(f"eq=gamma={color_grading['gamma']}")

            if "hue" in color_grading:
                color_filters.append(f"hue=h={color_grading['hue']}")

            if color_filters:
                if "-vf" in cmd:
                    # Append to existing filter
                    idx = cmd.index("-vf")
                    cmd[idx + 1] = f"{cmd[idx + 1]},{','.join(color_filters)}"
                else:
                    cmd.extend(["-vf", ",".join(color_filters)])

        # Add text overlay if enabled
        text_overlay = style.get("text_overlay", {})
        if text_overlay.get("enabled", False):
            text = text_overlay.get("text", "")
            font = text_overlay.get("font", "Arial")
            color = text_overlay.get("color", "white")
            size = text_overlay.get("size", 24)
            position = text_overlay.get("position", "top")

            # Convert position to drawtext coordinates
            if position == "top":
                x = "(w-text_w)/2"
                y = "20"
            elif position == "bottom":
                x = "(w-text_w)/2"
                y = "h-text_h-20"
            else:  # center
                x = "(w-text_w)/2"
                y = "(h-text_h)/2"

            drawtext_filter = f"drawtext=text='{text}':fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf:fontcolor={color}:fontsize={size}:x={x}:y={y}"

            if "-vf" in cmd:
                idx = cmd.index("-vf")
                cmd[idx + 1] = f"{cmd[idx + 1]},{drawtext_filter}"
            else:
                cmd.extend(["-vf", drawtext_filter])

        # Add output settings
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "copy",  # Keep original audio
                output_path,
            ]
        )

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

    def get_all_styles_with_availability(self, user_tier) -> List[Dict[str, Any]]:
        """Return ALL styles with availability info, available styles first."""

        # Define all video styles (complete list)
        all_styles = {
            "cinematic": {
                "name": "Cinematic",
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            "bright": {
                "name": "Bright & Vibrant",
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            "educational": {
                "name": "Educational",
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            "gaming": {
                "name": "Gaming",
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
            },
            "vlog": {
                "name": "Vlog",
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
            },
            "travel": {
                "name": "Travel",
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
            },
            "professional": {
                "name": "Professional",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "documentary": {
                "name": "Documentary",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "wedding": {
                "name": "Wedding",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "corporate": {
                "name": "Corporate",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "real_estate": {
                "name": "Real Estate",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "cinematic_pro": {
                "name": "Cinematic Pro",
                "available_tiers": ["plus", "enterprise"],
            },
            "artistic": {
                "name": "Artistic",
                "available_tiers": ["plus", "enterprise"],
            },
            "retro": {
                "name": "Retro",
                "available_tiers": ["plus", "enterprise"],
            },
            "futuristic": {
                "name": "Futuristic",
                "available_tiers": ["plus", "enterprise"],
            },
        }

        tier_str = (
            user_tier.value.lower()
            if hasattr(user_tier, "value")
            else str(user_tier).lower()
        )

        # Build list with availability
        styles_list = []
        for style_id, style in all_styles.items():
            available_tiers = style.get("available_tiers", [])
            is_available = tier_str in available_tiers

            styles_list.append(
                {
                    "id": style_id,
                    "name": style["name"],
                    "description": style.get("description", ""),
                    "available": is_available,
                    "required_tier": (
                        available_tiers[0] if available_tiers else "enterprise"
                    ),
                    "category": style.get("category", "basic"),
                }
            )

        # 🔥 FIX: Split into available and unavailable, sort each group alphabetically
        available_styles = [s for s in styles_list if s["available"]]
        unavailable_styles = [s for s in styles_list if not s["available"]]

        # Sort each group alphabetically by name
        available_styles.sort(key=lambda x: x["name"])
        unavailable_styles.sort(key=lambda x: x["name"])

        # Combine: available first, then unavailable
        return available_styles + unavailable_styles

    def get_all_styles(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all styles, optionally filtered by category."""
        if category:
            return [
                style
                for style in self._styles.values()
                if style.get("category") == category
            ]
        else:
            return list(self._styles.values())

    def get_styles_for_tier(self, tier) -> List[Dict[str, Any]]:
        """Get ALL styles with availability info for user tier."""
        tier_str = tier.value.lower() if hasattr(tier, "value") else str(tier).lower()

        styles_list = []
        for style_id, style in self._styles.items():
            available_tiers = style.get("available_tiers", [])
            is_available = tier_str in available_tiers

            styles_list.append(
                {
                    "id": style_id,
                    "name": style.get("name", style_id),
                    "description": style.get("description", ""),
                    "available": is_available,
                    "required_tier": (
                        available_tiers[0] if available_tiers else "enterprise"
                    ),
                    "category": style.get("category", "basic"),
                }
            )

        # Sort alphabetically by name
        styles_list.sort(key=lambda x: x["name"])

        return styles_list

    def get_thumbnail_styles_for_tier(self, tier) -> List[Dict[str, Any]]:
        """Get thumbnail styles that match video styles for consistency."""

        # Define thumbnail styles that match video styles
        thumbnail_styles = {
            "cinematic": {
                "name": "Cinematic",
                "description": "Movie poster style matching Cinematic video style",
                "video_style_match": "cinematic",
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            "bright": {
                "name": "Bright & Vibrant",
                "description": "Vibrant style matching Bright video style",
                "video_style_match": "bright",
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            "gaming": {
                "name": "Gaming",
                "description": "High-energy gaming style",
                "video_style_match": "gaming",
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
            },
            "educational": {
                "name": "Educational",
                "description": "Clean, informative style",
                "video_style_match": "educational",
                "available_tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            "vlog": {
                "name": "Vlog",
                "description": "Casual, personal style",
                "video_style_match": "vlog",
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
            },
            "professional": {
                "name": "Professional",
                "description": "Corporate, business style",
                "video_style_match": "professional",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "documentary": {
                "name": "Documentary",
                "description": "Authentic, natural style",
                "video_style_match": "documentary",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "travel": {
                "name": "Travel",
                "description": "Warm, inviting style",
                "video_style_match": "travel",
                "available_tiers": ["starter", "pro", "plus", "enterprise"],
            },
            "wedding": {
                "name": "Wedding",
                "description": "Romantic, soft style",
                "video_style_match": "wedding",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "corporate": {
                "name": "Corporate",
                "description": "Polished, trustworthy style",
                "video_style_match": "corporate",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "real_estate": {
                "name": "Real Estate",
                "description": "Bright, spacious style",
                "video_style_match": "real_estate",
                "available_tiers": ["pro", "plus", "enterprise"],
            },
            "cinematic_pro": {
                "name": "Cinematic Pro",
                "description": "Advanced cinematic style",
                "video_style_match": "cinematic_pro",
                "available_tiers": ["plus", "enterprise"],
            },
            "artistic": {
                "name": "Artistic",
                "description": "Creative, artistic style",
                "video_style_match": "artistic",
                "available_tiers": ["plus", "enterprise"],
            },
            "retro": {
                "name": "Retro",
                "description": "80s retro style",
                "video_style_match": "retro",
                "available_tiers": ["plus", "enterprise"],
            },
            "futuristic": {
                "name": "Futuristic",
                "description": "Cyberpunk, sci-fi style",
                "video_style_match": "futuristic",
                "available_tiers": ["plus", "enterprise"],
            },
        }

        tier_str = tier.value.lower() if hasattr(tier, "value") else str(tier).lower()

        styles_list = []
        for style_id, style in thumbnail_styles.items():
            available_tiers = style.get("available_tiers", [])
            is_available = tier_str in available_tiers

            styles_list.append(
                {
                    "id": style_id,
                    "name": style["name"],
                    "description": style["description"],
                    "available": is_available,
                    "video_style_match": style.get("video_style_match", style_id),
                    "required_tier": (
                        available_tiers[0] if available_tiers else "enterprise"
                    ),
                }
            )

        return styles_list

    def is_style_available(self, style_name: str, tier: Tier) -> bool:
        """Check if style is available for user tier."""
        style = self.get_style(style_name)
        if not style:
            return False

        tier_str = tier.value.lower()
        return tier_str in style.get("available_tiers", [])

    def _calculate_style_cost(self, style: Dict[str, Any], tier: Tier) -> float:
        """Calculate cost for applying a style."""
        # Base cost per style
        base_cost = 0.001  # $0.001 per style application

        # Adjust based on complexity
        complexity_factors = {
            "basic": 1.0,
            "cinematic": 1.2,
            "gaming": 1.5,
            "educational": 1.0,
            "social_media": 1.1,
            "professional": 1.3,
            "artistic": 1.8,
            "custom": 2.0,
        }

        category = style.get("category", "basic")
        complexity = complexity_factors.get(category, 1.0)

        # GPU requirement adds cost
        if style.get("requires_gpu", False):
            complexity *= 1.5

        # Calculate cost
        cost = base_cost * complexity

        # Apply tier adjustments
        tier_multipliers = {
            Tier.FREE: 1.0,
            Tier.STARTER: 1.0,
            Tier.PRO: 1.0,
            Tier.PLUS: 1.0,
            Tier.ENTERPRISE: 1.0,
        }

        multiplier = tier_multipliers.get(tier, 1.0)

        return cost * multiplier

    def _increment_style_usage(self, style_name: str):
        """Increment style usage count."""
        if style_name in self._styles:
            self._styles[style_name]["usage_count"] = (
                self._styles[style_name].get("usage_count", 0) + 1
            )
            self._save_styles(self._styles)

    def create_custom_style(
        self,
        name: str,
        category: str,
        description: str,
        ffmpeg_filters: List[str],
        color_grading: Dict[str, float],
        created_by: str,
        available_tiers: List[str] = None,
    ) -> Dict[str, Any]:
        """Create a custom video style."""
        if name in self._styles:
            raise ProcessingError(f"Style '{name}' already exists")

        if available_tiers is None:
            available_tiers = ["pro", "plus", "enterprise"]

        custom_style = {
            "name": name,
            "category": category,
            "description": description,
            "ffmpeg_filters": ffmpeg_filters,
            "color_grading": color_grading,
            "transitions": [],
            "text_overlay": {"enabled": False},
            "prompt_template": f"custom {category} style: {description}",
            "negative_prompt": "",
            "style_weight": 0.5,
            "available_tiers": available_tiers,
            "requires_gpu": False,
            "created_by": created_by,
            "is_public": False,
            "usage_count": 0,
        }

        self._styles[name] = custom_style
        self._save_styles(self._styles)

        return custom_style

    def get_popular_styles(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get most popular styles by usage count."""
        all_styles = self.get_all_styles()
        sorted_styles = sorted(
            all_styles, key=lambda x: x.get("usage_count", 0), reverse=True
        )
        return sorted_styles[:limit]
