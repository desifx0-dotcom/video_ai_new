"""
Video router for API v1 - Complete production version with tier enforcement.
"""

from flask import Blueprint, request, jsonify, send_file, g
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import logging
from datetime import datetime
from typing import Optional, Any
from pathlib import Path
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from core.domain.entities.user import Tier
from services.credit_service import CreditService
from services.thumbnail_service import ThumbnailService
from services.title_service import TitleService
from tasks.video_tasks import process_video_async, create_short_clips_async, apply_different_styles_async, duplicate_video_async

from core.exceptions import (
    ValidationError,
    UnauthorizedError,
    ForbiddenError,
    TierLimitExceeded,
    InsufficientCreditsError,
)
from api.dependencies import (
    validate_request,
    paginate,
    handle_file_upload,
    track_analytics,
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
    VideoRegenerateThumbnailSchema,
    VideoRegenerateMetadataSchema,
    RegenerationResponseSchema,
)
from services.video_service import VideoService
from services.tier_service import TierService
from services.credit_service import CreditService
from services.user_service import UserService
from services.thumbnail_service import ThumbnailService
from services.title_service import TitleService
from tasks.video_tasks import process_video_async

router = Blueprint("videos", __name__)
logger = logging.getLogger(__name__)

# Initialize services
video_service = VideoService()
tier_service = TierService()
credit_service = CreditService()
user_service = UserService()
thumbnail_service = ThumbnailService()
title_service = TitleService()


@router.route("/upload", methods=["POST"])
@jwt_required()
@handle_file_upload(
    max_size_mb=2048, allowed_extensions=["mp4", "avi", "mov", "mkv", "webm"]
)
@validate_request(VideoUploadSchema)
@track_analytics("video.upload")
def upload_video():
    """Upload and process a video with full tier enforcement."""
    user_id = get_jwt_identity()
    file_info = g.uploaded_file
    options = g.validated_data

    try:
        # Get user
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Let video_service handle everything (duration, silent detection, tier checks, metadata)
        video, upload_path = video_service.upload_video(
            user_id=user_id,
            file_obj=file_info["file"],
            filename=file_info["filename"],
            file_size=file_info["size"],
            content_type=file_info["content_type"],
            options=options,
        )

        # Build response
        response_schema = VideoResponseSchema()
        response_data = response_schema.dump(video.to_dict())

        # Add display values from video object (already set in video_service)
        response_data["original_fps"] = getattr(video, "original_fps", "unknown")
        response_data["original_audio_quality"] = getattr(video, "original_audio_quality", "unknown")
        response_data["original_aspect_ratio"] = getattr(video, "original_aspect_ratio", "unknown")
        response_data["original_resolution"] = getattr(video, "original_resolution", "unknown")

        return jsonify(response_data), 201

    except InsufficientCreditsError as e:
        return jsonify({
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": str(e),
                "credits_needed": getattr(e, "credits_needed", 1),
            }
        }), 403

    except TierLimitExceeded as e:
        return jsonify({
            "error": {
                "code": "TIER_LIMIT_EXCEEDED",
                "message": str(e),
                "upgrade_url": "/pricing",
            }
        }), 403

    except ValidationError as e:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(e),
                "field": getattr(e, "field", None),
            }
        }), 400

    except Exception as e:
        logger.error(f"Video upload failed: {str(e)}", exc_info=True)
        return jsonify({
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e),
            }
        }), 500

