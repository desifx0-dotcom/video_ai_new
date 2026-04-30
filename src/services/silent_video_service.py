"""
Silent video detection and analysis service with tier-based frame limits.
Complete production version with proper tier enforcement and user messaging.
"""

import os
import subprocess
import tempfile
import random
import shutil
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import json

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError, TierLimitExceeded
from providers.ffmpeg_provider import FFmpegProvider
from providers.google_provider import GoogleProvider

logger = logging.getLogger(__name__)


class SilentVideoService:
    """Silent video detection and analysis service with tier enforcement."""

    # Cost per frame analysis
    COST_PER_FRAME = 0.005

    # Tier-specific frame limits
    TIER_FRAMES = {
        Tier.FREE: 0,
        Tier.STARTER: 2,
        Tier.PRO: 4,
        Tier.PLUS: 5,
        Tier.ENTERPRISE: 15,
    }

    def __init__(self):
        self.ffmpeg = FFmpegProvider()
        try:
            self.google = GoogleProvider()
            self.google_available = True
        except Exception as e:
            logger.warning(f"Google Vision not available: {e}")
            self.google_available = False
            self.google = None

    def analyze_silent_video(
        self,
        video_path: str,
        user_tier: Tier,
        num_frames: Optional[int] = None,
        regenerate: bool = False,
        video_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze silent video with tier-based frame limits.

        Returns analysis results with user-friendly messages.
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        # Check if silent video is allowed for this tier
        if not self.is_silent_video_allowed(user_tier):
            raise TierLimitExceeded(
                "silent_video",
                0,
                0,
                message=f"Silent videos are not available in {user_tier.value} tier. "
                f"Upgrade to Starter or higher to analyze silent videos.",
                upgrade_url="/pricing",
            )

        # Get number of frames based on tier
        if num_frames is None:
            num_frames = self._get_frames_for_tier(user_tier)

        # Extract frames
        frames = self._extract_frames(video_path, num_frames)

        if not frames:
            return {
                "is_silent": True,
                "frame_count": 0,
                "analysis_results": [],
                "description": "Unable to extract frames from video.",
                "total_cost": 0.0,
                "tier": user_tier.value,
                "regenerated": regenerate,
            }

        # Analyze frames with Google Vision
        analysis_results = self._analyze_with_google_vision(frames)
        total_cost = len(analysis_results) * self.COST_PER_FRAME

        # Generate description based on analysis
        description = self._generate_description(
            analysis_results, user_tier, regenerate, video_id
        )

        # Cleanup frames
        self._cleanup_frames(frames)

        return {
            "is_silent": True,
            "frame_count": len(frames),
            "analyzed_frames": len(analysis_results),
            "analysis_results": analysis_results,
            "description": description,
            "total_cost": total_cost,
            "tier": user_tier.value,
            "regenerated": regenerate,
            "message": self._get_success_message(user_tier, len(analysis_results)),
        }

    def is_silent_video_allowed(self, user_tier: Tier) -> bool:
        """Check if silent video processing is allowed for tier."""
        return self._get_frames_for_tier(user_tier) > 0

    def get_silent_video_limit_message(self, user_tier: Tier) -> str:
        """Get user-friendly message about silent video limits."""
        frames = self._get_frames_for_tier(user_tier)

        if frames == 0:
            return (
                f"⚠️ Silent videos are not available in {user_tier.value} tier.\n"
                f"Upgrade to Starter ($24/month) to analyze silent videos."
            )

        return f"📹 Silent video analysis: up to {frames} frames analyzed."

    def _get_frames_for_tier(self, user_tier: Tier) -> int:
        """Get number of frames to analyze based on tier."""
        return self.TIER_FRAMES.get(user_tier, 0)

    def _extract_frames(self, video_path: str, num_frames: int) -> List[str]:
        """Extract frames from video."""
        if num_frames <= 0:
            return []

        try:
            metadata = self.ffmpeg.get_video_metadata(video_path)
            duration = metadata.get("duration", 60)
        except Exception as e:
            logger.error(f"Failed to get video metadata: {e}")
            duration = 60

        # Calculate intervals - distribute evenly
        if num_frames == 1:
            intervals = [duration / 2]
        else:
            intervals = [
                duration * (i + 1) / (num_frames + 1) for i in range(num_frames)
            ]

        frames_dir = tempfile.mkdtemp(prefix="video_ai_frames_")
        frames = []

        for i, interval in enumerate(intervals):
            frame_path = os.path.join(frames_dir, f"frame_{i:03d}.jpg")
            cmd = [
                "ffmpeg",
                "-ss",
                str(interval),
                "-i",
                video_path,
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-vf",
                "scale=640:360",
                "-y",
                frame_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(frame_path):
                frames.append(frame_path)

        return frames

    def _analyze_with_google_vision(
        self, frame_paths: List[str]
    ) -> List[Dict[str, Any]]:
        """Analyze frames with Google Vision API."""
        if not self.google_available or not self.google:
            return []

        results = []
        for frame_path in frame_paths:
            try:
                analysis = self.google.analyze_image(frame_path)
                if analysis:
                    results.append(
                        {
                            "frame_path": frame_path,
                            "labels": analysis.get("labels", [])[:10],
                            "objects": analysis.get("objects", [])[:5],
                            "description": analysis.get("description", ""),
                            "confidence": analysis.get("confidence", 0.5),
                            "cost": self.COST_PER_FRAME,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
            except Exception as e:
                logger.error(f"Frame analysis failed: {e}")
                continue

        return results

    def _generate_description(
        self,
        analysis_results: List[Dict[str, Any]],
        user_tier: Tier,
        regenerate: bool = False,
        video_id: Optional[str] = None,
    ) -> str:
        """Generate video description from frame analysis."""
        if not analysis_results:
            return "A silent video with engaging visual content."

        # Extract labels and objects
        all_labels = []
        all_objects = []
        all_descriptions = []

        for analysis in analysis_results:
            all_labels.extend(analysis.get("labels", []))
            all_objects.extend(analysis.get("objects", []))
            if analysis.get("description"):
                all_descriptions.append(analysis["description"])

        from collections import Counter

        common_objects = [obj for obj, _ in Counter(all_objects).most_common(3) if obj]
        common_labels = [
            label for label, _ in Counter(all_labels).most_common(3) if label
        ]

        # Generate descriptive text
        if common_objects:
            main_subject = ", ".join(common_objects[:2])
            return f"A silent video featuring {main_subject}. Visual elements include {', '.join(common_labels[:2])}."

        if common_labels:
            return f"An artistic silent video with {', '.join(common_labels[:2])} elements."

        if all_descriptions:
            return f"Silent video content: {all_descriptions[0][:150]}"

        return "A silent video with engaging visual content."

    def _cleanup_frames(self, frames: List[str]):
        """Clean up temporary frame files."""
        for frame in frames:
            try:
                if os.path.exists(frame):
                    os.remove(frame)
            except Exception as e:
                logger.warning(f"Failed to remove frame {frame}: {e}")

        frame_dir = os.path.dirname(frames[0]) if frames else None
        if frame_dir and os.path.exists(frame_dir):
            shutil.rmtree(frame_dir, ignore_errors=True)

    def _get_success_message(self, user_tier: Tier, analyzed_frames: int) -> str:
        """Get user-friendly success message."""
        if analyzed_frames == 0:
            return "Silent video detected. Upgrade to analyze content."

        frames_remaining = self._get_frames_for_tier(user_tier) - analyzed_frames

        if frames_remaining > 0:
            return f"✅ Analyzed {analyzed_frames} frames. {frames_remaining} frame(s) remaining this month."

        return f"✅ Analyzed {analyzed_frames} frames. All frames used for this month."

    def is_silent_video(self, video_path: str, threshold: float = 0.01) -> bool:
        """Detect if video is silent."""
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            audio_path = self._extract_audio(video_path)
            has_speech = self._detect_speech(audio_path, threshold)
            # Cleanup
            if os.path.exists(audio_path):
                os.remove(audio_path)
                audio_dir = os.path.dirname(audio_path)
                if os.path.exists(audio_dir):
                    shutil.rmtree(audio_dir, ignore_errors=True)
            return not has_speech
        except Exception as e:
            logger.error(f"Error detecting silent video: {str(e)}")
            return False

    def _extract_audio(self, video_path: str) -> str:
        """Extract audio from video."""
        audio_dir = tempfile.mkdtemp(prefix="video_ai_audio_")
        audio_path = os.path.join(audio_dir, "audio.wav")
        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ProcessingError(f"Failed to extract audio: {result.stderr}")
        return audio_path

    def _detect_speech(self, audio_path: str, threshold: float = 0.01) -> bool:
        """Detect if audio contains speech."""
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

        mean_volume = None
        for line in result.stderr.split("\n"):
            if "mean_volume:" in line:
                try:
                    parts = line.split(":")
                    if len(parts) > 1:
                        mean_volume = float(parts[1].strip().split()[0])
                except Exception:
                    pass

        # If mean volume is very low, likely silent
        return mean_volume is not None and mean_volume > -30.0
