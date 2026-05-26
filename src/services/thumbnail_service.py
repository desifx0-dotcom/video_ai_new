"""
Thumbnail generation service with tier-based model selection, one-at-a-time regeneration,
AND actual thumbnail style application using FFmpeg filters.
"""

import os
import tempfile
import random
import uuid
import subprocess
from typing import Dict, Any, List, Optional, Tuple
import logging
import json
from datetime import datetime
from pathlib import Path

from core.domain.value_objects.tier import Tier
from core.exceptions import (
    ProcessingError,
    ExternalServiceError,
    TierLimitExceeded,
    InsufficientCreditsError,
)
from providers.stability_provider import StabilityProvider
from providers.openai_provider import OpenAIProvider
from providers.ffmpeg_provider import FFmpegProvider
from services.tier_service import TierService

logger = logging.getLogger(__name__)


class ThumbnailService:
    """Thumbnail generation service with tier-based model selection and style application."""

    # Unique concept templates for true variety
    CONCEPT_STYLES = [
        "dramatic lighting, intense mood, cinematic",
        "bright and colorful, vibrant, eye-catching",
        "minimalist, clean design, modern",
        "action shot, dynamic movement, energetic",
        "close-up, emotional, human element",
        "mysterious, intriguing, dark atmosphere",
        "professional, corporate, polished",
        "funny, humorous, playful",
        "educational, informative, clean",
        "futuristic, cyberpunk, tech-inspired",
        "vintage, retro, nostalgic",
        "romantic, soft, dreamy",
        "scary, suspenseful, thriller",
        "whimsical, magical, fantasy",
        "abstract, artistic, creative",
        "bold typography, text-focused",
        "collage style, mixed media",
        "watercolor, artistic, soft",
        "neon glow, cyber, electric",
        "rustic, natural, organic",
    ]

    # Cost per thumbnail by model
    MODEL_COSTS = {
        "sd-3.5-medium": 0.002,
        "sd-xl": 0.005,
        "sd-3.6-turbo": 0.008,
        "dall-e-3": 0.040,
    }

    # THUMBNAIL STYLE FILTERS (FFmpeg filters for post-processing)
    THUMBNAIL_STYLE_FILTERS = {
        # Basic styles (all tiers)
        "default": None,
        "cinematic": "eq=brightness=0.05:contrast=1.15:saturation=1.1,unsharp=5:5:0.8",
        "bright": "eq=brightness=0.12:contrast=1.08:saturation=1.2",
        "dark": "eq=brightness=-0.1:contrast=1.18:saturation=0.88,colorbalance=gs=-0.04",
        "vlog": "eq=brightness=0.08:contrast=1.02:saturation=1.08,colorbalance=rs=0.02:gs=0.01:bs=-0.02",
        
        # Starter tier
        "educational": "eq=brightness=0.03:contrast=1.1:saturation=1.05,unsharp=3:3:0.5",
        "gaming": "eq=saturation=1.25:contrast=1.15:brightness=0.03,unsharp=5:5:1.0,colorbalance=rs=0.05:gs=0.03:bs=-0.02",
        "travel": "eq=saturation=1.18:contrast=1.05:brightness=0.05,colorbalance=rs=0.03:gs=0.02:bs=0.04",
        
        # Pro tier
        "professional": "eq=contrast=1.08:saturation=0.98,unsharp=3:3:0.4",
        "documentary": "eq=brightness=0:contrast=1.02:saturation=0.95,colorbalance=rs=-0.02:gs=-0.01:bs=-0.01",
        "wedding": "eq=brightness=0.07:contrast=1.02:saturation=1.05,colorbalance=rs=0.04:gs=0.02:bs=0.03",
        "corporate": "eq=brightness=0.03:contrast=1.08:saturation=0.98,unsharp=2:2:0.3",
        "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.06,unsharp=4:4:0.6",
        "action": "eq=contrast=1.2:brightness=0.03,unsharp=5:5:1.2,eq=saturation=1.1",
        "minimalist": "eq=saturation=0.92:contrast=1.05,unsharp=2:2:0.2",
        "vintage": "eq=brightness=0.02:contrast=0.92:saturation=0.88,colorbalance=rs=-0.03:gs=-0.02:bs=0.05",
        
        # Plus tier
        "cinematic_pro": "eq=brightness=0.06:contrast=1.2:saturation=1.12,unsharp=5:5:1.0,colorbalance=rs=0.02:gs=0.01:bs=-0.01",
        "artistic": "eq=saturation=1.2:contrast=1.08:brightness=0.03,unsharp=4:4:0.8,colorbalance=rs=0.04:gs=0.02:bs=0.06",
        "retro": "eq=brightness=0.02:contrast=0.92:saturation=0.85,colorbalance=rs=-0.04:gs=-0.03:bs=0.08",
        "futuristic": "eq=saturation=1.25:contrast=1.15:brightness=0.04,unsharp=5:5:1.0,colorbalance=rs=0.06:gs=0.04:bs=0.1",
        "cartoon": "eq=saturation=1.2:contrast=1.1,edgedetect=low=0.1:high=0.3,unsharp=3:3:0.5",
        "glamour": "eq=brightness=0.05:contrast=1.02:saturation=1.1,unsharp=4:4:0.7,colorbalance=rs=0.05:gs=0.03:bs=0.03",
        "mystery": "eq=brightness=-0.05:contrast=1.15:saturation=0.92,colorbalance=gs=-0.04,unsharp=3:3:0.5",
        "tech": "eq=saturation=1.18:contrast=1.12:brightness=0.03,unsharp=5:5:0.9,colorbalance=rs=0.06:gs=0.04:bs=0.09",
        "dramatic": "eq=brightness=-0.03:contrast=1.25:saturation=1.1,unsharp=5:5:1.2",
        "warm": "eq=brightness=0.04:contrast=1.02:saturation=1.05,colorbalance=rs=0.06:gs=0.02:bs=-0.03",
        "cool": "eq=brightness=0.02:contrast=1.03:saturation=1.02,colorbalance=rs=-0.02:gs=0:bs=0.05",
        "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
        "black_and_white": "hue=s=0,eq=contrast=1.1",
        "text_heavy": "eq=brightness=0.02:contrast=1.2:saturation=1.05,unsharp=3:3:0.8",
        
        # Enterprise tier
        "hollywood": "eq=brightness=0.04:contrast=1.18:saturation=1.15,unsharp=5:5:1.1,colorbalance=rs=0.03:gs=0.02:bs=-0.02",
        "dreamy": "eq=brightness=0.06:contrast=1.02:saturation=1.08,unsharp=3:3:0.4,colorbalance=rs=0.04:gs=0.03:bs=0.07",
        "neon": "eq=saturation=1.3:contrast=1.2:brightness=0.05,colorbalance=rs=0.08:gs=0.05:bs=0.12,unsharp=4:4:0.8",
        "pastel": "eq=saturation=0.85:contrast=1.02:brightness=0.07,colorbalance=rs=0.02:gs=0.02:bs=0.02",
        "hdr": "eq=contrast=1.15:saturation=1.12,brightness=0.02,unsharp=5:5:1.0",
    }

    def __init__(self, redis_client=None):
        self.stability = StabilityProvider()
        self.openai = OpenAIProvider()
        self.ffmpeg = FFmpegProvider()
        self.tier_service = TierService(redis_client)
        self._redis = redis_client

        # In-memory fallback for development
        self._generated_thumbnails = {}
        self._used_concepts = {}
        self._regeneration_count = {}

    def _normalize_tier(self, tier) -> Tier:
        """Convert tier to Tier enum safely."""
        if isinstance(tier, Tier):
            return tier
        if isinstance(tier, str):
            # Try to convert string to Tier enum
            tier_lower = tier.lower()
            for t in Tier:
                if t.value == tier_lower:
                    return t
            return Tier.FREE
        return Tier.FREE

    def _get_tier_value(self, tier) -> str:
        """Get tier string value safely."""
        if isinstance(tier, Tier):
            return tier.value
        return str(tier).lower()

    def get_all_thumbnail_styles(self, tier: Tier) -> List[Dict[str, Any]]:
        """Get all available thumbnail styles with tier availability."""

        all_styles = [
            # ========== FREE TIER STYLES ==========
            {
                "id": "default",
                "name": "Default",
                "description": "Standard thumbnail style - no effects applied",
                "available": True,
                "required_tier": "free",
            },
            {
                "id": "cinematic",
                "name": "Cinematic",
                "description": "Movie-style thumbnail with dramatic lighting and slight sharpening",
                "available": True,
                "required_tier": "free",
            },
            {
                "id": "bright",
                "name": "Bright & Vibrant",
                "description": "High-contrast, colorful thumbnails that pop",
                "available": True,
                "required_tier": "free",
            },
            {
                "id": "educational",
                "name": "Educational",
                "description": "Clean, clear style perfect for tutorials and lessons",
                "available": True,
                "required_tier": "free",
            },
            {
                "id": "vlog",
                "name": "Vlog Style",
                "description": "Warm, personal style for vlog content",
                "available": True,
                "required_tier": "free",
            },

            # ========== STARTER TIER STYLES ==========
            {
                "id": "dark",
                "name": "Dark & Moody",
                "description": "Dramatic dark-themed thumbnails with enhanced contrast",
                "available": True,
                "required_tier": "starter",
            },
            {
                "id": "gaming",
                "name": "Gaming Style",
                "description": "Saturated, high-contrast style for gaming content",
                "available": True,
                "required_tier": "starter",
            },
            {
                "id": "travel",
                "name": "Travel Style",
                "description": "Warm, vibrant style for travel and adventure videos",
                "available": True,
                "required_tier": "starter",
            },
            {
                "id": "action",
                "name": "Action Shot",
                "description": "Dynamic, motion-focused thumbnails with sharpening",
                "available": True,
                "required_tier": "starter",
            },
            {
                "id": "minimalist",
                "name": "Minimalist",
                "description": "Clean, simple design with subtle adjustments",
                "available": True,
                "required_tier": "starter",
            },

            # ========== PRO TIER STYLES ==========
            {
                "id": "professional",
                "name": "Professional",
                "description": "Polished, corporate-style thumbnails",
                "available": True,
                "required_tier": "pro",
            },
            {
                "id": "documentary",
                "name": "Documentary",
                "description": "Authentic, filmic style for documentary content",
                "available": True,
                "required_tier": "pro",
            },
            {
                "id": "wedding",
                "name": "Wedding",
                "description": "Soft, romantic style for wedding videos",
                "available": True,
                "required_tier": "pro",
            },
            {
                "id": "corporate",
                "name": "Corporate",
                "description": "Clean, professional look for business content",
                "available": True,
                "required_tier": "pro",
            },
            {
                "id": "real_estate",
                "name": "Real Estate",
                "description": "Enhanced colors and sharpness for property videos",
                "available": True,
                "required_tier": "pro",
            },
            {
                "id": "vintage",
                "name": "Vintage",
                "description": "Retro, film-style look with color balance adjustments",
                "available": True,
                "required_tier": "pro",
            },
            {
                "id": "text_heavy",
                "name": "Text Heavy",
                "description": "Thumbnails optimized for text overlay",
                "available": True,
                "required_tier": "pro",
            },

            # ========== PLUS TIER STYLES ==========
            {
                "id": "cinematic_pro",
                "name": "Cinematic Pro",
                "description": "Advanced cinematic style with color grading",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "artistic",
                "name": "Artistic",
                "description": "Creative, artistic style with unique color balance",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "retro",
                "name": "Retro",
                "description": "80s/90s retro style with vintage color tones",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "futuristic",
                "name": "Futuristic",
                "description": "Cyberpunk, sci-fi style with blue/cyan tones",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "cartoon",
                "name": "Cartoon",
                "description": "Illustrated, animated style with edge detection",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "glamour",
                "name": "Glamour",
                "description": "Polished, magazine-style look",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "mystery",
                "name": "Mystery",
                "description": "Intriguing, suspenseful dark style",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "tech",
                "name": "Tech",
                "description": "Futuristic, cyberpunk style with neon tones",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "dramatic",
                "name": "Dramatic",
                "description": "High-contrast, intense style",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "warm",
                "name": "Warm",
                "description": "Golden, warm color tones",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "cool",
                "name": "Cool",
                "description": "Blue, cool color tones",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "sepia",
                "name": "Sepia",
                "description": "Classic sepia-toned vintage style",
                "available": True,
                "required_tier": "plus",
            },
            {
                "id": "black_and_white",
                "name": "Black & White",
                "description": "Classic monochrome style",
                "available": True,
                "required_tier": "plus",
            },

            # ========== ENTERPRISE TIER STYLES ==========
            {
                "id": "hollywood",
                "name": "Hollywood",
                "description": "Premium cinematic style with professional color grading",
                "available": True,
                "required_tier": "enterprise",
            },
            {
                "id": "dreamy",
                "name": "Dreamy",
                "description": "Soft, ethereal style with gentle colors",
                "available": True,
                "required_tier": "enterprise",
            },
            {
                "id": "neon",
                "name": "Neon",
                "description": "Vibrant neon/cyberpunk style",
                "available": True,
                "required_tier": "enterprise",
            },
            {
                "id": "pastel",
                "name": "Pastel",
                "description": "Soft, pastel color tones",
                "available": True,
                "required_tier": "enterprise",
            },
            {
                "id": "hdr",
                "name": "HDR",
                "description": "High dynamic range style for maximum detail",
                "available": True,
                "required_tier": "enterprise",
            },
            {
                "id": "custom",
                "name": "Custom",
                "description": "Custom style based on video content",
                "available": False,
                "required_tier": "enterprise",
            },
        ]
        
        tier = self._normalize_tier(tier)
        user_tier_str = tier.value
        tier_rank = {"free": 0, "starter": 1, "pro": 2, "plus": 3, "enterprise": 4}
        user_rank = tier_rank.get(user_tier_str, 0)

        for style in all_styles:
            required_rank = tier_rank.get(style["required_tier"], 0)
            style["available"] = user_rank >= required_rank

        # Sort alphabetically by name
        all_styles.sort(key=lambda x: x["name"])

        return all_styles

    def _apply_thumbnail_style(self, image_path: str, style: str) -> str:
        """
        Apply style filter to thumbnail using FFmpeg.

        Args:
            image_path: Path to source image
            style: Style identifier (cinematic, bright, dark, etc.)

        Returns:
            Path to styled image (original if style not found or error)
        """
        if not image_path or not os.path.exists(image_path):
            return image_path

        filter_chain = self.THUMBNAIL_STYLE_FILTERS.get(style)
        if filter_chain is None:
            logger.debug(f"No filter for thumbnail style: {style}")
            return image_path

        # Create output path
        base_name = os.path.splitext(image_path)[0]
        output_path = f"{base_name}_styled_{style}.jpg"

        cmd = [
            "ffmpeg",
            "-i",
            image_path,
            "-vf",
            filter_chain,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and os.path.exists(output_path):
                # Replace original with styled version
                os.remove(image_path)
                os.rename(output_path, image_path)
                logger.info(
                    f"✅ Applied thumbnail style '{style}' to {os.path.basename(image_path)}"
                )
            else:
                logger.warning(
                    f"Failed to apply style '{style}': {result.stderr[:100]}"
                )
                if os.path.exists(output_path):
                    os.remove(output_path)
        except Exception as e:
            logger.error(f"Error applying thumbnail style '{style}': {e}")

        return image_path

    def _apply_thumbnail_styles_to_all(
        self, thumbnail_paths: List[str], style: str
    ) -> List[str]:
        """Apply style to all thumbnails in list."""
        if not style or style == "default":
            return thumbnail_paths

        styled_paths = []
        for path in thumbnail_paths:
            styled_path = self._apply_thumbnail_style(path, style)
            styled_paths.append(styled_path)

        return styled_paths

    def generate_thumbnails(
        self,
        video_path: str,
        title: str,
        video_type: str,
        tier: Tier,
        transcription: Optional[str] = None,
        user_id: Optional[str] = None,
        video_id: Optional[str] = None,
        thumbnail_style: str = "default",
    ) -> Dict[str, Any]:
        """Generate initial thumbnails for a video with style application."""
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        tier = self._normalize_tier(tier)

        # Get tier specifications
        tier_spec = self.tier_service.get_tier(tier)
        if not tier_spec:
            raise ProcessingError(f"Invalid tier: {tier}")

        try:
            # Get model and settings based on tier
            model, steps = self._get_model_and_steps(tier)

            # Get counts from tier service
            ai_count = tier_spec.ai_thumbnails
            extracted_count = tier_spec.extracted_frames

            # Generate AI thumbnails with fallback
            ai_thumbnails = []
            total_cost = 0.0

            for i in range(ai_count):
                concept = self._get_new_concept(video_id)
                result = self._generate_single_thumbnail(
                    title=title,
                    video_type=video_type,
                    tier=tier,
                    transcription=transcription,
                    concept=concept,
                    model=model,
                    steps=steps,
                    attempt_number=i + 1,
                )
                if result:
                    # 🔥 APPLY STYLE TO GENERATED THUMBNAIL
                    styled_path = self._apply_thumbnail_style(
                        result["thumbnail"]["path"], thumbnail_style
                    )
                    result["thumbnail"]["path"] = styled_path
                    ai_thumbnails.append(result["thumbnail"])
                    total_cost += result["cost"]
                    self._add_used_concept(video_id, concept)

            # Extract frames from video
            extracted_thumbnails = self._extract_frames(video_path, extracted_count)

            # 🔥 APPLY STYLE TO EXTRACTED FRAMES
            extracted_thumbnails = self._apply_thumbnail_styles_to_all(
                extracted_thumbnails, thumbnail_style
            )

            # Select best thumbnail (first AI thumbnail or first extracted)
            selected = (
                ai_thumbnails[0]["path"]
                if ai_thumbnails
                else (extracted_thumbnails[0] if extracted_thumbnails else None)
            )

            return {
                "success": True,
                "ai_thumbnails": ai_thumbnails,
                "extracted_thumbnails": extracted_thumbnails,
                "selected": selected,
                "cost": total_cost,
                "tier": tier.value,
                "ai_count": len(ai_thumbnails),
                "extracted_count": len(extracted_thumbnails),
                "model": model,
                "video_id": video_id,
                "thumbnail_style": thumbnail_style,
            }

        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            raise ProcessingError(
                f"Thumbnail generation failed: {str(e)}", step="thumbnail_generation"
            )

    def regenerate_thumbnail(
        self,
        video_id: str,
        video_path: str,
        title: str,
        video_type: str,
        tier: Tier,
        transcription: Optional[str] = None,
        user_id: Optional[str] = None,
        thumbnail_style: str = "default",
    ) -> Dict[str, Any]:
        """Regenerate a single thumbnail with a different concept and apply style."""
        # Check regeneration limits
        current_count = self._get_regeneration_count(video_id)
        max_regenerations = self.tier_service.get_thumbnail_regenerations(tier)

        tier = self._normalize_tier(tier)

        if current_count >= max_regenerations:
            raise TierLimitExceeded(
                "thumbnail_regenerations",
                current_count,
                max_regenerations,
                message=f"You've used {current_count} of {max_regenerations} thumbnail regenerations",
            )

        # Get tier specifications
        tier_spec = self.tier_service.get_tier(tier)
        if not tier_spec:
            raise ProcessingError(f"Invalid tier: {tier}")

        # Get model based on tier
        model, steps = self._get_model_and_steps(tier)

        # Get a truly different concept
        concept = self._get_new_concept(video_id, force_different=True)

        # Generate new thumbnail
        result = self._generate_single_thumbnail(
            title=title,
            video_type=video_type,
            tier=tier,
            transcription=transcription,
            concept=concept,
            model=model,
            steps=steps,
            attempt_number=current_count + 1,
            is_regeneration=True,
        )

        if result:
            # 🔥 APPLY STYLE TO REGENERATED THUMBNAIL
            styled_path = self._apply_thumbnail_style(
                result["thumbnail"]["path"], thumbnail_style
            )
            result["thumbnail"]["path"] = styled_path

            self._add_used_concept(video_id, concept)
            new_count = self._increment_regeneration_count(video_id)

            return {
                "success": True,
                "thumbnail": result["thumbnail"],
                "concept": concept,
                "regeneration_count": new_count,
                "max_regenerations": max_regenerations,
                "model": model,
                "cost": result["cost"],
                "thumbnail_style": thumbnail_style,
            }
        else:
            return {"success": False, "error": "Failed to generate thumbnail"}

    def _generate_single_thumbnail(
        self,
        title: str,
        video_type: str,
        tier: Tier,
        concept: str,
        model: str,
        steps: int,
        attempt_number: int = 1,
        is_regeneration: bool = False,
        transcription: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate a single thumbnail with specific concept."""
        prompt = self._build_prompt(
            title=title,
            video_type=video_type,
            concept=concept,
            transcription=transcription,
            attempt_number=attempt_number,
            is_regeneration=is_regeneration,
        )

        try:
            image_data = self.stability.generate_image(
                prompt=prompt,
                model=model,
                steps=steps,
                cfg_scale=7.0,
                width=1280,
                height=720,
            )

            thumbnail_path = self._save_thumbnail(
                image_data, f"ai_thumbnail_{attempt_number}_{uuid.uuid4().hex[:8]}"
            )

            return {
                "thumbnail": {
                    "id": str(uuid.uuid4()),
                    "path": thumbnail_path,
                    "concept": concept,
                    "prompt": prompt,
                    "model": model,
                    "created_at": datetime.utcnow().isoformat(),
                    "is_regeneration": is_regeneration,
                },
                "cost": self.MODEL_COSTS.get(model, 0.002),
            }

        except Exception as e:
            logger.error(f"Failed to generate thumbnail with {model}: {e}")

            if tier in [Tier.PLUS, Tier.ENTERPRISE]:
                try:
                    return self._generate_with_dalle(title, concept)
                except Exception as e2:
                    logger.error(f"DALL·E 3 fallback also failed: {e2}")

            return None

    def _generate_with_dalle(
        self, title: str, concept: str
    ) -> Optional[Dict[str, Any]]:
        """Generate thumbnail with DALL·E 3."""
        dalle_prompt = f"A professional YouTube thumbnail for a video titled: '{title}'. Style: {concept}. High quality, 4K resolution, engaging, clickable."

        response = self.openai.generate_image(
            prompt=dalle_prompt,
            model="dall-e-3",
            size="1024x1024",
            quality="hd",
        )

        thumbnail_path = self._save_thumbnail(
            response, f"ai_thumbnail_dalle_{uuid.uuid4().hex[:8]}"
        )

        return {
            "thumbnail": {
                "id": str(uuid.uuid4()),
                "path": thumbnail_path,
                "concept": concept,
                "prompt": dalle_prompt,
                "model": "dall-e-3",
                "created_at": datetime.utcnow().isoformat(),
                "is_regeneration": True,
            },
            "cost": self.MODEL_COSTS["dall-e-3"],
        }

    def _build_prompt(
        self,
        title: str,
        video_type: str,
        concept: str,
        transcription: Optional[str],
        attempt_number: int,
        is_regeneration: bool,
    ) -> str:
        """Build prompt for thumbnail generation."""
        base_context = f"A professional YouTube/TikTok style thumbnail for a video titled: '{title}'"

        if video_type == "speech" and transcription:
            key_phrases = self._extract_key_phrases(transcription, max_phrases=3)
            context = f"{base_context}. The video content is about: {key_phrases[:200]}"
        elif video_type == "silent":
            context = (
                f"{base_context}. This is a silent video with engaging visual content."
            )
        else:
            context = base_context

        if is_regeneration:
            context += f" This is variation #{attempt_number}. Make it distinctly different from previous versions."

        prompt = f"{context}. Style: {concept}. High quality, 4K resolution, professional thumbnail design, vibrant colors, clear focal point, suitable for YouTube/TikTok."

        return prompt

    def _get_new_concept(self, video_id: str, force_different: bool = False) -> str:
        """Get a concept different from previously used ones."""
        used = self._get_used_concepts(video_id)
        available = [c for c in self.CONCEPT_STYLES if c not in used]

        if not available:
            base_concept = random.choice(self.CONCEPT_STYLES[:10])
            count = len(used)
            return f"{base_concept} (variation {count + 1} - enhanced)"

        return random.choice(available)

    def _extract_frames(self, video_path: str, count: int) -> List[str]:
        """Extract frames from video."""
        if count <= 0:
            return []

        metadata = self.ffmpeg.get_video_metadata(video_path)
        duration = metadata.get("duration", 60)

        if count == 1:
            intervals = [duration / 2]
        else:
            intervals = [duration * (i + 1) / (count + 1) for i in range(count)]

        frames = []
        for i, interval in enumerate(intervals):
            try:
                frame_dir = tempfile.mkdtemp(prefix="video_ai_frames_")
                frame_path = os.path.join(frame_dir, f"frame_{i:03d}.jpg")
                self.ffmpeg.extract_frame_at_time(
                    video_path, interval, frame_path, width=640, height=360
                )
                if os.path.exists(frame_path):
                    frames.append(frame_path)
            except Exception as e:
                logger.error(f"Failed to extract frame at {interval}s: {str(e)}")
                continue

        return frames

    def _get_model_and_steps(self, tier: Tier) -> Tuple[str, int]:
        """Get model and steps based on tier."""
        tier_settings = {
            Tier.FREE: ("sd-3.5-medium", 20),
            Tier.STARTER: ("sd-3.5-medium", 30),
            Tier.PRO: ("sd-xl", 40),
            Tier.PLUS: ("sd-3.6-turbo", 50),
            Tier.ENTERPRISE: ("sd-3.6-turbo", 50),
        }
        return tier_settings.get(tier, ("sd-3.5-medium", 20))

    def _extract_key_phrases(self, text: str, max_phrases: int = 3) -> str:
        """Extract key phrases from text."""
        if not text:
            return ""
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 10]
        key_sentences = sentences[:max_phrases]
        if key_sentences:
            return ". ".join(key_sentences)
        return text[:150]

    def _save_thumbnail(self, image_data, filename: str) -> str:
        """
        Save thumbnail image to temporary file with longer TTL.
        """
        import base64
        import tempfile
        from datetime import datetime, timedelta
        
        # Create thumbnails directory (still temp, but with organization)
        thumbnails_dir = Path(tempfile.gettempdir()) / 'video_ai_thumbnails'
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        
        # Create unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = f"{filename}_{timestamp}_{unique_id}.png"
        filepath = thumbnails_dir / safe_filename
        
        # Decode and save
        if isinstance(image_data, str) and image_data.startswith("data:image"):
            import re
            match = re.match(r"data:image/(.+?);base64,(.+)", image_data)
            if match:
                image_data = base64.b64decode(match.group(2))
        elif isinstance(image_data, str):
            return image_data
        
        with open(filepath, "wb") as f:
            f.write(image_data)
        
        # Store metadata with expiry (24 hours)
        expiry_time = datetime.now() + timedelta(hours=24)
        expiry_file = thumbnails_dir / f"{safe_filename}.expiry"
        with open(expiry_file, "w") as f:
            f.write(expiry_time.isoformat())
        
        logger.info(f"✅ Thumbnail saved: {filepath} (expires in 24 hours)")
        
        # Return ABSOLUTE path - your serve_thumbnail needs this
        return str(filepath.absolute())

    def get_thumbnail_history(self, video_id: str) -> List[Dict[str, Any]]:
        """Get thumbnail generation history for a video."""
        history = []
        
        if self._redis:
            import json
            key = f"thumb:{video_id}:history"
            redis_history = self._redis.lrange(key, 0, -1)
            history = [json.loads(h.decode()) for h in redis_history] if redis_history else []
        else:
            history = self._generated_thumbnails.get(video_id, [])
        
        # Convert to relative paths if needed and ensure they exist
        valid_history = []
        base_url = os.getenv('APP_URL', 'http://localhost:5000')
        
        for thumb in history:
            if isinstance(thumb, dict):
                path = thumb.get('path', '')
                # Replace absolute paths with relative
                if path.startswith('C:\\') or path.startswith('/tmp'):
                    # Convert to relative path for URL
                    path = path.replace('\\', '/')
                    thumb['url'] = f"{base_url}/api/v1/videos/thumbnails/{path}"
                else:
                    thumb['url'] = f"{base_url}/api/v1/videos/thumbnails/{path}"
                
                # Also store the original path for serving
                thumb['file_path'] = path
                valid_history.append(thumb)
        
        return valid_history

    def get_regeneration_count(self, video_id: str) -> int:
        """Get number of regenerations for a video."""
        return self._get_regeneration_count(video_id)

    def get_max_regenerations(self, tier: Tier) -> int:
        """Get maximum regenerations allowed for tier."""
        return self.tier_service.get_thumbnail_regenerations(tier)

    def _get_redis_key(self, video_id: str, suffix: str) -> str:
        """Generate Redis key for tracking."""
        return f"thumb:{video_id}:{suffix}"

    def _get_used_concepts(self, video_id: str) -> List[str]:
        """Get used concepts from Redis or memory."""
        if self._redis:
            key = self._get_redis_key(video_id, "concepts")
            concepts = self._redis.lrange(key, 0, -1)
            return [c.decode() for c in concepts] if concepts else []
        return self._used_concepts.get(video_id, [])

    def _add_used_concept(self, video_id: str, concept: str):
        """Track used concept in Redis or memory."""
        if self._redis:
            key = self._get_redis_key(video_id, "concepts")
            self._redis.rpush(key, concept)
            self._redis.expire(key, 2592000)
        else:
            if video_id not in self._used_concepts:
                self._used_concepts[video_id] = []
            self._used_concepts[video_id].append(concept)

    def _get_regeneration_count(self, video_id: str) -> int:
        """Get regeneration count from Redis or memory."""
        if self._redis:
            key = self._get_redis_key(video_id, "regen_count")
            count = self._redis.get(key)
            return int(count) if count else 0
        return self._regeneration_count.get(video_id, 0)

    def _increment_regeneration_count(self, video_id: str) -> int:
        """Increment regeneration count."""
        if self._redis:
            key = self._get_redis_key(video_id, "regen_count")
            new_count = self._redis.incr(key)
            self._redis.expire(key, 2592000)
            return new_count
        new_count = self._regeneration_count.get(video_id, 0) + 1
        self._regeneration_count[video_id] = new_count
        return new_count

