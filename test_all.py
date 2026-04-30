from src.services.video_service import VideoService
import json

vs = VideoService()

# Get your video ID (check your database or recent uploads)
video = vs.get_video_by_id("YOUR_VIDEO_ID_HERE")

if video:
    print("=== VIDEO OBJECT ATTRIBUTES ===")
    print(f"video_type: {video.video_type}")
    print(f"output_quality: {video.output_quality}")
    print(f'fps: {getattr(video, "fps", "NOT SET")}')
    print(f'audio_quality: {getattr(video, "audio_quality", "NOT SET")}')
    print(f'aspect_ratio: {getattr(video, "aspect_ratio", "NOT SET")}')
    print(f'thumbnail_style: {getattr(video, "thumbnail_style", "NOT SET")}')
    print(f'applied_styles: {getattr(video, "applied_styles", [])}')
    print(f'auto_transcribe: {getattr(video, "auto_transcribe", True)}')

    # Also check the full dict
    print("\n=== VIDEO DICT ===")
    full_dict = video.to_dict()
    print(f'fps in dict: {full_dict.get("fps")}')
    print(f'aspect_ratio in dict: {full_dict.get("aspect_ratio")}')
    print(f'thumbnail_style in dict: {full_dict.get("thumbnail_style")}')
else:
    print("Video not found")
