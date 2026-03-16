"""
Thumbnail generation service.
"""
import os
import tempfile
import random
from typing import Dict, Any, List, Optional
import logging

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError, ExternalServiceError
from providers.stability_provider import StabilityProvider
from providers.ffmpeg_provider import FFmpegProvider

logger = logging.getLogger(__name__)

class ThumbnailService:
    """Thumbnail generation service."""
    
    def __init__(self):
        self.stability = StabilityProvider()
        self.ffmpeg = FFmpegProvider()
    
    def generate_thumbnails(
        self,
        video_path: str,
        title: str,
        video_type: str,
        tier: Tier,
        transcription: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate thumbnails for video.
        
        Args:
            video_path: Path to video file
            title: Video title
            video_type: Type of video
            tier: User tier
            transcription: Optional transcription for context
        
        Returns:
            Thumbnail results
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")
        
        try:
            # Generate AI thumbnails
            ai_thumbnails = self._generate_ai_thumbnails(title, video_type, tier, transcription)
            
            # Extract frames from video
            extracted_thumbnails = self._extract_frames(video_path, tier)
            
            # Select best thumbnail
            selected = self._select_best_thumbnail(ai_thumbnails, extracted_thumbnails, title)
            
            # Calculate cost
            cost = self._calculate_cost(tier, len(ai_thumbnails))
            
            return {
                'ai_thumbnails': ai_thumbnails,
                'extracted_thumbnails': extracted_thumbnails,
                'selected': selected,
                'cost': cost,
                'tier': tier.value,
                'ai_count': len(ai_thumbnails),
                'extracted_count': len(extracted_thumbnails)
            }
            
        except Exception as e:
            if "Stability" in str(e) or "SDXL" in str(e):
                raise ExternalServiceError("StabilityAI", str(e))
            else:
                raise ProcessingError(f"Thumbnail generation failed: {str(e)}", step="thumbnail_generation")
    
    def _generate_ai_thumbnails(
        self,
        title: str,
        video_type: str,
        tier: Tier,
        transcription: Optional[str] = None
    ) -> List[str]:
        """Generate AI thumbnails using Stability AI."""
        # Get number of thumbnails based on tier
        count = self._get_ai_thumbnail_count(tier)
        
        if count <= 0:
            return []
        
        # Get model and steps based on tier
        model, steps = self._get_model_and_steps(tier)
        
        # Generate prompts
        prompts = self._generate_prompts(title, video_type, transcription, count)
        
        # Generate images
        thumbnails = []
        
        for i, prompt in enumerate(prompts):
            try:
                image_data = self.stability.generate_image(
                    prompt=prompt,
                    model=model,
                    steps=steps,
                    cfg_scale=7.0,
                    width=1280,
                    height=720
                )
                
                # Save thumbnail
                thumbnail_path = self._save_thumbnail(image_data, f"ai_thumbnail_{i}")
                thumbnails.append(thumbnail_path)
                
            except Exception as e:
                logger.error(f"Failed to generate AI thumbnail {i}: {str(e)}")
                continue
        
        return thumbnails
    
    def _extract_frames(self, video_path: str, tier: Tier) -> List[str]:
        """Extract frames from video."""
        # Get number of frames based on tier
        count = self._get_extracted_thumbnail_count(tier)
        
        if count <= 0:
            return []
        
        # Get video duration
        metadata = self.ffmpeg.get_video_metadata(video_path)
        duration = metadata.get('duration', 60)
        
        # Calculate frame intervals
        intervals = []
        if count == 1:
            intervals = [duration / 2]  # Middle of video
        else:
            # Spread frames throughout video
            interval = duration / (count + 1)
            intervals = [interval * (i + 1) for i in range(count)]
        
        # Extract frames
        frames = []
        
        for i, interval in enumerate(intervals):
            try:
                frame_path = self.ffmpeg.extract_frame(
                    video_path=video_path,
                    timestamp=interval,
                    output_dir=tempfile.gettempdir(),
                    filename=f"frame_{i}"
                )
                
                if frame_path and os.path.exists(frame_path):
                    frames.append(frame_path)
                    
            except Exception as e:
                logger.error(f"Failed to extract frame at {interval}s: {str(e)}")
                continue
        
        return frames
    
    def _select_best_thumbnail(
        self,
        ai_thumbnails: List[str],
        extracted_thumbnails: List[str],
        title: str
    ) -> str:
        """Select the best thumbnail from available options."""
        all_thumbnails = ai_thumbnails + extracted_thumbnails
        
        if not all_thumbnails:
            # No thumbnails available
            return ""
        
        # Simple selection logic
        # In production, you might use AI to analyze and select the best thumbnail
        
        # Prefer AI thumbnails over extracted frames
        if ai_thumbnails:
            # Select first AI thumbnail (could be improved with analysis)
            return ai_thumbnails[0]
        else:
            # Select middle frame from extracted frames
            middle_index = len(extracted_thumbnails) // 2
            return extracted_thumbnails[middle_index]
    
    def _get_ai_thumbnail_count(self, tier: Tier) -> int:
        """Get number of AI thumbnails for tier."""
        tier_counts = {
            Tier.FREE: 1,
            Tier.STARTER: 3,
            Tier.PRO: 5,
            Tier.PLUS: 10,
            Tier.ENTERPRISE: 20
        }
        
        return tier_counts.get(tier, 1)
    
    def _get_extracted_thumbnail_count(self, tier: Tier) -> int:
        """Get number of extracted thumbnails for tier."""
        tier_counts = {
            Tier.FREE: 5,
            Tier.STARTER: 8,
            Tier.PRO: 15,
            Tier.PLUS: 25,
            Tier.ENTERPRISE: 50
        }
        
        return tier_counts.get(tier, 5)
    
    def _get_model_and_steps(self, tier: Tier) -> tuple[str, int]:
        """Get model and steps for AI thumbnail generation."""
        tier_settings = {
            Tier.FREE: ('sd-3.5-medium', 20),
            Tier.STARTER: ('sd-3.5-medium', 30),
            Tier.PRO: ('sd-xl', 40),
            Tier.PLUS: ('sd-3.6-turbo', 50),
            Tier.ENTERPRISE: ('sd-3.6-turbo', 50)
        }
        
        return tier_settings.get(tier, ('sd-3.5-medium', 20))
    
    def _generate_prompts(
        self,
        title: str,
        video_type: str,
        transcription: Optional[str],
        count: int
    ) -> List[str]:
        """Generate prompts for AI thumbnail generation."""
        prompts = []
        
        # Base prompt
        base_context = f"A YouTube/TikTok style thumbnail for a video titled: '{title}'"
        
        if video_type == 'speech' and transcription:
            # Extract key phrases from transcription
            key_phrases = self._extract_key_phrases(transcription)
            context = f"{base_context}. The video is about: {key_phrases}"
        elif video_type == 'silent':
            context = f"{base_context}. This is a silent video with engaging visual content."
        else:
            context = base_context
        
        # Generate different prompt variations
        styles = [
            "cinematic, dramatic lighting, professional photography",
            "bright, colorful, vibrant, eye-catching, social media style",
            "minimalist, clean, elegant, modern design",
            "text-heavy with bold typography, YouTube thumbnail style",
            "action shot, dynamic composition, exciting",
            "close-up, emotional, human element",
            "mysterious, intriguing, dark atmosphere",
            "funny, humorous, cartoonish, playful",
            "educational, informative, clean presentation",
            "gaming, futuristic, cyberpunk aesthetic"
        ]
        
        # Select random styles for diversity
        selected_styles = random.sample(styles, min(count, len(styles)))
        
        for style in selected_styles:
            prompt = f"{context}. Style: {style}. High quality, detailed, 4K."
            prompts.append(prompt)
        
        return prompts
    
    def _extract_key_phrases(self, transcription: str, max_phrases: int = 3) -> str:
        """Extract key phrases from transcription."""
        # Simple extraction - in production, use NLP
        sentences = transcription.split('.')
        
        # Take first few sentences
        key_sentences = sentences[:3]
        
        # Clean up
        phrases = []
        for sentence in key_sentences:
            sentence = sentence.strip()
            if sentence and len(sentence.split()) > 3:
                phrases.append(sentence)
        
        # Join phrases
        if phrases:
            return '. '.join(phrases)
        else:
            # Fallback: use first 50 words
            words = transcription.split()[:50]
            return ' '.join(words)
    
    def _save_thumbnail(self, image_data: bytes, filename: str) -> str:
        """Save thumbnail image to temporary file."""
        import base64
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="video_ai_thumbnails_")
        filepath = os.path.join(temp_dir, f"{filename}.png")
        
        # Decode if base64
        if isinstance(image_data, str) and image_data.startswith('data:image'):
            # Extract base64 data
            import re
            match = re.match(r'data:image/(.+?);base64,(.+)', image_data)
            if match:
                image_data = base64.b64decode(match.group(2))
        
        # Save image
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        return filepath
    
    def _calculate_cost(self, tier: Tier, ai_thumbnail_count: int) -> float:
        """Calculate thumbnail generation cost."""
        # Cost per image based on steps
        steps = self._get_model_and_steps(tier)[1]
        
        # Cost per step (approximate)
        cost_per_step = 0.0001  # $0.0001 per step
        
        # Calculate cost per image
        cost_per_image = steps * cost_per_step
        
        # Total cost
        total_cost = ai_thumbnail_count * cost_per_image
        
        # Apply tier adjustments
        tier_multipliers = {
            Tier.FREE: 1.0,
            Tier.STARTER: 1.0,
            Tier.PRO: 1.0,
            Tier.PLUS: 1.0,
            Tier.ENTERPRISE: 1.0
        }
        
        multiplier = tier_multipliers.get(tier, 1.0)
        
        return total_cost * multiplier
    
    def optimize_thumbnail(self, thumbnail_path: str) -> str:
        """Optimize thumbnail for web display."""
        if not os.path.exists(thumbnail_path):
            return thumbnail_path
        
        try:
            # Create optimized version
            optimized_path = thumbnail_path.replace('.png', '_optimized.jpg')
            
            cmd = [
                'ffmpeg', '-i', thumbnail_path,
                '-vf', 'scale=1280:720',
                '-q:v', '2',  # Quality (2-31, lower is better)
                '-y',
                optimized_path
            ]
            
            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(optimized_path):
                # Replace original with optimized
                os.remove(thumbnail_path)
                return optimized_path
            else:
                return thumbnail_path
                
        except Exception as e:
            logger.error(f"Thumbnail optimization failed: {str(e)}")
            return thumbnail_path