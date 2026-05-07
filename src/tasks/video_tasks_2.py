"""
Video processing Celery tasks - PRODUCTION VERSION
Single-pass processing - one final video, multiple intermediate files deleted.
"""

import os
import sys
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List
import uuid
import subprocess
import json
import shutil
from pathlib import Path

from .celery_app import celery_app
from services.video_service import VideoService
from services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationChannel,
)
from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)

video_service = VideoService()


def _send_ws_update(video_id, user_id, status, progress, step=None, message=None):
    """Send WebSocket update safely."""
    try:
        from api.websocket import send_video_update
        send_video_update(video_id, user_id, status, progress, step, message)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket update: {e}")


def _send_ws_completed(video_id, user_id, url, proc_time, cost):
    """Send WebSocket completion safely."""
    try:
        from api.websocket import send_video_completed
        send_video_completed(video_id, user_id, url, proc_time, cost)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket completion: {e}")


def _send_ws_failed(video_id, user_id, error, retry_count, can_retry):
    """Send WebSocket failure safely."""
    try:
        from api.websocket import send_video_failed
        send_video_failed(video_id, user_id, error, retry_count, can_retry)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket failure: {e}")


@celery_app.task(bind=True, max_retries=3)
def process_video_async(
    self, video_id: str, user_id: str, options: Dict[str, Any] = None
):
    """
    Process video asynchronously - SINGLE PASS, ONE FINAL VIDEO.
    All features (aspect_ratio, fps, audio_quality, quality, speed) are applied
    in a single FFmpeg command, producing ONE final video file.
    """
    options = options or {}
    from services.user_service import UserService

    logger.info("=" * 80)
    logger.info(f"📥 VIDEO PROCESSING STARTED for {video_id}")
    logger.info(f"📥 Options: {options}")
    logger.info("=" * 80)

    notification_service = NotificationService()
    user_service = UserService()
    send_email_notification = options.get("send_email_notification", False)

    try:
        logger.info(f"Starting video processing for video_id: {video_id}, user_id: {user_id}")

        _send_ws_update(video_id, user_id, "queued", 10, "queued", "Video queued for processing")

        self.update_state(
            state="PROGRESS",
            meta={"current": "starting", "total": 100, "status": "Processing video..."},
        )

        # Get video data
        video = video_service.get_video_by_id(video_id)
        if not video:
            raise ProcessingError(f"Video not found: {video_id}")

        input_path = video.original_path
        if not input_path or not os.path.exists(input_path):
            raise ProcessingError(f"Original video not found: {input_path}")

        # Create output directory
        video_dir = os.path.dirname(input_path)
        final_output_path = os.path.join(video_dir, f"final_processed_{video_id}.mp4")
        temp_output_path = os.path.join(video_dir, f"temp_processing_{uuid.uuid4().hex[:8]}.mp4")

        # Get video info
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", input_path
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        video_info = json.loads(probe_result.stdout) if probe_result.returncode == 0 else {}
        streams = video_info.get('streams', [{}])
        orig_width = streams[0].get('width', 1920) if streams else 1920
        orig_height = streams[0].get('height', 1080) if streams else 1080

        logger.info(f"📐 Original resolution: {orig_width}x{orig_height}")

        # ========== BUILD SINGLE FFMPEG COMMAND ==========
        filters = []
        output_quality = options.get("quality", "720p")
        aspect_ratio = options.get("aspect_ratio")
        fps = options.get("fps")
        speed = options.get("speed")
        audio_quality = options.get("audio_quality")

        # 1. Scale filter (with quality)
        quality_map = {
            "480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080),
            "2K": (2560, 1440), "4k": (3840, 2160), "4K+HDR": (3840, 2160), "8K": (7680, 4320)
        }
        target_w, target_h = quality_map.get(output_quality, (orig_width, orig_height))
        target_w = min(target_w, orig_width)
        target_h = min(target_h, orig_height)
        
        scale_filter = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
        filters.append(scale_filter)

        # 2. Aspect ratio filter (pad after scaling)
        aspect_map = {
            "16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080),
            "4:5": (1080, 1350), "2:3": (1080, 1620), "3:2": (1920, 1280),
            "21:9": (2560, 1080), "5:4": (1280, 1024)
        }
        if aspect_ratio and aspect_ratio in aspect_map:
            ar_w, ar_h = aspect_map[aspect_ratio]
            pad_filter = f"pad={ar_w}:{ar_h}:(ow-iw)/2:(oh-ih)/2"
            filters.append(pad_filter)

        # 3. FPS filter
        if fps and fps != "original" and fps.isdigit():
            fps_filter = f"fps={fps}"
            filters.append(fps_filter)

        # 4. Speed filter (setpts)
        video_speed_filter = None
        audio_speed_filter = None
        if speed and speed != 1.0:
            pts_speed = 1.0 / float(speed)
            video_speed_filter = f"setpts={pts_speed}*PTS"
            audio_speed_filter = f"atempo={speed}"
            filters.append(video_speed_filter)

        # Build filter complex
        filter_complex = ",".join(filters) if filters else "null"

        # Build video encoding parameters
        video_params = ["-c:v", "libx264", "-preset", "medium", "-crf", "23"]

        # Build audio encoding parameters
        audio_bitrate_map = {"128k": "128k", "192k": "192k", "256k": "256k", "320k": "320k"}
        audio_bitrate = audio_bitrate_map.get(audio_quality, "192k") if audio_quality else "192k"

        # Build final command
        cmd = ["ffmpeg", "-i", input_path]

        if video_speed_filter and audio_speed_filter:
            # Separate video and audio streams
            cmd += [
                "-filter_complex",
                f"[0:v]{filter_complex}[v];[0:a]{audio_speed_filter}[a]",
                "-map", "[v]", "-map", "[a]"
            ]
        elif filter_complex != "null":
            cmd += ["-vf", filter_complex]
            if audio_speed_filter:
                cmd += ["-af", audio_speed_filter]

        cmd += video_params + ["-c:a", "aac", "-b:a", audio_bitrate, "-movflags", "+faststart", "-y", temp_output_path]

        logger.info(f"🎬 Running FFmpeg command with filters: {filter_complex}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

        if result.returncode != 0:
            raise ProcessingError(f"FFmpeg failed: {result.stderr[:500]}")

        # Move temp file to final location
        if os.path.exists(temp_output_path) and os.path.getsize(temp_output_path) > 0:
            shutil.move(temp_output_path, final_output_path)
            logger.info(f"✅ Final video saved: {final_output_path}")

            # Clean up any intermediate files
            for f in os.listdir(video_dir):
                if f.startswith("temp_") and f.endswith(".mp4"):
                    try:
                        os.remove(os.path.join(video_dir, f))
                    except:
                        pass

            # Update video record
            video.output_path = final_output_path
            video.output_video_url = final_output_path
            video.output_video_size = os.path.getsize(final_output_path)
            video.output_quality = output_quality
            video.status = "completed"
            video.processing_completed = datetime.utcnow()
            if video.processing_started:
                video.processing_time = (video.processing_completed - video.processing_started).total_seconds()
            video.aspect_ratio = aspect_ratio
            video.fps = fps
            video.audio_quality = audio_quality
            video.speed = speed

            video_service.update_video(video)
            logger.info(f"✅ Video record updated: {final_output_path}")

            _send_ws_completed(video_id, user_id, final_output_path, video.processing_time, 0)

            return {
                "success": True,
                "video_id": video_id,
                "output_url": final_output_path,
                "processing_time": video.processing_time,
            }

        else:
            raise ProcessingError("FFmpeg produced empty output")

    except ProcessingError as e:
        logger.error(f"Video processing failed: {str(e)}")
        _send_ws_failed(video_id, user_id, str(e), 0, True)
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        return {"success": False, "video_id": video_id, "error": str(e), "retries_exhausted": True}

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
        _send_ws_failed(video_id, user_id, str(e), 0, True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {"success": False, "video_id": video_id, "error": str(e), "retries_exhausted": True}