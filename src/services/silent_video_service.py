"""
Silent video detection and analysis service.
"""

import os
import subprocess
import tempfile
from typing import Dict, Any, List, Optional
import logging
from config import GOOGLE_API_KEY
from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError
from providers.ffmpeg_provider import FFmpegProvider
from providers.google_provider import GoogleProvider

logger = logging.getLogger(__name__)


class SilentVideoService:
    """Silent video detection and analysis service."""

    def __init__(self):
        self.ffmpeg = FFmpegProvider()

        # Pass the API key from config to GoogleProvider
        try:
            self.google = GoogleProvider(api_key=GOOGLE_API_KEY)
            self.google_available = True
            logger.info("GoogleProvider initialized with API key")
        except Exception as e:
            logger.warning(f"Google Vision not available: {e}. Using mock mode.")
            self.google_available = False
            self.google = None

    def is_silent_video(self, video_path: str, threshold: float = 0.01) -> bool:
        """
        Detect if video is silent (no speech).

        Args:
            video_path: Path to video file
            threshold: Audio level threshold for silence detection

        Returns:
            True if video is silent
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            # Extract audio
            audio_path = self._extract_audio(video_path)

            # Analyze audio for speech
            has_speech = self._detect_speech(audio_path, threshold)

            # Cleanup temporary audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)

            return not has_speech

        except Exception as e:
            logger.error(f"Error detecting silent video: {str(e)}")
            # If we can't determine, assume it has speech (safer assumption)
            return False

    def analyze_silent_video(
        self, video_path: str, user_tier: Tier, num_frames: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Analyze silent video using AI vision.

        Args:
            video_path: Path to video file
            user_tier: User tier for analysis limits
            num_frames: Number of frames to analyze (None for tier default)

        Returns:
            Analysis results
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        # Get number of frames based on tier
        if num_frames is None:
            num_frames = self._get_frames_for_tier(user_tier)

        # Extract frames
        frames = self._extract_frames(video_path, num_frames)

        # Analyze frames with AI
        analysis_results = []
        total_cost = 0.0

        for frame_path in frames:
            try:
                # Analyze frame with Google Vision
                analysis = self.google.analyze_image(frame_path)

                if analysis:
                    analysis_results.append(analysis)
                    total_cost += analysis.get("cost", 0.0)

                # Cleanup frame file
                os.remove(frame_path)

            except Exception as e:
                logger.error(f"Error analyzing frame: {str(e)}")

        # Cleanup frame directory
        frame_dir = os.path.dirname(frames[0]) if frames else None
        if frame_dir and os.path.exists(frame_dir):
            import shutil

            shutil.rmtree(frame_dir, ignore_errors=True)

        # Generate description from analysis
        description = self._generate_description(analysis_results, user_tier)

        return {
            "is_silent": True,
            "frame_count": len(frames),
            "analysis_results": analysis_results,
            "description": description,
            "total_cost": total_cost,
            "tier": user_tier.value,
        }

    def _extract_audio(self, video_path: str) -> str:
        """Extract audio from video for analysis."""
        # Create temporary audio file
        audio_dir = tempfile.mkdtemp(prefix="video_ai_audio_")
        audio_path = os.path.join(audio_dir, "audio.wav")

        # Extract audio using FFmpeg
        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vn",  # No video
            "-acodec",
            "pcm_s16le",  # WAV format
            "-ar",
            "16000",  # 16kHz sample rate
            "-ac",
            "1",  # Mono
            "-y",  # Overwrite output
            audio_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise ProcessingError(f"Failed to extract audio: {result.stderr}")

        return audio_path

    def _detect_speech(self, audio_path: str, threshold: float = 0.01) -> bool:
        """
        Detect if audio contains speech.

        Args:
            audio_path: Path to audio file
            threshold: Threshold for speech detection

        Returns:
            True if speech is detected
        """
        # Simple energy-based speech detection
        # In production, you would use a proper VAD (Voice Activity Detection) library

        # Get audio statistics using FFmpeg
        cmd = [
            "ffmpeg",
            "-i",
            audio_path,
            "-af",
            "volumedetect",
            "-f",
            "null",
            "/dev/null",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.warning(f"Failed to analyze audio: {result.stderr}")
            return True  # Assume speech if we can't analyze

        # Parse output for mean_volume
        output = result.stderr
        mean_volume = None

        for line in output.split("\n"):
            if "mean_volume:" in line:
                try:
                    # Extract volume value (e.g., "mean_volume: -20.5 dB")
                    parts = line.split(":")
                    if len(parts) > 1:
                        volume_str = parts[1].strip().split()[0]
                        mean_volume = float(volume_str)
                except (ValueError, IndexError):
                    pass

        # If we can't get volume, assume speech
        if mean_volume is None:
            return True

        # Convert dB to linear scale for threshold comparison
        # -30 dB or louder suggests speech presence
        return mean_volume > -30.0

    def _extract_frames(self, video_path: str, num_frames: int) -> List[str]:
        """Extract frames from video at intervals."""
        # Get video duration
        metadata = self.ffmpeg.get_video_metadata(video_path)
        duration = metadata.get("duration", 60)

        # Calculate frame intervals
        if num_frames <= 1:
            intervals = [duration / 2]  # Middle of video
        else:
            intervals = [
                i * duration / (num_frames + 1) for i in range(1, num_frames + 1)
            ]

        # Create temporary directory for frames
        frames_dir = tempfile.mkdtemp(prefix="video_ai_frames_")
        frames = []

        # Extract frames at intervals
        for i, interval in enumerate(intervals):
            frame_path = os.path.join(frames_dir, f"frame_{i:03d}.jpg")

            cmd = [
                "ffmpeg",
                "-ss",
                str(interval),  # Seek to position
                "-i",
                video_path,
                "-vframes",
                "1",  # Extract 1 frame
                "-q:v",
                "2",  # Quality (2-31, lower is better)
                "-y",  # Overwrite output
                frame_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and os.path.exists(frame_path):
                frames.append(frame_path)
            else:
                logger.warning(
                    f"Failed to extract frame at {interval}s: {result.stderr}"
                )

        return frames

    def _get_frames_for_tier(self, user_tier: Tier) -> int:
        """Get number of frames to analyze based on tier."""
        tier_frames = {
            Tier.FREE: 0,  # No analysis for free tier
            Tier.STARTER: 2,
            Tier.PRO: 3,
            Tier.PLUS: 5,
            Tier.ENTERPRISE: 10,
        }

        return tier_frames.get(user_tier, 0)

    def _generate_description(
        self, analysis_results: List[Dict[str, Any]], user_tier: Tier
    ) -> str:
        """Generate video description from frame analysis."""
        if not analysis_results:
            return "A silent video with visual content."

        # Extract key information from analyses
        all_labels = []
        all_objects = []

        for analysis in analysis_results:
            labels = analysis.get("labels", [])
            objects = analysis.get("objects", [])

            all_labels.extend(labels)
            all_objects.extend(objects)

        # Count frequency of labels
        from collections import Counter

        label_counter = Counter(all_labels)
        object_counter = Counter(all_objects)

        # Get most common elements
        common_labels = [label for label, _ in label_counter.most_common(5)]
        common_objects = [obj for obj, _ in object_counter.most_common(5)]

        # Generate description
        if common_objects:
            objects_str = ", ".join(common_objects[:3])
            description = f"A video featuring {objects_str}."
        elif common_labels:
            labels_str = ", ".join(common_labels[:3])
            description = f"A {labels_str} video."
        else:
            description = "A silent video with visual content."

        # Add context based on tier
        if user_tier in [Tier.PRO, Tier.PLUS, Tier.ENTERPRISE] and analysis_results:
            # For higher tiers, include more detailed analysis
            colors = []
            for analysis in analysis_results:
                colors.extend(analysis.get("dominant_colors", []))

            if colors:
                color_counter = Counter(colors)
                common_colors = [color for color, _ in color_counter.most_common(3)]
                if common_colors:
                    color_str = ", ".join(common_colors)
                    description += f" Dominant colors include {color_str}."

        return description

    def get_silent_video_savings(self, video_duration: float) -> Dict[str, float]:
        """
        Calculate cost savings for silent video processing.

        Args:
            video_duration: Video duration in seconds

        Returns:
            Cost savings information
        """
        # Cost per minute for speech video (transcription + title generation)
        speech_cost_per_minute = 0.037  # $0.037 per minute

        # Cost per minute for silent video (frame analysis only)
        silent_cost_per_minute = 0.012  # $0.012 per minute

        video_minutes = video_duration / 60

        speech_cost = speech_cost_per_minute * video_minutes
        silent_cost = silent_cost_per_minute * video_minutes

        savings = speech_cost - silent_cost
        savings_percentage = (savings / speech_cost * 100) if speech_cost > 0 else 0

        return {
            "speech_cost": speech_cost,
            "silent_cost": silent_cost,
            "savings": savings,
            "savings_percentage": savings_percentage,
            "duration_minutes": video_minutes,
            "cost_per_minute_speech": speech_cost_per_minute,
            "cost_per_minute_silent": silent_cost_per_minute,
        }

    def should_analyze_silent_video(self, user_tier: Tier) -> bool:
        """Check if silent video should be analyzed based on tier."""
        # Only analyze silent videos for Starter tier and above
        return user_tier in [Tier.STARTER, Tier.PRO, Tier.PLUS, Tier.ENTERPRISE]
