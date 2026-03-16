"""
Video router for API v1.
"""

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import logging
from datetime import datetime
from pathlib import Path

from core.exceptions import ValidationError, UnauthorizedError, ForbiddenError
from api.dependencies import (
    validate_request,
    paginate,
    handle_file_upload,
    track_analytics,
    background_task,
)
from api.schemas.video import (
    VideoUploadSchema,
    VideoUpdateSchema,
    VideoProcessSchema,
    VideoResponseSchema,
    VideoListSchema,
    ProcessingStatusSchema,
    BatchProcessSchema,
    ExportSchema,
)
from services.video_service import VideoService
from services.tier_service import TierService
from tasks.video_tasks import process_video_async
from tasks.cleanup_tasks import cleanup_temporary_files as cleanup_video_files

router = Blueprint("videos", __name__)
logger = logging.getLogger(__name__)

video_service = VideoService()
tier_service = TierService()


@router.route("/upload", methods=["POST"])
@jwt_required()
@handle_file_upload(
    max_size_mb=2048, allowed_extensions=["mp4", "avi", "mov", "mkv", "webm"]
)
@validate_request(VideoUploadSchema)
@track_analytics("video.upload")
def upload_video():
    from flask import g

    """Upload and process a video."""
    user_id = get_jwt_identity()
    file_info = g.uploaded_file
    options = g.validated_data

    try:
        # Check user tier limits
        from services.user_service import UserService

        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        if not user:
            raise UnauthorizedError("User not found")

        # Upload and process video
        video, upload_path = video_service.upload_video(
            user_id=user_id,
            file_obj=file_info["file"],
            filename=file_info["filename"],
            file_size=file_info["size"],
            content_type=file_info["content_type"],
            options=options,
        )

        # Return video information
        response_schema = VideoResponseSchema()
        return jsonify(response_schema.dump(video.to_dict())), 201

    except Exception as e:
        logger.error(f"Video upload failed: {str(e)}")
        raise


@router.route("/", methods=["GET"])
@jwt_required()
@paginate(default_per_page=20, max_per_page=100)
def list_videos():
    """List user's videos."""
    user_id = get_jwt_identity()
    page = request.pagination["page"]
    per_page = request.pagination["per_page"]
    offset = request.pagination["offset"]

    try:
        # Get filters from query parameters
        status = request.args.get("status")
        video_type = request.args.get("type")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        filters = {"user_id": user_id, "is_deleted": False}

        if status:
            filters["status"] = status
        if video_type:
            filters["video_type"] = video_type

        # Get videos from database
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        # Apply date filters if provided
        query = db.query(
            "videos",
            filters=filters,
            order_by="created_at",
            descending=True,
            limit=per_page,
            offset=offset,
        )

        # Get total count for pagination
        total = db.count("videos", filters=filters)

        # Format response
        videos = []
        for video_data in query:
            video = video_service.get_video(video_data["id"], user_id)
            if video:
                videos.append(video.to_dict())

        response_schema = VideoListSchema()
        return (
            jsonify(
                response_schema.dump(
                    {
                        "videos": videos,
                        "total": total,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page,
                    }
                )
            ),
            200,
        )

    except Exception as e:
        logger.error(f"List videos failed: {str(e)}")
        raise


@router.route("/<video_id>", methods=["GET"])
@jwt_required()
def get_video(video_id):
    """Get video details."""
    user_id = get_jwt_identity()

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            raise ValidationError("Video not found", field="video_id")

        response_schema = VideoResponseSchema()
        return jsonify(response_schema.dump(video.to_dict())), 200

    except Exception as e:
        logger.error(f"Get video failed: {str(e)}")
        raise


@router.route("/<video_id>", methods=["PUT"])
@jwt_required()
@validate_request(VideoUpdateSchema)
def update_video(video_id):
    """Update video metadata."""
    from flask import g

    user_id = get_jwt_identity()
    data = g.validated_data

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            raise ValidationError("Video not found", field="video_id")

        # Update video metadata
        if "title" in data:
            video.title = data["title"]
        if "description" in data:
            video.description = data["description"]
        if "tags" in data:
            video.tags = data["tags"]
        if "selected_thumbnail" in data:
            video.selected_thumbnail = data["selected_thumbnail"]
        if "privacy" in data:
            video.privacy = data["privacy"]

        video.updated_at = datetime.utcnow()

        # Save to database
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()
        db.save("videos", video_id, video.to_dict())

        response_schema = VideoResponseSchema()
        return jsonify(response_schema.dump(video.to_dict())), 200

    except Exception as e:
        logger.error(f"Update video failed: {str(e)}")
        raise


@router.route("/<video_id>", methods=["DELETE"])
@jwt_required()
@track_analytics("video.delete")
def delete_video(video_id):
    """Delete a video."""
    user_id = get_jwt_identity()

    try:
        success = video_service.delete_video(video_id, user_id)

        if not success:
            raise ValidationError(
                "Video not found or permission denied", field="video_id"
            )

        return jsonify({"success": True, "message": "Video deleted successfully"}), 200

    except Exception as e:
        logger.error(f"Delete video failed: {str(e)}")
        raise