@router.route("/<video_id>/process", methods=["POST"])
@jwt_required()
@validate_request(VideoProcessSchema)
@track_analytics("video.process")
def process_video(video_id):
    """
    Process or reprocess a video with user-selected options.
    This handles both initial processing and reprocessing with new settings.
    """
    from flask import g
    from datetime import datetime
    from services.credit_service import CreditService
    from services.tier_service import TierService
    from core.exceptions import InsufficientCreditsError, TierLimitExceeded

    user_id = get_jwt_identity()
    options = g.validated_data
    credit_service = CreditService()
    tier_service = TierService()

    try:
        # Get the video
        video = video_service.get_video_by_id(video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Check if user owns this video
        if video.user_id != user_id:
            return (
                jsonify({"error": "You don't have permission to process this video"}),
                403,
            )

        # Get user for tier and credit checks
        user = user_service.get_user_by_id(user_id)

        # ========== APPLY USER-SELECTED OPTIONS TO VIDEO OBJECT ==========
        logger.info(f"🔄 Processing video {video_id} with user options:")
        logger.info(f"   Quality: {options.get('quality')}")
        logger.info(f"   FPS: {options.get('fps')}")
        logger.info(f"   Audio Quality: {options.get('audio_quality')}")
        logger.info(f"   Aspect Ratio: {options.get('aspect_ratio')}")
        logger.info(f"   Thumbnail Style: {options.get('thumbnail_style')}")
        logger.info(f"   Styles: {options.get('styles')}")

        # Update video with user's processing options
        if options.get("quality"):
            video.output_quality = options["quality"]
        if options.get("fps"):
            video.fps = options["fps"]
        if options.get("audio_quality"):
            video.audio_quality = options["audio_quality"]
        if options.get("aspect_ratio"):
            video.aspect_ratio = options["aspect_ratio"]
        if options.get("thumbnail_style"):
            video.thumbnail_style = options["thumbnail_style"]
        if options.get("styles"):
            video.applied_styles = options["styles"]
        if options.get("auto_transcribe") is not None:
            video.auto_transcribe = options["auto_transcribe"]
        if options.get("generate_chapters") is not None:
            video.generate_chapters = options["generate_chapters"]
        if options.get("remove_silence") is not None:
            video.remove_silence = options["remove_silence"]
        if options.get("translation_language"):
            video.translation_language = options["translation_language"]
        if options.get("speed") is not None:
            video.speed = options["speed"]
            logger.info(f"✅ Setting speed from frontend: {video.speed}x")

        # Check if this is a reprocessing (video already completed)
        is_reprocessing = video.status == "completed"

        # Set status to queued/processing
        video.status = "queued"
        video.processing_started = None  # Reset processing timers
        video.processing_completed = None
        video.processing_time = None
        video.updated_at = datetime.utcnow()

        # Save updated video to database
        video_service.update_video(video)
        logger.info(f"✅ Video options saved to database: {video.to_dict()}")

        # Check credits for processing (if not unlimited tier)
        if user.tier not in ["plus", "enterprise"]:
            credits_needed = max(1, int(video.duration) // 60)
            if user.credits_remaining < credits_needed:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "INSUFFICIENT_CREDITS",
                                "message": f"Insufficient credits: {user.credits_remaining}/{credits_needed}",
                                "credits_needed": credits_needed,
                            }
                        }
                    ),
                    403,
                )

            # Deduct credits
            credit_service.use_credits(
                user_id,
                credits_needed,
                f"Video processing: {video.original_filename}",
                video_id=video_id,
            )

        # Prepare options for Celery task
        celery_options = {
            "quality": video.output_quality,
            "fps": video.fps,
            "audio_quality": video.audio_quality,
            "aspect_ratio": getattr(video, "aspect_ratio", "original"),
            "thumbnail_style": video.thumbnail_style,
            "styles": video.applied_styles,
            "auto_transcribe": video.auto_transcribe,
            "generate_chapters": video.generate_chapters,
            "remove_silence": video.remove_silence,
            "translation_language": video.translation_language,
            "is_reprocessing": is_reprocessing,
            "send_email_notification": options.get("send_email_notification", False),
            "speed": float(options.get("speed", 1.0)),
        }

        logger.info(f"📤 Sending to Celery with options: {celery_options}")

        # Start async processing
        from tasks.video_tasks import process_video_async

        process_video_async.delay(video_id, user_id, celery_options)

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Processing started"
                        if not is_reprocessing
                        else "Reprocessing started"
                    ),
                    "video_id": video_id,
                }
            ),
            200,
        )

    except InsufficientCreditsError as e:
        return (
            jsonify(
                {
                    "error": {
                        "code": "INSUFFICIENT_CREDITS",
                        "message": str(e),
                        "credits_needed": getattr(e, "credits_needed", 1),
                    }
                }
            ),
            403,
        )
    except TierLimitExceeded as e:
        return (
            jsonify(
                {
                    "error": {
                        "code": "TIER_LIMIT_EXCEEDED",
                        "message": str(e),
                        "upgrade_url": "/pricing",
                    }
                }
            ),
            403,
        )
    except Exception as e:
        logger.error(f"Process video failed for {video_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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


@router.route("/<video_id>/regenerate-thumbnail", methods=["POST"])
@jwt_required()
@validate_request(VideoRegenerateThumbnailSchema)
def regenerate_thumbnail(video_id):
    """Regenerate a single thumbnail with a different concept."""
    user_id = get_jwt_identity()
    data = g.validated_data

    try:
        # Get video
        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Get user
        user = user_service.get_user_by_id(user_id)

        # Check thumbnail regeneration limits
        max_thumbnails = tier_service.get_ai_thumbnails_count(user.tier)
        current_regens = getattr(video, "thumbnail_regenerations", 0)

        if current_regens >= max_thumbnails:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "REGENERATION_LIMIT_EXCEEDED",
                            "message": f"You've used {current_regens} of {max_thumbnails} thumbnail regenerations.",
                            "current": current_regens,
                            "limit": max_thumbnails,
                            "upgrade_url": "/pricing",
                        }
                    }
                ),
                403,
            )

        # Check credits
        if not credit_service.can_process(user_id, "thumbnail_generation"):
            return (
                jsonify(
                    {
                        "error": {
                            "code": "INSUFFICIENT_CREDITS",
                            "message": "Insufficient credits for thumbnail regeneration.",
                            "credits_needed": 2,
                            "credits_remaining": credit_service.get_credits(user_id),
                            "upgrade_url": "/pricing",
                        }
                    }
                ),
                403,
            )

        # Generate new thumbnail
        result = thumbnail_service.regenerate_thumbnail(
            video_id=video_id,
            video_path=video.original_path,
            title=video.title,
            video_type="silent" if getattr(video, "is_silent", False) else "speech",
            tier=user.tier,
            transcription=video.transcription,
            user_id=user_id,
        )

        # Deduct credits (2 credits for thumbnail regeneration)
        credit_service.use_credits(
            user_id,
            2,
            f"Thumbnail regeneration for video {video_id}",
            video_id=video_id,
            operation="thumbnail_regeneration",
        )

        # Update video tracking
        video.thumbnail_regenerations = current_regens + 1
        if not hasattr(video, "used_thumbnail_concepts"):
            video.used_thumbnail_concepts = []
        video.used_thumbnail_concepts.append(result.get("concept", ""))

        # Update video in database
        video_service.update_video(video)

        response_schema = RegenerationResponseSchema()
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Thumbnail regenerated successfully",
                    "regenerations_remaining": max_thumbnails - (current_regens + 1),
                    "data": result,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Thumbnail regeneration failed: {str(e)}")
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500


