"""
FFmpeg provider for video/audio processing.
"""

import os
import subprocess
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)


class FFmpegProvider:
    """FFmpeg provider for video/audio processing."""

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        # Use provided paths first
        if ffmpeg_path and ffprobe_path:
            self.ffmpeg_path = ffmpeg_path
            self.ffprobe_path = ffprobe_path
        else:
            # Check environment variables
            env_ffmpeg = os.getenv("FFMPEG_PATH")
            env_ffprobe = os.getenv("FFPROBE_PATH")
            
            if env_ffmpeg and env_ffprobe:
                self.ffmpeg_path = env_ffmpeg
                self.ffprobe_path = env_ffprobe
            else:
                # Auto-detect from common paths
                detected_ffmpeg, detected_ffprobe = self._find_ffmpeg()
                if detected_ffmpeg and detected_ffprobe:
                    self.ffmpeg_path = detected_ffmpeg
                    self.ffprobe_path = detected_ffprobe
                else:
                    # Fallback to 'ffmpeg' (relies on PATH)
                    self.ffmpeg_path = "ffmpeg"
                    self.ffprobe_path = "ffprobe"
        
        self._ffmpeg_available = None
        
    def _ensure_ffmpeg(self):
        """Lazy test FFmpeg - only when first used."""
        if self._ffmpeg_available is not None:
            return
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"], capture_output=True, timeout=5
            )
            self._ffmpeg_available = True
        except Exception:
            self._ffmpeg_available = False
            raise ProcessingError("FFmpeg not found")

    @classmethod
    def _find_ffmpeg(cls) -> tuple:
        """Auto-detect FFmpeg from common installation paths."""
        import shutil
        import platform
        
        # First try system PATH
        ffmpeg = shutil.which('ffmpeg')
        ffprobe = shutil.which('ffprobe')
        if ffmpeg and ffprobe:
            return ffmpeg, ffprobe
        
        # Platform-specific common paths
        system = platform.system().lower()
        
        if system == 'windows':
            common_paths = [
            # Winget installation path (your newer FFmpeg)
            r'C:\Users\Acer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe',
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\FFmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
            ]
        elif system == 'darwin':  # macOS
            common_paths = [
                '/usr/local/bin/ffmpeg',
                '/opt/homebrew/bin/ffmpeg',
                '/usr/bin/ffmpeg',
            ]
        else:  # Linux
            common_paths = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/ffmpeg/bin/ffmpeg',
            ]
        
        for path in common_paths:
            if os.path.exists(path):
                ffprobe_path = path.replace('ffmpeg', 'ffprobe')
                if os.path.exists(ffprobe_path):
                    return path, ffprobe_path
        
        return None, None

    def _test_ffmpeg(self):
        """Test FFmpeg installation."""
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            raise ProcessingError(
                "FFmpeg not found or not working. Please install FFmpeg."
            )

    def get_video_duration(self, video_path: str) -> float:
        """
        Get video duration in seconds.

        Args:
            video_path: Path to video file

        Returns:
            Duration in seconds
        """
        self._ensure_ffmpeg()

        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            cmd = [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                video_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                raise ProcessingError(f"Failed to get video duration: {result.stderr}")

            data = json.loads(result.stdout)
            duration = float(data["format"]["duration"])

            return duration

        except (subprocess.SubprocessError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to get video duration: {str(e)}")
            raise ProcessingError(f"Failed to get video duration: {str(e)}")

    def get_video_metadata(self, video_path: str) -> Dict[str, Any]:
        """Get comprehensive video metadata."""

        self._ensure_ffmpeg()

        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            cmd = [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,bit_rate,sample_rate,channels,r_frame_rate",
                "-show_entries",
                "format=duration,size,bit_rate",
                "-of",
                "json",
                video_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                raise ProcessingError(f"Failed to get video metadata: {result.stderr}")

            data = json.loads(result.stdout)

            # Parse streams
            video_stream = None
            audio_stream = None

            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                elif stream.get("codec_type") == "audio":
                    audio_stream = stream

            # Calculate FPS from r_frame_rate
            fps = 0
            if video_stream and "r_frame_rate" in video_stream:
                try:
                    num, den = video_stream["r_frame_rate"].split("/")
                    fps = float(num) / float(den) if float(den) != 0 else 0
                except:
                    fps = 0

            # Get audio bitrate
            audio_bitrate = 0
            if audio_stream and "bit_rate" in audio_stream:
                try:
                    audio_bitrate = int(audio_stream["bit_rate"])
                except:
                    audio_bitrate = 0

            # If audio bitrate not in stream, try format
            if audio_bitrate == 0 and data.get("format", {}).get("bit_rate"):
                try:
                    audio_bitrate = int(data["format"]["bit_rate"])
                except:
                    pass

            metadata = {
                "duration": float(data.get("format", {}).get("duration", 0)),
                "size": int(data.get("format", {}).get("size", 0)),
                "format": data.get("format", {}).get("format_name", ""),
                "video": {
                    "codec": (
                        video_stream.get("codec_name", "") if video_stream else None
                    ),
                    "width": int(video_stream.get("width", 0)) if video_stream else 0,
                    "height": int(video_stream.get("height", 0)) if video_stream else 0,
                    "fps": round(fps, 2) if fps > 0 else 0,
                    "bitrate": (
                        int(video_stream.get("bit_rate", 0))
                        if video_stream and video_stream.get("bit_rate")
                        else 0
                    ),
                },
                "audio": {
                    "codec": (
                        audio_stream.get("codec_name", "") if audio_stream else None
                    ),
                    "bitrate": audio_bitrate,
                    "sample_rate": (
                        int(audio_stream.get("sample_rate", 0))
                        if audio_stream and audio_stream.get("sample_rate")
                        else 0
                    ),
                    "channels": (
                        int(audio_stream.get("channels", 0)) if audio_stream else 0
                    ),
                },
            }

            return metadata

        except Exception as e:
            logger.error(f"Failed to get video metadata: {str(e)}")
            raise ProcessingError(f"Failed to get video metadata: {str(e)}")

    def extract_audio(self, video_path: str, output_path: str) -> bool:
        """
        Extract audio from video.

        Args:
            video_path: Path to video file
            output_path: Path to save extracted audio

        Returns:
            True if successful
        """
        self._ensure_ffmpeg()

        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            cmd = [
                self.ffmpeg_path,
                "-i",
                video_path,
                "-vn",  # No video
                "-acodec",
                "pcm_s16le",  # WAV format
                "-ar",
                "44100",  # Sample rate
                "-ac",
                "2",  # Stereo
                "-y",  # Overwrite output
                output_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                logger.error(f"Audio extraction failed: {result.stderr}")
                return False

            return os.path.exists(output_path)

        except subprocess.SubprocessError as e:
            logger.error(f"Audio extraction failed: {str(e)}")
            return False

    def get_audio_duration(self, audio_path: str) -> float:
        """
        Get audio duration in seconds.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        return self.get_video_duration(audio_path)  # FFprobe works for audio too

    # Add this method to providers/ffmpeg_provider.py
    def extract_frame_at_time(
        self,
        video_path: str,
        timestamp: float,
        output_path: str,
        width: int = 640,
        height: int = 360,
    ) -> bool:
        """
        Extract frame at specific timestamp with resize.

        Args:
            video_path: Path to video file
            timestamp: Time in seconds
            output_path: Path to save the frame
            width: Output width
            height: Output height

        Returns:
            True if successful
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            cmd = [
                self.ffmpeg_path,
                "-ss",
                str(timestamp),
                "-i",
                video_path,
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-y",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and os.path.exists(output_path):
                return True

            logger.error(f"Frame extraction failed: {result.stderr}")
            return False

        except subprocess.SubprocessError as e:
            logger.error(f"Frame extraction failed: {str(e)}")
            return False

    def extract_multiple_frames(
        self, video_path: str, timestamps: List[float], output_dir: str
    ) -> List[str]:
        """
        Extract multiple frames from video.

        Args:
            video_path: Path to video file
            timestamps: List of timestamps in seconds
            output_dir: Directory to save frames

        Returns:
            List of paths to extracted frames
        """
        frames = []

        for i, timestamp in enumerate(timestamps):
            frame_path = self.extract_frame(
                video_path=video_path,
                timestamp=timestamp,
                output_dir=output_dir,
                filename=f"frame_{i:03d}",
            )

            if frame_path:
                frames.append(frame_path)

        return frames

    def detect_silent_segments(
        self,
        video_path: str,
        silence_threshold: float = -30.0,
        silence_duration: float = 1.0,
    ) -> List[Dict[str, float]]:
        """
        Detect silent segments in video.

        Args:
            video_path: Path to video file
            silence_threshold: dB threshold for silence
            silence_duration: Minimum duration for silence

        Returns:
            List of silent segments (start, end)
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            cmd = [
                self.ffmpeg_path,
                "-i",
                video_path,
                "-af",
                f"silencedetect=n={silence_threshold}dB:d={silence_duration}",
                "-f",
                "null",
                "-",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"Silence detection failed: {result.stderr}")
                return []

            # Parse output for silence segments
            segments = []
            output = result.stderr

            import re

            # Find silence_start and silence_end patterns
            start_pattern = r"silence_start: (\d+\.?\d*)"
            end_pattern = r"silence_end: (\d+\.?\d*) \| silence_duration: (\d+\.?\d*)"

            starts = re.findall(start_pattern, output)
            ends = re.findall(end_pattern, output)

            for start, (end, duration) in zip(starts, ends):
                segments.append(
                    {
                        "start": float(start),
                        "end": float(end),
                        "duration": float(duration),
                    }
                )

            return segments

        except Exception as e:
            logger.error(f"Silence detection failed: {str(e)}")
            return []

    def convert_video(
        self,
        input_path: str,
        output_path: str,
        codec: str = "libx264",
        crf: int = 23,
        preset: str = "medium",
        resolution: Optional[str] = None,
        bitrate: Optional[str] = None,
    ) -> bool:
        """
        Convert video format/codec.

        Args:
            input_path: Input video path
            output_path: Output video path
            codec: Video codec
            crf: Constant Rate Factor
            preset: Encoding preset
            resolution: Output resolution (e.g., '1280x720')
            bitrate: Output bitrate (e.g., '2M')

        Returns:
            True if successful
        """
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        try:
            cmd = [self.ffmpeg_path, "-i", input_path, "-y"]

            # Add video codec settings
            cmd.extend(["-c:v", codec])
            cmd.extend(["-crf", str(crf)])
            cmd.extend(["-preset", preset])

            # Add resolution if specified
            if resolution:
                cmd.extend(["-vf", f"scale={resolution}"])

            # Add bitrate if specified
            if bitrate:
                cmd.extend(["-b:v", bitrate])

            # Copy audio
            cmd.extend(["-c:a", "copy"])

            # Output path
            cmd.append(output_path)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600  # 10 minutes timeout
            )

            if result.returncode != 0:
                logger.error(f"Video conversion failed: {result.stderr}")
                return False

            return os.path.exists(output_path)

        except subprocess.SubprocessError as e:
            logger.error(f"Video conversion failed: {str(e)}")
            return False

    def merge_video_audio(
        self, video_path: str, audio_path: str, output_path: str
    ) -> bool:
        """
        Merge video and audio files.

        Args:
            video_path: Path to video file (without audio or with different audio)
            audio_path: Path to audio file
            output_path: Output video path

        Returns:
            True if successful
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")
        if not os.path.exists(audio_path):
            raise ProcessingError(f"Audio file not found: {audio_path}")

        try:
            cmd = [
                self.ffmpeg_path,
                "-i",
                video_path,
                "-i",
                audio_path,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                "-y",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"Video/audio merge failed: {result.stderr}")
                return False

            return os.path.exists(output_path)

        except subprocess.SubprocessError as e:
            logger.error(f"Video/audio merge failed: {str(e)}")
            return False

    def create_thumbnail_grid(
        self,
        video_path: str,
        output_path: str,
        columns: int = 3,
        rows: int = 3,
        width: int = 640,
    ) -> bool:
        """
        Create thumbnail grid from video.

        Args:
            video_path: Path to video file
            output_path: Output image path
            columns: Number of columns
            rows: Number of rows
            width: Output width

        Returns:
            True if successful
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")

        try:
            # Get video duration
            duration = self.get_video_duration(video_path)

            # Calculate timestamps for each thumbnail
            total_thumbnails = columns * rows
            interval = duration / (total_thumbnails + 1)
            timestamps = [interval * (i + 1) for i in range(total_thumbnails)]

            # Extract frames
            temp_dir = os.path.join(os.path.dirname(output_path), "temp_frames")
            os.makedirs(temp_dir, exist_ok=True)

            frame_paths = []
            for i, timestamp in enumerate(timestamps):
                frame_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
                if self.extract_frame(
                    video_path, timestamp, temp_dir, f"frame_{i:03d}"
                ):
                    frame_paths.append(frame_path)

            if not frame_paths:
                return False

            # Create grid using FFmpeg
            # Build filter complex for grid
            inputs = " ".join([f"-i {fp}" for fp in frame_paths])

            # Calculate grid layout
            tile_width = width // columns
            tile_height = tile_width * 9 // 16  # 16:9 aspect ratio

            # Build filter complex
            filter_complex = ""
            for i in range(len(frame_paths)):
                filter_complex += f"[{i}:v]scale={tile_width}:{tile_height}[v{i}];"

            filter_complex += f"[v0]"
            for i in range(1, len(frame_paths)):
                filter_complex += f"[v{i}]"

            filter_complex += f"xstack=inputs={len(frame_paths)}:layout="

            # Create layout string (0_0|w0_0|w0+w1_0, etc.)
            layout_parts = []
            for row in range(rows):
                for col in range(columns):
                    idx = row * columns + col
                    if idx < len(frame_paths):
                        x = col * tile_width
                        y = row * tile_height
                        layout_parts.append(f"{x}_{y}")

            filter_complex += "|".join(layout_parts)
            filter_complex += f"[out]"

            cmd = [
                self.ffmpeg_path,
                *inputs.split(),
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-y",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            # Cleanup temporary frames
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

            if result.returncode != 0:
                logger.error(f"Thumbnail grid creation failed: {result.stderr}")
                return False

            return os.path.exists(output_path)

        except Exception as e:
            logger.error(f"Thumbnail grid creation failed: {str(e)}")
            return False

    def change_aspect_ratio(
        self, input_path: str, output_path: str, aspect_ratio: str
    ) -> bool:
        """Change video aspect ratio."""

        # Parse aspect ratio
        if aspect_ratio == "original":
            return False  # No change needed

        # Define target dimensions
        aspect_map = {
            "16:9": {"width": 1920, "height": 1080, "description": "YouTube, Desktop"},
            "9:16": {
                "width": 1080,
                "height": 1920,
                "description": "TikTok, Shorts, Reels",
            },
            "1:1": {
                "width": 1080,
                "height": 1080,
                "description": "Instagram, Facebook",
            },
            "4:5": {"width": 1080, "height": 1350, "description": "Instagram Portrait"},
            "2:3": {"width": 1080, "height": 1620, "description": "Story, Pinterest"},
            "3:2": {"width": 1920, "height": 1280, "description": "Standard Photo"},
            "21:9": {
                "width": 2560,
                "height": 1080,
                "description": "Ultrawide/Cinematic",
            },
            "5:4": {"width": 1280, "height": 1024, "description": "Facebook, LinkedIn"},
        }

        if aspect_ratio not in aspect_map:
            logger.warning(f"Unknown aspect ratio: {aspect_ratio}")
            return False

        target = aspect_map[aspect_ratio]
        target_width = target["width"]
        target_height = target["height"]

        # Build FFmpeg command
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-vf",
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "copy",
            "-y",
            output_path,
        ]

        logger.info(
            f"Changing aspect ratio to {aspect_ratio} ({target_width}x{target_height})"
        )

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Aspect ratio change failed: {result.stderr}")
            return False

        logger.info(f"Successfully changed aspect ratio to {aspect_ratio}")
        return True

    def change_quality(self, input_path: str, output_path: str, quality: str) -> bool:
        """
        Change video quality/resolution.

        Args:
            input_path: Path to input video
            output_path: Path to output video
            quality: Quality string ('original', '480p', '720p', '1080p', '2K' , '3K', '4k')

        Returns:
            True if successful
        """
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        # If quality is "original", just copy the file
        if quality == "original":
            import shutil

            shutil.copy2(input_path, output_path)
            logger.info(f"Copied original quality video to {output_path}")
            return True

        # Define target resolutions
        quality_map = {
            "480p": {"width": 854, "height": 480, "bitrate": "1M"},
            "720p": {"width": 1280, "height": 720, "bitrate": "2M"},
            "1080p": {"width": 1920, "height": 1080, "bitrate": "4M"},
            "2K": {"width": 2560, "height": 1440, "bitrate": "6M"},  # 2K QHD
            "3K": {"width": 3072, "height": 1728, "bitrate": "7M"},  # 3K (custom)
            "4k": {"width": 3840, "height": 2160, "bitrate": "8M"},
            "8k": {"width": 7680, "height": 4320, "bitrate": "16M"},
        }

        # Normalize quality string (handle variations like '480' vs '480p')
        normalized_quality = quality
        if quality == "480":
            normalized_quality = "480p"
        elif quality == "720":
            normalized_quality = "720p"
        elif quality == "1080":
            normalized_quality = "1080p"

        if normalized_quality not in quality_map:
            logger.warning(f"Unknown quality: {quality}, defaulting to 720p")
            normalized_quality = "720p"

        target = quality_map[normalized_quality]

        try:
            # Build FFmpeg command
            cmd = [
                self.ffmpeg_path,
                "-i",
                input_path,
                "-vf",
                f"scale={target['width']}:{target['height']}:force_original_aspect_ratio=decrease,pad={target['width']}:{target['height']}:(ow-iw)/2:(oh-ih)/2",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-b:v",
                target["bitrate"],
                "-c:a",
                "copy",  # Keep original audio
                "-y",
                output_path,
            ]

            logger.info(
                f"Changing video quality to {quality} ({target['width']}x{target['height']})"
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                logger.error(f"Quality change failed: {result.stderr}")
                return False

            logger.info(f"Successfully changed video quality to {quality}")
            return os.path.exists(output_path)

        except subprocess.SubprocessError as e:
            logger.error(f"Quality change failed: {str(e)}")
            return False

    def change_fps(self, input_path: str, output_path: str, fps: str) -> bool:
        """
        Change video frame rate.

        Args:
            input_path: Path to input video
            output_path: Path to output video
            fps: Target FPS (original, 24, 30, 60)

        Returns:
            True if successful
        """
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        if fps == "original":
            import shutil

            shutil.copy2(input_path, output_path)
            return True

        # Validate FPS value
        fps_values = {"24": 24, "30": 30, "60": 60}
        if fps not in fps_values:
            logger.warning(f"Unknown FPS: {fps}, defaulting to 30")
            fps = "30"

        target_fps = fps_values[fps]

        try:
            cmd = [
                self.ffmpeg_path,
                "-i",
                input_path,
                "-vf",
                f"fps={target_fps}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "copy",
                "-y",
                output_path,
            ]

            logger.info(f"Changing FPS to {target_fps}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"FPS change failed: {result.stderr}")
                return False

            logger.info(f"Successfully changed FPS to {target_fps}")
            return os.path.exists(output_path)

        except subprocess.SubprocessError as e:
            logger.error(f"FPS change failed: {str(e)}")
            return False

    def apply_video_style(self, input_path: str, output_path: str, style: str) -> bool:
        """
        Apply cinematic/bright/dark/gaming style to video using FFmpeg filters.

        Args:
            input_path: Path to input video
            output_path: Path to output video
            style: Style name (cinematic, bright, dark, gaming, etc.)

        Returns:
            True if successful
        """
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        # Define filter chains for each style
        style_filters = {
            # ========== FREE TIER STYLES ==========
            "cinematic": "eq=brightness=0.05:contrast=1.15:saturation=1.1",
            "bright": "eq=brightness=0.12:contrast=1.08:saturation=1.2",
            "educational": "eq=brightness=0.03:contrast=1.1:saturation=1.05",
            "vlog": "eq=brightness=0.08:contrast=1.02:saturation=1.08",
            
            # ========== STARTER TIER STYLES ==========
            "gaming": "eq=saturation=1.25:contrast=1.15:brightness=0.03",
            "travel": "eq=saturation=1.18:contrast=1.05:brightness=0.05",
            
            # ========== PRO TIER STYLES ==========
            "professional": "eq=contrast=1.08:saturation=0.98",
            "documentary": "eq=brightness=0:contrast=1.02:saturation=0.95",
            "wedding": "eq=brightness=0.07:contrast=1.02:saturation=1.05",
            "corporate": "eq=brightness=0.03:contrast=1.08:saturation=0.98",
            "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.06",
            "dark": "eq=brightness=-0.08:contrast=1.15:saturation=0.9",
            "action": "eq=contrast=1.2:brightness=0.03",
            "minimalist": "eq=saturation=0.92:contrast=1.05",
            "vintage": "eq=brightness=0.02:contrast=0.92:saturation=0.88",
            
            # ========== PLUS TIER STYLES ==========
            "cinematic_pro": "eq=brightness=0.06:contrast=1.2:saturation=1.12",
            "artistic": "eq=saturation=1.2:contrast=1.08:brightness=0.03",
            "retro": "eq=brightness=0.02:contrast=0.92:saturation=0.85",
            "futuristic": "eq=saturation=1.25:contrast=1.15:brightness=0.04",
            "cartoon": "eq=saturation=1.2:contrast=1.1",
            "glamour": "eq=brightness=0.05:contrast=1.02:saturation=1.1",
            "mystery": "eq=brightness=-0.05:contrast=1.15:saturation=0.92",
            "tech": "eq=saturation=1.18:contrast=1.12:brightness=0.03",
            "dramatic": "eq=brightness=-0.03:contrast=1.25:saturation=1.1",
            "warm": "eq=brightness=0.04:contrast=1.02:saturation=1.05",
            "cool": "eq=brightness=0.02:contrast=1.03:saturation=1.02",
            "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
            "black_and_white": "hue=s=0,eq=contrast=1.1",
            
            # ========== ENTERPRISE TIER STYLES ==========
            "hollywood": "eq=brightness=0.04:contrast=1.18:saturation=1.15",
            "dreamy": "eq=brightness=0.06:contrast=1.02:saturation=1.08",
            "neon": "eq=saturation=1.3:contrast=1.2:brightness=0.05",
            "pastel": "eq=saturation=0.85:contrast=1.02:brightness=0.07",
            "hdr": "eq=contrast=1.15:saturation=1.12,brightness=0.02",
        }

        # Get filters for the requested style
        filters = style_filters.get(style, style_filters.get("cinematic"))

        # Build filter complex string
        filter_chain = ",".join(filters)

        try:
            cmd = [
                self.ffmpeg_path,
                "-i",
                input_path,
                "-vf",
                filter_chain,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "copy",
                "-y",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"Style application failed: {result.stderr}")
                return False

            logger.info(f"Successfully applied '{style}' style to {output_path}")
            return os.path.exists(output_path)

        except Exception as e:
            logger.error(f"Style application error: {str(e)}")
            return False

    def apply_video_style(self, input_path: str, output_path: str, style: str) -> bool:
        """
        Apply cinematic/bright/dark/gaming style to video using FFmpeg filters.
        Complete production version with all tiers.
        """
        if not os.path.exists(input_path):
            raise ProcessingError(f"Input file not found: {input_path}")

        # ========== COMPLETE STYLE FILTERS - ALL TIERS ==========
        style_filters = {
            # ========== FREE TIER STYLES ==========
            "cinematic": "eq=brightness=0.05:contrast=1.15:saturation=1.1",
            "bright": "eq=brightness=0.12:contrast=1.08:saturation=1.2",
            "educational": "eq=brightness=0.03:contrast=1.1:saturation=1.05",
            "vlog": "eq=brightness=0.08:contrast=1.02:saturation=1.08",
            
            # ========== STARTER TIER STYLES ==========
            "gaming": "eq=saturation=1.25:contrast=1.15:brightness=0.03",
            "travel": "eq=saturation=1.18:contrast=1.05:brightness=0.05",
            
            # ========== PRO TIER STYLES ==========
            "professional": "eq=contrast=1.08:saturation=0.98",
            "documentary": "eq=brightness=0:contrast=1.02:saturation=0.95",
            "wedding": "eq=brightness=0.07:contrast=1.02:saturation=1.05",
            "corporate": "eq=brightness=0.03:contrast=1.08:saturation=0.98",
            "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.06",
            "dark": "eq=brightness=-0.08:contrast=1.15:saturation=0.9",
            "action": "eq=contrast=1.2:brightness=0.03",
            "minimalist": "eq=saturation=0.92:contrast=1.05",
            "vintage": "eq=brightness=0.02:contrast=0.92:saturation=0.88",
            
            # ========== PLUS TIER STYLES ==========
            "cinematic_pro": "eq=brightness=0.06:contrast=1.2:saturation=1.12",
            "artistic": "eq=saturation=1.2:contrast=1.08:brightness=0.03",
            "retro": "eq=brightness=0.02:contrast=0.92:saturation=0.85",
            "futuristic": "eq=saturation=1.25:contrast=1.15:brightness=0.04",
            "cartoon": "eq=saturation=1.2:contrast=1.1",
            "glamour": "eq=brightness=0.05:contrast=1.02:saturation=1.1",
            "mystery": "eq=brightness=-0.05:contrast=1.15:saturation=0.92",
            "tech": "eq=saturation=1.18:contrast=1.12:brightness=0.03",
            "dramatic": "eq=brightness=-0.03:contrast=1.25:saturation=1.1",
            "warm": "eq=brightness=0.04:contrast=1.02:saturation=1.05",
            "cool": "eq=brightness=0.02:contrast=1.03:saturation=1.02",
            "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
            "black_and_white": "hue=s=0,eq=contrast=1.1",
            
            # ========== ENTERPRISE TIER STYLES ==========
            "hollywood": "eq=brightness=0.04:contrast=1.18:saturation=1.15",
            "dreamy": "eq=brightness=0.06:contrast=1.02:saturation=1.08",
            "neon": "eq=saturation=1.3:contrast=1.2:brightness=0.05",
            "pastel": "eq=saturation=0.85:contrast=1.02:brightness=0.07",
            "hdr": "eq=contrast=1.15:saturation=1.12,brightness=0.02",
        }

        # Get filter for the requested style
        filter_str = style_filters.get(style.lower())
        if not filter_str:
            logger.warning(f"Unknown style: {style}, defaulting to 'cinematic'")
            filter_str = style_filters.get("cinematic")

        try:
            cmd = [
                self.ffmpeg_path,
                "-i", input_path,
                "-vf", filter_str,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-c:a", "copy",
                "-y", output_path,
            ]

            logger.info(f"Applying style '{style}' to video")
            logger.info(f"Filter: {filter_str}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"Style application failed: {result.stderr}")
                return False

            logger.info(f"Successfully applied '{style}' style")
            return os.path.exists(output_path)

        except subprocess.SubprocessError as e:
            logger.error(f"Style application error: {str(e)}")
            return False


    def apply_multiple_styles(self, input_path: str, output_path: str, styles: List[str]) -> bool:
        """Apply multiple styles sequentially to a video."""
        if not styles:
            import shutil
            shutil.copy2(input_path, output_path)
            return True

        current_input = input_path
        temp_files = []

        for i, style in enumerate(styles):
            temp_output = output_path if i == len(styles) - 1 else f"{output_path}.temp_{i}.mp4"
            if i < len(styles) - 1:
                temp_files.append(temp_output)

            if not self.apply_video_style(current_input, temp_output, style):
                # Clean up temp files on failure
                for f in temp_files:
                    if os.path.exists(f):
                        os.remove(f)
                return False

            current_input = temp_output

        # Clean up temporary files
        for f in temp_files:
            if os.path.exists(f) and f != output_path:
                os.remove(f)

        return True

    def test_ffmpeg(self) -> Dict[str, Any]:
        """Test FFmpeg installation and capabilities."""
        try:
            # Get version
            version_result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            version_output = (
                version_result.stdout.split("\n")[0]
                if version_result.returncode == 0
                else "Unknown"
            )

            # Get supported codecs
            codecs_result = subprocess.run(
                [self.ffmpeg_path, "-codecs"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            supported_codecs = []
            if codecs_result.returncode == 0:
                for line in codecs_result.stdout.split("\n"):
                    if "libx264" in line or "libx265" in line or "aac" in line:
                        supported_codecs.append(line.strip())

            return {
                "installed": True,
                "version": version_output,
                "ffmpeg_path": self.ffmpeg_path,
                "ffprobe_path": self.ffprobe_path,
                "supported_codecs": supported_codecs[:10],  # First 10
            }

        except Exception as e:
            return {"installed": False, "error": str(e)}
