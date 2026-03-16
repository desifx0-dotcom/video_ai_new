"""
Video quality processing service.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

from core.domain.value_objects.tier import Tier
from core.exceptions import ProcessingError
from providers.ffmpeg_provider import FFmpegProvider

logger = logging.getLogger(__name__)


class QualityService:
    """Video quality processing service."""

    def __init__(self):
        self.ffmpeg = FFmpegProvider()

    def process_video(
        self,
        input_path: str,
        target_quality: str,
        user_tier: Tier,
        output_format: str = "mp4",
    ) -> Dict[str, Any]:
        """
        Process video to target quality based on user tier.

        Args:
            input_path: Input video path
            target_quality: Target quality (720p, 1080p, 4k, 4k+hdr)
            user_tier: User tier for quality settings
            output_format: Output format

        Returns:
            Processing result
        """
        # Validate input file
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        # Get quality settings for tier
        quality_settings = self._get_quality_settings(target_quality, user_tier)

        # Create output path
        output_dir = tempfile.mkdtemp(prefix="video_ai_quality_")
        output_filename = f"processed_{Path(input_path).stem}.{output_format}"
        output_path = os.path.join(output_dir, output_filename)

        try:
            # Get video metadata
            metadata = self.ffmpeg.get_video_metadata(input_path)

            # Scale video if needed
            if metadata["width"] > quality_settings["max_width"]:
                scale_filter = self._create_scale_filter(metadata, quality_settings)
            else:
                scale_filter = None

            # Build FFmpeg command
            cmd = ["ffmpeg", "-i", input_path, "-y"]

            # Add video codec and quality settings
            cmd.extend(
                [
                    "-c:v",
                    quality_settings["video_codec"],
                    "-preset",
                    quality_settings["preset"],
                    "-crf",
                    str(quality_settings["crf"]),
                    "-b:v",
                    str(quality_settings["bitrate"]),
                    "-maxrate",
                    str(quality_settings["maxrate"]),
                    "-bufsize",
                    str(quality_settings["bufsize"]),
                    "-pix_fmt",
                    quality_settings["pix_fmt"],
                ]
            )

            # Add scale filter if needed
            if scale_filter:
                cmd.extend(["-vf", scale_filter])

            # Add audio settings
            cmd.extend(
                [
                    "-c:a",
                    quality_settings["audio_codec"],
                    "-b:a",
                    str(quality_settings["audio_bitrate"]),
                    "-ar",
                    str(quality_settings["audio_sample_rate"]),
                ]
            )

            # Add HDR settings if applicable
            if target_quality == "4k+hdr" and quality_settings.get("hdr_params"):
                for param, value in quality_settings["hdr_params"].items():
                    cmd.extend([param, value])

            # Add output
            cmd.append(output_path)

            # Execute FFmpeg command
            logger.info(f"Processing video with command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=quality_settings.get("timeout", 1800),  # 30 minutes default
            )

            if result.returncode != 0:
                raise ProcessingError(
                    f"FFmpeg failed: {result.stderr}", step="quality_processing"
                )

            # Get output file size
            output_size = os.path.getsize(output_path)

            return {
                "success": True,
                "path": output_path,
                "size": output_size,
                "quality": target_quality,
                "tier": user_tier.value,
                "command": " ".join(cmd),
                "output_dir": output_dir,
            }

        except subprocess.TimeoutExpired:
            raise ProcessingError("Video processing timeout", step="quality_processing")
        except Exception as e:
            # Cleanup output directory on error
            if os.path.exists(output_dir):
                import shutil

                shutil.rmtree(output_dir, ignore_errors=True)
            raise ProcessingError(
                f"Quality processing failed: {str(e)}", step="quality_processing"
            )

    def _get_quality_settings(
        self, target_quality: str, user_tier: Tier
    ) -> Dict[str, Any]:
        """Get quality settings for target quality and user tier."""
        # Base settings for each quality level
        base_settings = {
            "720p": {
                "width": 1280,
                "height": 720,
                "max_width": 1280,
                "max_height": 720,
                "bitrate": 2000000,  # 2 Mbps
                "maxrate": 2500000,  # 2.5 Mbps
                "bufsize": 5000000,  # 5 Mbps
                "crf": 23,
                "preset": "veryfast",
                "video_codec": "libx264",
                "audio_codec": "aac",
                "audio_bitrate": 128000,
                "audio_sample_rate": 44100,
                "pix_fmt": "yuv420p",
            },
            "1080p": {
                "width": 1920,
                "height": 1080,
                "max_width": 1920,
                "max_height": 1080,
                "bitrate": 5000000,  # 5 Mbps
                "maxrate": 6250000,  # 6.25 Mbps
                "bufsize": 12500000,  # 12.5 Mbps
                "crf": 21,
                "preset": "medium",
                "video_codec": "libx264",
                "audio_codec": "aac",
                "audio_bitrate": 192000,
                "audio_sample_rate": 44100,
                "pix_fmt": "yuv420p",
            },
            "4k": {
                "width": 3840,
                "height": 2160,
                "max_width": 3840,
                "max_height": 2160,
                "bitrate": 15000000,  # 15 Mbps
                "maxrate": 18750000,  # 18.75 Mbps
                "bufsize": 37500000,  # 37.5 Mbps
                "crf": 19,
                "preset": "slow",
                "video_codec": "libx265",
                "audio_codec": "aac",
                "audio_bitrate": 256000,
                "audio_sample_rate": 48000,
                "pix_fmt": "yuv420p10le",  # 10-bit for better quality
            },
            "4k+hdr": {
                "width": 3840,
                "height": 2160,
                "max_width": 3840,
                "max_height": 2160,
                "bitrate": 25000000,  # 25 Mbps
                "maxrate": 31250000,  # 31.25 Mbps
                "bufsize": 62500000,  # 62.5 Mbps
                "crf": 17,
                "preset": "veryslow",
                "video_codec": "libx265",
                "audio_codec": "aac",
                "audio_bitrate": 320000,
                "audio_sample_rate": 48000,
                "pix_fmt": "yuv420p10le",
                "hdr_params": {
                    "-color_primaries": "bt2020",
                    "-color_trc": "smpte2084",
                    "-colorspace": "bt2020nc",
                    "-x265-params": "hdr-opt=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400",
                },
            },
        }

        if target_quality not in base_settings:
            raise ProcessingError(f"Unsupported quality: {target_quality}")

        settings = base_settings[target_quality].copy()

        # Adjust settings based on tier
        tier_adjustments = {
            Tier.FREE: {
                "preset": "ultrafast",
                "crf": 26,  # Higher CRF = lower quality, smaller file
                "bitrate_multiplier": 0.8,
                "audio_bitrate": 96000,
            },
            Tier.STARTER: {
                "preset": "fast",
                "crf": 23,
                "bitrate_multiplier": 1.0,
                "audio_bitrate": 128000,
            },
            Tier.PRO: {
                "preset": "medium",
                "crf": 20,
                "bitrate_multiplier": 1.2,
                "audio_bitrate": 192000,
            },
            Tier.PLUS: {
                "preset": "slow",
                "crf": 18,
                "bitrate_multiplier": 1.5,
                "audio_bitrate": 256000,
            },
            Tier.ENTERPRISE: {
                "preset": "veryslow",
                "crf": 16,
                "bitrate_multiplier": 2.0,
                "audio_bitrate": 320000,
            },
        }

        adjustment = tier_adjustments.get(user_tier, tier_adjustments[Tier.FREE])

        # Apply tier adjustments
        settings["preset"] = adjustment["preset"]
        settings["crf"] = adjustment["crf"]
        settings["bitrate"] = int(
            settings["bitrate"] * adjustment["bitrate_multiplier"]
        )
        settings["maxrate"] = int(
            settings["maxrate"] * adjustment["bitrate_multiplier"]
        )
        settings["bufsize"] = int(
            settings["bufsize"] * adjustment["bitrate_multiplier"]
        )
        settings["audio_bitrate"] = adjustment["audio_bitrate"]

        # Higher tiers get better codecs
        if (
            user_tier in [Tier.PRO, Tier.PLUS, Tier.ENTERPRISE]
            and target_quality == "1080p"
        ):
            settings["video_codec"] = "libx265"
            settings["pix_fmt"] = "yuv420p10le"

        # Add timeout based on preset
        preset_timeouts = {
            "ultrafast": 600,  # 10 minutes
            "superfast": 900,  # 15 minutes
            "veryfast": 1200,  # 20 minutes
            "faster": 1500,  # 25 minutes
            "fast": 1800,  # 30 minutes
            "medium": 2400,  # 40 minutes
            "slow": 3000,  # 50 minutes
            "slower": 3600,  # 60 minutes
            "veryslow": 4800,  # 80 minutes
        }

        settings["timeout"] = preset_timeouts.get(settings["preset"], 1800)

        return settings

    def _create_scale_filter(
        self, metadata: Dict[str, Any], quality_settings: Dict[str, Any]
    ) -> str:
        """Create FFmpeg scale filter for resizing video."""
        input_width = metadata["width"]
        input_height = metadata["height"]

        max_width = quality_settings["max_width"]
        max_height = quality_settings["max_height"]

        # Calculate aspect ratio
        input_ratio = input_width / input_height
        target_ratio = max_width / max_height

        if input_ratio > target_ratio:
            # Input is wider than target
            scale_width = max_width
            scale_height = int(max_width / input_ratio)
        else:
            # Input is taller than target
            scale_height = max_height
            scale_width = int(max_height * input_ratio)

        # Ensure dimensions are even (required by some codecs)
        scale_width = scale_width - (scale_width % 2)
        scale_height = scale_height - (scale_height % 2)

        return f"scale={scale_width}:{scale_height}"

    def get_default_quality(self, user_tier: Tier) -> str:
        """Get default quality for user tier."""
        tier_qualities = {
            Tier.FREE: "720p",
            Tier.STARTER: "1080p",
            Tier.PRO: "4k",
            Tier.PLUS: "4k+hdr",
            Tier.ENTERPRISE: "4k+hdr",
        }

        return tier_qualities.get(user_tier, "720p")

    def get_available_qualities(self, user_tier: Tier) -> List[str]:
        """Get available qualities for user tier."""
        all_qualities = ["720p", "1080p", "4k", "4k+hdr"]

        tier_limits = {
            Tier.FREE: ["720p"],
            Tier.STARTER: ["720p", "1080p"],
            Tier.PRO: ["720p", "1080p", "4k"],
            Tier.PLUS: ["720p", "1080p", "4k", "4k+hdr"],
            Tier.ENTERPRISE: ["720p", "1080p", "4k", "4k+hdr"],
        }

        return tier_limits.get(user_tier, ["720p"])

    def estimate_output_size(
        self, input_path: str, target_quality: str, user_tier: Tier
    ) -> Dict[str, Any]:
        """
        Estimate output file size for quality processing.

        Args:
            input_path: Input video path
            target_quality: Target quality
            user_tier: User tier

        Returns:
            Size estimation
        """
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        # Get input file size and duration
        input_size = os.path.getsize(input_path)
        metadata = self.ffmpeg.get_video_metadata(input_path)
        duration = metadata.get("duration", 60)  # Default 60 seconds

        # Get quality settings
        quality_settings = self._get_quality_settings(target_quality, user_tier)

        # Estimate bitrate in bits per second
        video_bitrate = quality_settings["bitrate"]
        audio_bitrate = quality_settings["audio_bitrate"]
        total_bitrate = video_bitrate + audio_bitrate

        # Calculate estimated size
        estimated_size_bits = total_bitrate * duration
        estimated_size_bytes = estimated_size_bits / 8

        # Add overhead (container, metadata, etc.)
        estimated_size_bytes *= 1.1

        # Calculate compression ratio
        if input_size > 0:
            compression_ratio = estimated_size_bytes / input_size
        else:
            compression_ratio = 1.0

        return {
            "input_size_mb": input_size / (1024 * 1024),
            "estimated_size_mb": estimated_size_bytes / (1024 * 1024),
            "compression_ratio": compression_ratio,
            "video_bitrate_mbps": video_bitrate / 1000000,
            "audio_bitrate_kbps": audio_bitrate / 1000,
            "duration_seconds": duration,
            "quality": target_quality,
            "tier": user_tier.value,
        }