@router.route("/<video_id>/process", methods=["POST"])
@jwt_required()
@validate_request(VideoProcessSchema)
@track_analytics("video.reprocess")
def reprocess_video(video_id):
    """Reprocess a video with new options."""
    from flask import g

    user_id = get_jwt_identity()
    options = g.validated_data

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            raise ValidationError("Video not found", field="video_id")

        # Check if video can be reprocessed
        if video.status not in ["completed", "failed"]:
            raise ValidationError("Video is still processing", field="video_id")

        # Update video status
        video.status = "queued"
        video.updated_at = datetime.utcnow()

        # Save to database
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()
        db.save("videos", video_id, video.to_dict())

        # Start reprocessing
        process_video_async.delay(video_id, user_id, options)

        response_schema = VideoResponseSchema()
        return jsonify(response_schema.dump(video.to_dict())), 200

    except Exception as e:
        logger.error(f"Reprocess video failed: {str(e)}")
        raise


@router.route("/<video_id>/status", methods=["GET"])
@jwt_required()
def get_processing_status(video_id):
    """Get video processing status."""
    user_id = get_jwt_identity()

    try:
        status = video_service.get_processing_status(video_id, user_id)

        if not status:
            raise ValidationError("Video not found", field="video_id")

        response_schema = ProcessingStatusSchema()
        return jsonify(response_schema.dump(status)), 200

    except Exception as e:
        logger.error(f"Get status failed: {str(e)}")
        raise