@router.route("/<video_id>/title/regenerate", methods=["POST"])
@jwt_required()
def regenerate_video_title(video_id):
    """Regenerate video title."""
    user_id = get_jwt_identity()

    try:
        from services.title_service import TitleService
        from services.user_service import UserService

        user_service = UserService()
        title_service = TitleService()

        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        user = user_service.get_user_by_id(user_id)

        # Check regeneration limits
        max_regens = tier_service.get_text_regenerations(user.tier)
        current_regens = getattr(video, "title_regenerations", 0)

        if current_regens >= max_regens:
            return (
                jsonify(
                    {
                        "error": f"Regeneration limit reached. Max {max_regens} regenerations allowed."
                    }
                ),
                403,
            )

        # Generate new title
        result = title_service.generate_metadata(
            transcript=video.transcription or "",
            video_id=video_id,
            options={"tier": user.tier.value},
        )

        new_title = result.get("title", video.title)

        # Update video
        video.title = new_title
        video.title_regenerations = current_regens + 1
        video_service.update_video(video)

        return (
            jsonify(
                {
                    "success": True,
                    "title": new_title,
                    "regenerations_used": current_regens + 1,
                    "regenerations_remaining": max_regens - (current_regens + 1),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to regenerate title: {e}")
        return jsonify({"error": str(e)}), 500


@router.route("/<video_id>/regenerate-metadata", methods=["POST"])
@jwt_required()
@validate_request(VideoRegenerateMetadataSchema)
def regenerate_metadata(video_id):
    """Regenerate title, description, or tags with different concepts."""
    user_id = get_jwt_identity()
    data = g.validated_data

    try:
        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        user = user_service.get_user_by_id(user_id)

        # Check regeneration limits
        max_regens = tier_service.get_text_regenerations(user.tier)
        current_regens = getattr(video, "title_regenerations", 0)

        if current_regens >= max_regens:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "REGENERATION_LIMIT_EXCEEDED",
                            "message": f"You've used {current_regens} of {max_regens} metadata regenerations.",
                            "current": current_regens,
                            "limit": max_regens,
                            "upgrade_url": "/pricing",
                        }
                    }
                ),
                403,
            )

        # Calculate credits needed
        credits_needed = 0
        if data.get("regenerate_title", False):
            credits_needed += 1
        if data.get("regenerate_description", False):
            credits_needed += 1
        if data.get("regenerate_tags", False):
            credits_needed += 1

        if credits_needed > 0:
            if not credit_service.can_process(user_id, "title_generation"):
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "INSUFFICIENT_CREDITS",
                                "message": "Insufficient credits for metadata regeneration.",
                                "credits_needed": credits_needed,
                                "credits_remaining": credit_service.get_credits(
                                    user_id
                                ),
                                "upgrade_url": "/pricing",
                            }
                        }
                    ),
                    403,
                )

        # Get previous metadata
        previous_metadata = {
            "title": video.title,
            "description": video.description,
            "tags": video.tags,
        }

        # Generate new metadata
        result = title_service.regenerate_metadata(
            video_id=video_id,
            transcript=video.transcription,
            user_tier=user.tier,
            previous_metadata=previous_metadata,
            regenerate_title=data.get("regenerate_title", False),
            regenerate_description=data.get("regenerate_description", False),
            regenerate_tags=data.get("regenerate_tags", False),
        )

        # Deduct credits
        if data.get("regenerate_title", False):
            credit_service.use_credits(
                user_id,
                1,
                f"Title regeneration for video {video_id}",
                video_id=video_id,
                operation="title_regeneration",
            )
            video.title = result.get("title")
            video.title_regenerations = current_regens + 1

        if data.get("regenerate_description", False):
            credit_service.use_credits(
                user_id,
                1,
                f"Description regeneration for video {video_id}",
                video_id=video_id,
                operation="description_regeneration",
            )
            video.description = result.get("description")

        if data.get("regenerate_tags", False):
            credit_service.use_credits(
                user_id,
                1,
                f"Tags regeneration for video {video_id}",
                video_id=video_id,
                operation="tags_regeneration",
            )
            video.tags = result.get("tags", [])

        # Track used concepts
        if not hasattr(video, "used_title_concepts"):
            video.used_title_concepts = []
        if result.get("concept"):
            video.used_title_concepts.append(result["concept"])

        video.updated_at = datetime.utcnow()
        video_service.update_video(video)

        response_schema = RegenerationResponseSchema()
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Metadata regenerated successfully",
                    "regenerations_remaining": max_regens - (current_regens + 1),
                    "data": {
                        "title": video.title,
                        "description": video.description,
                        "tags": video.tags,
                        "concept_used": result.get("concept"),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Metadata regeneration failed: {str(e)}")
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500

# ========== QUICK ACTIONS ENDPOINTS ==========

@router.route("/<video_id>/apply-styles", methods=["POST"])
@jwt_required()
@track_analytics("video.apply_styles")
def apply_different_styles(video_id):
    """
    Apply different video styles to the processed video.
    Costs: 1 credit per video
    """
    user_id = get_jwt_identity()
    credit_service = CreditService()
    user_service = UserService()
    
    try:
        # Get video
        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        # Check if video is completed
        if video.status != "completed":
            return jsonify({"error": "Video must be completed before applying styles"}), 400
        
        # Check credits
        if not credit_service.can_process(user_id, "style_application"):
            credits_needed = credit_service.get_operation_cost("style_application")
            return jsonify({
                "error": {
                    "code": "INSUFFICIENT_CREDITS",
                    "message": f"Insufficient credits. Need {credits_needed} credit(s) to apply styles.",
                    "credits_needed": credits_needed,
                    "credits_remaining": credit_service.get_credits(user_id),
                    "upgrade_url": "/pricing"
                }
            }), 403
        
        # Get user for tier check
        user = user_service.get_user_by_id(user_id)
        
        # Get style options from request body
        data = request.get_json() or {}
        styles = data.get("styles", [])
        
        if not styles:
            return jsonify({"error": "No styles provided"}), 400
        
        # Check if styles are allowed for user tier
        tier_service = TierService()
        tier_spec = tier_service.get_tier(user.tier)
        
        # Deduct credits (1 credit for style application)
        credit_service.use_credits(
            user_id=user_id,
            amount=1,
            description=f"Apply styles to video: {video.original_filename}",
            video_id=video_id,
            operation="style_application"
        )
        
        # Queue background task for style application
        task = apply_different_styles_async.delay(
            video_id=video_id,
            user_id=user_id,
            styles=styles,
            output_quality=video.output_quality
        )
        
        return jsonify({
            "success": True,
            "message": "Style application started",
            "task_id": task.id,
            "credits_deducted": 1,
            "credits_remaining": credit_service.get_credits(user_id)
        }), 202
        
    except InsufficientCreditsError as e:
        return jsonify({
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": str(e),
                "credits_needed": getattr(e, "credits_needed", 1),
                "upgrade_url": "/pricing"
            }
        }), 403
    except Exception as e:
        logger.error(f"Apply styles failed for {video_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@router.route("/<video_id>/create-clips", methods=["POST"])
@jwt_required()
@track_analytics("video.create_clips")
def create_short_clips(video_id):
    """
    Create short clips from the video.
    Costs: 1 credit per clip created
    """
    user_id = get_jwt_identity()
    credit_service = CreditService()
    user_service = UserService()
    
    try:
        # Get video
        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        # Check if video is completed
        if video.status != "completed":
            return jsonify({"error": "Video must be completed before creating clips"}), 400
        
        # Get clip options from request
        data = request.get_json() or {}
        clip_count = data.get("clip_count", 3)
        clip_duration = data.get("clip_duration", 15)  # seconds per clip
        aspect_ratio = data.get("aspect_ratio", "9:16")  # TikTok/Shorts format
        
        # Validate clip count
        max_clips = 10
        if clip_count > max_clips:
            return jsonify({"error": f"Maximum {max_clips} clips allowed per request"}), 400
        
        # Calculate credits needed (1 credit per clip)
        credits_needed = clip_count
        credit_cost_per_clip = 1
        
        # Check credits
        if not credit_service.can_process(user_id, "clip_creation"):
            return jsonify({
                "error": {
                    "code": "INSUFFICIENT_CREDITS",
                    "message": f"Insufficient credits. Need {credits_needed} credit(s) to create {clip_count} clip(s).",
                    "credits_needed": credits_needed,
                    "credits_remaining": credit_service.get_credits(user_id),
                    "upgrade_url": "/pricing"
                }
            }), 403
        
        # Get user
        user = user_service.get_user_by_id(user_id)
        
        # Check if batch clip creation is allowed for tier
        tier_service = TierService()
        tier_spec = tier_service.get_tier(user.tier)
        
        # Deduct credits (1 credit per clip)
        credit_service.use_credits(
            user_id=user_id,
            amount=credits_needed,
            description=f"Create {clip_count} short clip(s) from video: {video.original_filename}",
            video_id=video_id,
            operation="clip_creation"
        )
        
        # Queue background task for clip creation
        task = create_short_clips_async.delay(
            video_id=video_id,
            user_id=user_id,
            clip_count=clip_count,
            clip_duration=clip_duration,
            aspect_ratio=aspect_ratio
        )
        
        return jsonify({
            "success": True,
            "message": f"Creating {clip_count} short clip(s)",
            "task_id": task.id,
            "credits_deducted": credits_needed,
            "credits_remaining": credit_service.get_credits(user_id),
            "credit_cost_per_clip": credit_cost_per_clip
        }), 202
        
    except InsufficientCreditsError as e:
        return jsonify({
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": str(e),
                "credits_needed": getattr(e, "credits_needed", 1),
                "upgrade_url": "/pricing"
            }
        }), 403
    except Exception as e:
        logger.error(f"Create clips failed for {video_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@router.route("/<video_id>/duplicate", methods=["POST"])
@jwt_required()
@track_analytics("video.duplicate")
def duplicate_video(video_id):
    """
    Duplicate video with new processing options.
    Costs: 1 credit for duplication + processing cost if reprocessing
    """
    user_id = get_jwt_identity()
    credit_service = CreditService()
    user_service = UserService()
    
    try:
        # Get original video
        original_video = video_service.get_video(video_id, user_id)
        if not original_video:
            return jsonify({"error": "Video not found"}), 404
        
        # Get duplicate options from request
        data = request.get_json() or {}
        new_options = data.get("options", {})
        reprocess = data.get("reprocess", True)
        
        # Check credits for duplication (1 credit)
        if not credit_service.can_process(user_id, "duplication"):
            return jsonify({
                "error": {
                    "code": "INSUFFICIENT_CREDITS",
                    "message": "Insufficient credits for duplication. Need 1 credit.",
                    "credits_needed": 1,
                    "credits_remaining": credit_service.get_credits(user_id),
                    "upgrade_url": "/pricing"
                }
            }), 403
        
        # Get user
        user = user_service.get_user_by_id(user_id)
        
        # Deduct duplication credit
        credit_service.use_credits(
            user_id=user_id,
            amount=1,
            description=f"Duplicate video: {original_video.original_filename}",
            video_id=video_id,
            operation="duplication"
        )
        
        # Queue background task for duplication
        task = duplicate_video_async.delay(
            original_video_id=video_id,
            user_id=user_id,
            new_options=new_options,
            reprocess=reprocess
        )
        
        return jsonify({
            "success": True,
            "message": "Video duplication started",
            "task_id": task.id,
            "credits_deducted": 1,
            "credits_remaining": credit_service.get_credits(user_id)
        }), 202
        
    except InsufficientCreditsError as e:
        return jsonify({
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": str(e),
                "credits_needed": getattr(e, "credits_needed", 1),
                "upgrade_url": "/pricing"
            }
        }), 403
    except Exception as e:
        logger.error(f"Duplicate video failed for {video_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@router.route("/credits/check", methods=["GET"])
@jwt_required()
def check_credits_for_action():
    """Check if user has enough credits for quick actions."""
    user_id = get_jwt_identity()
    credit_service = CreditService()
    
    credits = credit_service.get_credits(user_id)
    
    return jsonify({
        "credits_remaining": credits,
        "can_apply_style": credits >= 1,
        "can_create_clip": credits >= 1,
        "can_duplicate": credits >= 1,
        "operation_costs": {
            "apply_style": 1,
            "create_clip": 1,
            "duplicate": 1
        }
    })

# ========== QUICK ACTIONS ENDPOINTS ==========

@router.route("/credits/balance", methods=["GET"])
@jwt_required()
def get_credit_balance():
    """Get current user's credit balance."""
    user_id = get_jwt_identity()
    credit_service = CreditService()
    user_service = UserService()
    tier_service = TierService()
    
    try:
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "credits_remaining": user.credits_remaining,
            "tier": user.tier.value,
            "monthly_credits": tier_service.get_credits_per_month(user.tier),
            "credits_used_this_month": getattr(user, "credits_used_this_month", 0),
            "operation_costs": {
                "transcription": 1,
                "title_generation": 1,
                "thumbnail_generation": 2,
                "regeneration": 2,
                "translation": 1,
                "style_application": 1,
                "clip_creation": 1,
                "duplication": 1
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get credit balance: {str(e)}")
        return jsonify({"error": str(e)}), 500

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day"])


@router.route("/<video_id>/status", methods=["GET"])
@jwt_required()
@limiter.limit("300 per minute")
def get_processing_status(video_id):
    """Get video processing status."""
    user_id = get_jwt_identity()

    try:
        # First, check if video exists
        video = video_service.get_video_by_id(video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Check if user owns this video
        if video.user_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        # Get processing status
        status_data = {
            "video_id": video.id,
            "status": (
                video.status if isinstance(video.status, str) else video.status.value
            ),
            "progress": video.get_progress() if hasattr(video, "get_progress") else 0,
            "error": getattr(video, "error_message", None),
            "current_step": getattr(video, "current_step", None),
        }

        response_schema = ProcessingStatusSchema()
        return jsonify(response_schema.dump(status_data)), 200

    except Exception as e:
        logger.error(f"Get status failed: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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

@router.route("/thumbnails/<path:thumbnail_path>", methods=["GET"])
@jwt_required(optional=True)
def serve_thumbnail(thumbnail_path):
    """Serve thumbnail images."""
    import os
    from flask import send_file, abort
    
    # Handle URL decoding
    import urllib.parse
    thumbnail_path = urllib.parse.unquote(thumbnail_path)
    
    # Handle Windows paths
    if os.name == "nt":
        thumbnail_path = thumbnail_path.replace("/", "\\")
    
    # Check if file exists
    if not os.path.exists(thumbnail_path):
        print(f"❌ Thumbnail not found: {thumbnail_path}")
        abort(404)
    
    # Log success
    print(f"📸 Serving thumbnail: {thumbnail_path}")
    
    return send_file(thumbnail_path, mimetype="image/png", as_attachment=False)

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


@router.route("/<video_id>/raw-data", methods=["GET"])
@jwt_required()
def get_video_raw_data(video_id):
    """Get raw processing data for debugging."""
    user_id = get_jwt_identity()

    try:
        video = video_service.get_video(video_id, user_id)

        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Convert video object to dictionary with all attributes
        raw_data = {
            "id": video.id,
            "user_id": video.user_id,
            "original_filename": video.original_filename,
            "file_size": video.file_size,
            "duration": video.duration,
            "status": (
                video.status.value if hasattr(video.status, "value") else video.status
            ),
            "video_type": (
                video.video_type.value
                if hasattr(video.video_type, "value")
                else video.video_type
            ),
            "title": video.title,
            "description": video.description,
            "transcription": video.transcription,
            "tags": video.tags,
            "ai_thumbnails": video.ai_thumbnails,
            "extracted_thumbnails": video.extracted_thumbnails,
            "selected_thumbnail": video.selected_thumbnail,
            "output_quality": video.output_quality,
            "output_video_url": video.output_video_url,
            "output_video_size": video.output_video_size,
            "applied_styles": video.applied_styles,
            "processed_tier": video.processed_tier,
            "processing_time": video.processing_time,
            "total_cost": video.total_cost,
            "created_at": video.created_at.isoformat() if video.created_at else None,
            "updated_at": video.updated_at.isoformat() if video.updated_at else None,
            "processing_started": (
                video.processing_started.isoformat()
                if video.processing_started
                else None
            ),
            "processing_completed": (
                video.processing_completed.isoformat()
                if video.processing_completed
                else None
            ),
            "error_message": video.error_message,
            "retry_count": video.retry_count,
            "aspect_ratio": getattr(video, "aspect_ratio", None),
            "fps": getattr(video, "fps", None),
            "audio_quality": getattr(video, "audio_quality", None),
            "thumbnail_style": getattr(video, "thumbnail_style", None),
        }

        return jsonify(raw_data), 200

    except Exception as e:
        logger.error(f"Error getting raw data: {e}")
        return jsonify({"error": str(e)}), 500


@router.route("/stats", methods=["GET"])
@jwt_required()
@limiter.limit("300 per minute")
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

@router.route("/<video_id>/status", methods=["GET"])
@jwt_required()
def get_video_status(video_id):
    """Get video processing status with proper progress."""
    user_id = get_jwt_identity()
    
    try:
        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        # Safely get attributes with defaults
        status = getattr(video, 'status', 'pending')
        
        # Handle VideoStatus enum (convert to string if needed)
        if hasattr(status, 'value'):
            status = status.value
        
        # Get progress - try multiple sources
        progress = getattr(video, 'progress', 0)
        if progress == 0:
            # Fallback progress mapping
            progress_map = {
                'uploaded': 5,
                'queued': 10,
                'pending': 10,
                'processing': 15,
                'analyzing': 25,
                'transcribing': 40,
                'generating_metadata': 50,
                'generating_thumbnails': 60,
                'applying_styles': 75,
                'applying_filters': 85,
                'translating': 85,
                'compressing': 95,
                'completed': 100,
                'failed': 0,
                'error': 0
            }
            progress = progress_map.get(status, 0)
        
        # Get current step
        current_step = getattr(video, 'current_step', None)
        if not current_step:
            # Map status to step name
            step_map = {
                'uploaded': 'uploaded',
                'queued': 'queued',
                'processing': 'processing',
                'analyzing': 'analyzing',
                'transcribing': 'transcribing',
                'generating_metadata': 'generating_metadata',
                'generating_thumbnails': 'generating_thumbnails',
                'applying_styles': 'applying_styles',
                'applying_filters': 'applying_filters',
                'completed': 'completed',
                'failed': 'failed'
            }
            current_step = step_map.get(status, status)
        
        # Calculate estimated time if processing
        estimated_seconds = 0
        if status in ['processing', 'queued', 'analyzing', 'transcribing', 'generating_metadata', 'generating_thumbnails', 'applying_styles', 'applying_filters']:
            try:
                created_at = getattr(video, 'created_at', None)
                if created_at:
                    # Handle datetime objects
                    if hasattr(created_at, 'isoformat'):
                        elapsed = (datetime.utcnow() - created_at).total_seconds()
                    else:
                        elapsed = 60
                else:
                    elapsed = 60
                
                if progress > 0:
                    estimated_seconds = int((elapsed / progress) * (100 - progress))
                else:
                    estimated_seconds = 120  # Default 2 minutes
            except:
                estimated_seconds = 120
        
        # Get output URL safely
        output_url = getattr(video, 'output_video_url', None)
        if not output_url:
            output_url = getattr(video, 'output_path', None)
        
        # Get timestamps safely
        created_at_str = None
        updated_at_str = None
        try:
            created_at = getattr(video, 'created_at', None)
            if created_at:
                if hasattr(created_at, 'isoformat'):
                    created_at_str = created_at.isoformat()
                elif isinstance(created_at, str):
                    created_at_str = created_at
        except:
            pass
        
        try:
            updated_at = getattr(video, 'updated_at', None)
            if updated_at:
                if hasattr(updated_at, 'isoformat'):
                    updated_at_str = updated_at.isoformat()
                elif isinstance(updated_at, str):
                    updated_at_str = updated_at
        except:
            pass
        
        return jsonify({
            "video_id": video_id,
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "estimated_time_remaining": estimated_seconds,
            "output_url": output_url if status == 'completed' else None,
            "error_message": getattr(video, 'error_message', None),
            "created_at": created_at_str,
            "updated_at": updated_at_str
        }), 200
        
    except Exception as e:
        logger.error(f"Get video status failed for {video_id}: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "video_id": video_id,
            "status": "error"
        }), 500

@router.route("/<video_id>/regenerations-remaining", methods=["GET"])
@jwt_required()
def get_regenerations_remaining(video_id):
    """Get remaining regeneration counts for a video."""
    user_id = get_jwt_identity()

    try:
        from services.user_service import UserService
        from services.tier_service import TierService

        user_service = UserService()
        tier_service = TierService()

        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        user = user_service.get_user_by_id(user_id)

        # Get max limits from tier service
        max_text_regens = tier_service.get_text_regenerations(user.tier)
        max_thumb_regens = tier_service.get_thumbnail_regenerations(user.tier)

        # Get current usage (add these fields to your Video entity if missing)
        text_regens_used = getattr(video, "title_regenerations", 0)
        thumb_regens_used = getattr(video, "thumbnail_regenerations", 0)

        return (
            jsonify(
                {
                    "remaining": max(0, max_thumb_regens - thumb_regens_used),
                    "text_remaining": max(0, max_text_regens - text_regens_used),
                    "thumbnail_remaining": max(0, max_thumb_regens - thumb_regens_used),
                    "max_text": max_text_regens,
                    "max_thumbnail": max_thumb_regens,
                    "used_text": text_regens_used,
                    "used_thumbnail": thumb_regens_used,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get regenerations remaining: {e}")
        return jsonify({"error": str(e)}), 500


@router.route("/credits", methods=["GET"])
@jwt_required()
def get_credits():
    """Get current user's credit balance."""
    user_id = get_jwt_identity()

    try:
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        return (
            jsonify(
                {
                    "credits_remaining": user.credits_remaining,
                    "tier": user.tier.value,
                    "monthly_credits": tier_service.get_credits_per_month(user.tier),
                    "credits_used_this_month": getattr(
                        user, "credits_used_this_month", 0
                    ),
                    "videos_processed_this_month": user.videos_processed_this_month,
                    "monthly_video_limit": user.monthly_video_limit,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get credits: {str(e)}")
        return jsonify({"error": str(e)}), 500


@router.route("/export", methods=["POST"])
@jwt_required()
@validate_request(ExportSchema)
def export_videos():
    """Export video data."""
    user_id = get_jwt_identity()
    data = g.validated_data

    try:
        from providers.firebase_provider import FirebaseProvider

        db = FirebaseProvider()

        # Get user's videos
        videos = db.query("videos", filters={"user_id": user_id, "is_deleted": False})

        # Prepare export data
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
    words = transcription.split()
    segments = []

    for i in range(0, len(words), 10):
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

@router.route("/<video_id>/thumbnails/status", methods=["GET"])
@jwt_required()
def check_thumbnails_status(video_id):
    """Check if thumbnails are ready for serving."""
    user_id = get_jwt_identity()
    
    try:
        video = video_service.get_video(video_id, user_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        status = {
            "ai_thumbnails": [],
            "extracted_thumbnails": [],
            "ready": False
        }
        
        # Check each AI thumbnail
        for thumb in getattr(video, 'ai_thumbnails', []):
            thumb_path = thumb if isinstance(thumb, str) else thumb.get('path', '')
            exists = os.path.exists(thumb_path) if thumb_path else False
            status["ai_thumbnails"].append({
                "path": thumb_path,
                "exists": exists,
                "url": f"/api/v1/videos/thumbnails/{thumb_path}" if thumb_path else None
            })
        
        # Check extracted thumbnails
        for thumb in getattr(video, 'extracted_thumbnails', []):
            exists = os.path.exists(thumb) if thumb else False
            status["extracted_thumbnails"].append({
                "path": thumb,
                "exists": exists,
                "url": f"/api/v1/videos/thumbnails/{thumb}" if thumb else None
            })
        
        status["ready"] = all(t["exists"] for t in status["ai_thumbnails"]) if status["ai_thumbnails"] else True
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Failed to check thumbnails status: {e}")
        return jsonify({"error": str(e)}), 500