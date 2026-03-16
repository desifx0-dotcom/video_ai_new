"""
Title generation service using AI models.
"""
from typing import Dict, Any, List, Optional
import logging

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError, ExternalServiceError
from providers.google_provider import GoogleProvider
from providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

class TitleService:
    """Title generation service."""
    
    def __init__(self):
        self.google = GoogleProvider()
        self.openai = OpenAIProvider()
    
    def generate_title(
        self,
        transcription: Optional[str],
        video_type: str,
        tier: Tier,
        video_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate title, description, and tags for video.
        
        Args:
            transcription: Video transcription (if any)
            video_type: Type of video (speech, silent, music)
            tier: User tier for model selection
            video_description: Optional description from silent video analysis
        
        Returns:
            Generated content
        """
        # Prepare input text
        input_text = self._prepare_input_text(transcription, video_description, video_type)
        
        try:
            # Generate content based on tier
            if tier in [Tier.PLUS, Tier.ENTERPRISE]:
                # Use GPT-4 for higher tiers
                content = self._generate_with_gpt4(input_text, video_type, tier)
            elif tier == Tier.PRO:
                # Use Gemini Pro for Pro tier
                content = self._generate_with_gemini_pro(input_text, video_type, tier)
            else:
                # Use Gemini Flash for Free and Starter tiers
                content = self._generate_with_gemini_flash(input_text, video_type, tier)
            
            # Calculate cost
            cost = self._calculate_cost(tier, content.get('model', ''))
            
            return {
                'title': content['title'],
                'description': content['description'],
                'tags': content['tags'],
                'cost': cost,
                'model': content.get('model', 'gemini-flash'),
                'tier': tier.value,
                'video_type': video_type
            }
            
        except Exception as e:
            if "Google" in str(e) or "Gemini" in str(e):
                raise ExternalServiceError("Google", str(e))
            elif "OpenAI" in str(e) or "GPT" in str(e):
                raise ExternalServiceError("OpenAI", str(e))
            else:
                raise ProcessingError(f"Title generation failed: {str(e)}", step="title_generation")
    
    def _prepare_input_text(
        self,
        transcription: Optional[str],
        video_description: Optional[str],
        video_type: str
    ) -> str:
        """Prepare input text for AI model."""
        if transcription:
            # Use transcription for speech videos
            # Limit length to avoid token limits
            if len(transcription) > 4000:
                transcription = transcription[:4000] + "..."
            return transcription
        
        elif video_description:
            # Use description for silent videos
            return video_description
        
        else:
            # Generic input for unknown video types
            return f"This is a {video_type} video without transcription."
    
    def _generate_with_gemini_flash(
        self,
        input_text: str,
        video_type: str,
        tier: Tier
    ) -> Dict[str, Any]:
        """Generate content using Gemini Flash."""
        prompt = self._create_prompt(input_text, video_type, tier)
        
        response = self.google.generate_text(
            prompt=prompt,
            model='gemini-1.5-flash',
            temperature=0.7,
            max_tokens=500
        )
        
        # Parse response
        parsed = self._parse_ai_response(response)
        
        return {
            'title': parsed.get('title', f"{video_type.capitalize()} Video"),
            'description': parsed.get('description', ''),
            'tags': parsed.get('tags', []),
            'model': 'gemini-flash'
        }
    
    def _generate_with_gemini_pro(
        self,
        input_text: str,
        video_type: str,
        tier: Tier
    ) -> Dict[str, Any]:
        """Generate content using Gemini Pro."""
        prompt = self._create_prompt(input_text, video_type, tier)
        
        response = self.google.generate_text(
            prompt=prompt,
            model='gemini-1.5-pro',
            temperature=0.7,
            max_tokens=800
        )
        
        # Parse response
        parsed = self._parse_ai_response(response)
        
        return {
            'title': parsed.get('title', f"{video_type.capitalize()} Video"),
            'description': parsed.get('description', ''),
            'tags': parsed.get('tags', []),
            'model': 'gemini-pro'
        }
    
    def _generate_with_gpt4(
        self,
        input_text: str,
        video_type: str,
        tier: Tier
    ) -> Dict[str, Any]:
        """Generate content using GPT-4."""
        prompt = self._create_prompt(input_text, video_type, tier)
        
        response = self.openai.generate_text(
            prompt=prompt,
            model='gpt-4-turbo',
            temperature=0.7,
            max_tokens=1000
        )
        
        # Parse response
        parsed = self._parse_ai_response(response)
        
        return {
            'title': parsed.get('title', f"{video_type.capitalize()} Video"),
            'description': parsed.get('description', ''),
            'tags': parsed.get('tags', []),
            'model': 'gpt-4-turbo'
        }
    
    def _create_prompt(self, input_text: str, video_type: str, tier: Tier) -> str:
        """Create prompt for AI model."""
        if video_type == 'speech':
            content_type = "transcribed speech"
        elif video_type == 'silent':
            content_type = "visual content description"
        else:
            content_type = "video content"
        
        prompt = f"""
        Based on the following {content_type}, generate an engaging title, description, and relevant tags for a YouTube/TikTok style video.
        
        {content_type.upper()}:
        {input_text}
        
        Please provide:
        1. TITLE: A catchy, SEO-friendly title (5-10 words)
        2. DESCRIPTION: A compelling description (2-3 sentences)
        3. TAGS: 5-10 relevant hashtags/tags
        
        Format your response as:
        TITLE: [title here]
        DESCRIPTION: [description here]
        TAGS: [tag1, tag2, tag3, ...]
        
        Make the content engaging and suitable for social media.
        """
        
        return prompt
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Parse AI response into structured data."""
        title = ""
        description = ""
        tags = []
        
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('TITLE:'):
                current_section = 'title'
                title = line[6:].strip()
            elif line.startswith('DESCRIPTION:'):
                current_section = 'description'
                description = line[12:].strip()
            elif line.startswith('TAGS:'):
                current_section = 'tags'
                tags_str = line[5:].strip()
                tags = [tag.strip() for tag in tags_str.split(',')]
            elif current_section == 'description' and line:
                # Append continuation lines to description
                description += ' ' + line
            elif current_section == 'tags' and line and not line.startswith(('TITLE:', 'DESCRIPTION:')):
                # Handle multi-line tags
                more_tags = [tag.strip() for tag in line.split(',')]
                tags.extend(more_tags)
        
        # Clean up tags
        tags = [tag.strip('#').lower() for tag in tags if tag.strip()]
        
        # If parsing failed, use defaults
        if not title:
            title = "Engaging Video Content"
        
        if not description:
            description = "Watch this amazing video with engaging content."
        
        if not tags:
            tags = ['video', 'content', 'socialmedia', 'engagement', 'watch']
        
        return {
            'title': title,
            'description': description,
            'tags': tags[:10]  # Limit to 10 tags
        }
    
    def _calculate_cost(self, tier: Tier, model: str) -> float:
        """Calculate title generation cost."""
        # Cost per 1K tokens
        costs_per_1k = {
            'gemini-flash': 0.00006,  # $0.06 per 1K tokens
            'gemini-pro': 0.00025,    # $0.25 per 1K tokens
            'gpt-3.5-turbo': 0.00015, # $0.15 per 1K tokens
            'gpt-4-turbo': 0.0015     # $1.50 per 1K tokens
        }
        
        # Estimate tokens: prompt + completion
        # Rough estimate: 500 tokens total
        estimated_tokens = 500
        
        cost_per_token = costs_per_1k.get(model, 0.00006) / 1000
        cost = estimated_tokens * cost_per_token
        
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
    
    def generate_alternative_titles(
        self,
        title: str,
        count: int = 3,
        tier: Tier = Tier.FREE
    ) -> List[str]:
        """Generate alternative titles."""
        prompt = f"""
        Generate {count} alternative titles for this video title:
        "{title}"
        
        Make them catchy, SEO-friendly, and suitable for social media.
        Return each title on a new line.
        """
        
        try:
            if tier in [Tier.PLUS, Tier.ENTERPRISE]:
                response = self.openai.generate_text(
                    prompt=prompt,
                    model='gpt-4-turbo',
                    temperature=0.8,
                    max_tokens=200
                )
            else:
                response = self.google.generate_text(
                    prompt=prompt,
                    model='gemini-1.5-flash',
                    temperature=0.8,
                    max_tokens=200
                )
            
            # Parse response
            alternatives = [line.strip() for line in response.split('\n') if line.strip()]
            return alternatives[:count]
            
        except Exception as e:
            logger.error(f"Failed to generate alternative titles: {str(e)}")
            return []