@router.route("/<video_id>/download", methods=["GET"])
@jwt_required()
def download_video(video_id):
    """Download processed video."""
    user_id = get_jwt_identity()

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            raise ValidationError("Video not found", field="video_id")

        if video.status != "completed":
            raise ValidationError("Video is not ready for download", field="video_id")

        if not video.output_video_url:
            raise ValidationError("Video output not available", field="video_id")

        # For local files, send file directly
        if video.output_video_url.startswith("/"):
            if os.path.exists(video.output_video_url):
                return send_file(
                    video.output_video_url,
                    as_attachment=True,
                    download_name=f"processed_{video.original_filename}",
                )

        # For remote URLs, redirect or proxy
        return (
            jsonify(
                {
                    "download_url": video.output_video_url,
                    "filename": f"processed_{video.original_filename}",
                    "size": video.output_video_size,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Download video failed: {str(e)}")
        raise


@router.route("/<video_id>/thumbnails", methods=["GET"])
@jwt_required()
def get_thumbnails(video_id):
    """Get video thumbnails."""
    user_id = get_jwt_identity()

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            raise ValidationError("Video not found", field="video_id")

        return (
            jsonify(
                {
                    "ai_thumbnails": video.ai_thumbnails,
                    "extracted_thumbnails": video.extracted_thumbnails,
                    "selected_thumbnail": video.selected_thumbnail,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get thumbnails failed: {str(e)}")
        raise


@router.route("/<video_id>/transcription", methods=["GET"])
@jwt_required()
def get_transcription(video_id):
    """Get video transcription."""
    user_id = get_jwt_identity()

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            raise ValidationError("Video not found", field="video_id")

        return (
            jsonify(
                {
                    "transcription": video.transcription,
                    "language": video.transcription_language,
                    "translated_transcription": video.translated_transcription,
                    "translation_language": video.translation_language,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get transcription failed: {str(e)}")
        raise


@router.route("/batch/process", methods=["POST"])
@jwt_required()
@validate_request(BatchProcessSchema)
def batch_process():
    """Process multiple videos in batch."""
    user_id = get_jwt_identity()
    from flask import g

    data = g.validated_data

    try:
        results = []

        for video_id in data["video_ids"]:
            video = video_service.get_video(video_id, user_id)

            if not video:
                results.append(
                    {
                        "video_id": video_id,
                        "success": False,
                        "error": "Video not found or permission denied",
                    }
                )
                continue

            # Check if video can be processed
            if video.status not in ["completed", "failed"]:
                results.append(
                    {
                        "video_id": video_id,
                        "success": False,
                        "error": "Video is still processing",
                    }
                )
                continue

            # Update video status
            video.status = "queued"
            video.updated_at = datetime.utcnow()

            # Save to database
            from providers.firebase_provider import FirebaseProvider

            db = FirebaseProvider()
            db.save("videos", video_id, video.to_dict())

            # Start processing
            process_video_async.delay(video_id, user_id, data.get("options", {}))

            results.append(
                {"video_id": video_id, "success": True, "message": "Processing started"}
            )

        return jsonify({"results": results}), 200

    except Exception as e:
        logger.error(f"Batch process failed: {str(e)}")
        raise


@router.route("/batch/delete", methods=["POST"])
@jwt_required()
def batch_delete():
    """Delete multiple videos."""
    user_id = get_jwt_identity()

    try:
        video_ids = request.json.get("video_ids", [])

        if not video_ids:
            raise ValidationError("No video IDs provided", field="video_ids")

        if len(video_ids) > 10:
            raise ValidationError(
                "Maximum 10 videos can be deleted at once", field="video_ids"
            )

        results = []

        for video_id in video_ids:
            success = video_service.delete_video(video_id, user_id)

            results.append(
                {
                    "video_id": video_id,
                    "success": success,
                    "message": (
                        "Deleted" if success else "Not found or permission denied"
                    ),
                }
            )

        return jsonify({"results": results}), 200

    except Exception as e:
        logger.error(f"Batch delete failed: {str(e)}")
        raise


@router.route("/stats", methods=["GET"])
@jwt_required()
def get_video_stats():
    """Get user video statistics."""
    user_id = get_jwt_identity()

    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        # Get user's videos
        videos = db.query("videos", filters={"user_id": user_id, "is_deleted": False})

        # Calculate statistics
        total_videos = len(videos)
        completed_videos = len([v for v in videos if v.get("status") == "completed"])
        processing_videos = len([v for v in videos if v.get("status") == "processing"])
        failed_videos = len([v for v in videos if v.get("status") == "failed"])

        total_duration = sum(v.get("duration", 0) for v in videos)
        total_cost = sum(v.get("total_cost", 0) for v in videos)

        # Get tier information
        from services.user_service import UserService

        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        return (
            jsonify(
                {
                    "total_videos": total_videos,
                    "completed_videos": completed_videos,
                    "processing_videos": processing_videos,
                    "failed_videos": failed_videos,
                    "total_duration_minutes": total_duration / 60,
                    "total_cost": total_cost,
                    "videos_remaining_this_month": max(
                        0, user.monthly_video_limit - user.videos_processed_this_month
                    ),
                    "credits_remaining": user.credits_remaining,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Get video stats failed: {str(e)}")
        raise


@router.route("/export", methods=["POST"])
@jwt_required()
@validate_request(ExportSchema)
def export_videos():
    """Export video data."""
    from flask import g

    user_id = get_jwt_identity()
    data = g.validated_data

    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        # Get user's videos
        videos = db.query("videos", filters={"user_id": user_id, "is_deleted": False})

        # Prepare export data based on requested format
        export_data = []

        for video_data in videos:
            video_entry = {
                "id": video_data.get("id"),
                "title": video_data.get("title"),
                "original_filename": video_data.get("original_filename"),
                "duration": video_data.get("duration"),
                "status": video_data.get("status"),
                "created_at": video_data.get("created_at"),
                "output_video_url": video_data.get("output_video_url"),
            }

            if "transcription" in data.get("include", []):
                video_entry["transcription"] = video_data.get("transcription")
                video_entry["translated_transcription"] = video_data.get(
                    "translated_transcription"
                )

            if "metadata" in data.get("include", []):
                video_entry["metadata"] = {
                    "file_size": video_data.get("file_size"),
                    "output_quality": video_data.get("output_quality"),
                    "applied_styles": video_data.get("applied_styles"),
                    "total_cost": video_data.get("total_cost"),
                }

            export_data.append(video_entry)

        # Format based on requested format
        if data["format"] == "json":
            return jsonify({"videos": export_data}), 200

        elif data["format"] == "csv":
            import csv
            from io import StringIO

            if not export_data:
                return jsonify({"error": "No data to export"}), 404

            # Create CSV
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
            writer.writeheader()
            writer.writerows(export_data)

            return (
                jsonify(
                    {
                        "csv": output.getvalue(),
                        "filename": f'video_export_{datetime.utcnow().strftime("%Y%m%d")}.csv',
                    }
                ),
                200,
            )

        elif data["format"] == "srt":
            # Generate SRT captions for first video with transcription
            for video in export_data:
                if "transcription" in video and video["transcription"]:
                    srt_content = generate_srt_captions(video["transcription"])
                    return (
                        jsonify(
                            {
                                "srt": srt_content,
                                "filename": f'{video.get("title", "video")}.srt',
                            }
                        ),
                        200,
                    )

            return jsonify({"error": "No videos with transcription found"}), 404

        else:
            raise ValidationError(
                f"Unsupported format: {data['format']}", field="format"
            )

    except Exception as e:
        logger.error(f"Export videos failed: {str(e)}")
        raise


def generate_srt_captions(transcription, segment_duration=3):
    """Generate SRT captions from transcription."""
    # Split transcription into segments
    words = transcription.split()
    segments = []

    for i in range(0, len(words), 10):  # 10 words per segment
        segment = " ".join(words[i : i + 10])
        start_time = i * segment_duration
        end_time = (i + 10) * segment_duration

        segments.append(
            {
                "index": len(segments) + 1,
                "start_time": format_srt_time(start_time),
                "end_time": format_srt_time(end_time),
                "text": segment,
            }
        )

    # Format as SRT
    srt_lines = []
    for segment in segments:
        srt_lines.append(str(segment["index"]))
        srt_lines.append(f"{segment['start_time']} --> {segment['end_time']}")
        srt_lines.append(segment["text"])
        srt_lines.append("")

    return "\n".join(srt_lines)


def format_srt_time(seconds):
    """Format seconds to SRT time format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
