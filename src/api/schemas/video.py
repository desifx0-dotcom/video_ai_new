"""
Video schemas for request/response validation.
"""

from marshmallow import Schema, fields, validate, validates, ValidationError
from datetime import datetime
from typing import Optional, List


class VideoUploadSchema(Schema):
    """Video upload request schema."""

    title = fields.String(validate=validate.Length(max=255))
    description = fields.String(validate=validate.Length(max=5000))
    quality = fields.String(
        validate=validate.OneOf(["480p", "720p", "1080p", "4k", "4k+hdr"]),
        missing="720p",
    )
    styles = fields.List(
        fields.String(validate=validate.Length(max=50)),
        validate=validate.Length(max=5),
        missing=[],
    )
    translation_language = fields.String(validate=validate.Length(max=10), missing="")
    privacy = fields.String(
        validate=validate.OneOf(["private", "unlisted", "public"]), missing="private"
    )

    # 🔥 NEW FIELDS ADDED
    thumbnail_style = fields.String(
        validate=validate.OneOf(
            ["default", "cinematic", "bright", "dark", "text_heavy"]
        ),
        missing="default",
    )
    fps = fields.String(
        validate=validate.OneOf(["original", "24", "30", "60"]), missing="original"
    )
    audio_quality = fields.String(
        validate=validate.OneOf(["original", "128k", "192k", "256k", "320k"]),
        missing="original",
    )
    auto_transcribe = fields.Boolean(missing=True)
    generate_chapters = fields.Boolean(missing=False)
    remove_silence = fields.Boolean(missing=False)


class VideoUpdateSchema(Schema):
    """Video update request schema."""

    title = fields.String(validate=validate.Length(max=255))
    description = fields.String(validate=validate.Length(max=5000))
    tags = fields.List(fields.String(validate=validate.Length(max=50)))
    selected_thumbnail = fields.String(validate=validate.Length(max=500))
    privacy = fields.String(validate=validate.OneOf(["private", "unlisted", "public"]))


class VideoProcessSchema(Schema):
    """Video processing request schema."""

    styles = fields.List(
        fields.String(validate=validate.Length(max=50)),
        validate=validate.Length(max=5),
        missing=[],
    )
    quality = fields.String(
        validate=validate.OneOf(["480p", "720p", "1080p", "4k", "4k+hdr"]),
        missing="720p",
    )
    translation_language = fields.String(validate=validate.Length(max=10), missing="")
    regenerate_thumbnails = fields.Boolean(missing=False)
    regenerate_title = fields.Boolean(missing=False)

    # NEW FIELDS ADDED to process schema as well
    thumbnail_style = fields.String(
        validate=validate.OneOf(
            ["default", "cinematic", "bright", "dark", "text_heavy"]
        ),
        missing="default",
    )
    fps = fields.String(
        validate=validate.OneOf(["original", "24", "30", "60"]), missing="original"
    )
    audio_quality = fields.String(
        validate=validate.OneOf(["original", "128k", "192k", "256k", "320k"]),
        missing="original",
    )
    auto_transcribe = fields.Boolean(missing=True)
    generate_chapters = fields.Boolean(missing=False)
    remove_silence = fields.Boolean(missing=False)


class VideoResponseSchema(Schema):
    """Video response schema."""

    id = fields.String()
    user_id = fields.String()
    original_filename = fields.String()
    file_size = fields.Integer()
    duration = fields.Float()
    status = fields.String()
    video_type = fields.String()
    progress = fields.Float()

    # Results
    title = fields.String()
    description = fields.String()
    transcription = fields.String()
    transcription_language = fields.String()
    tags = fields.List(fields.String())

    # Thumbnails
    ai_thumbnails = fields.List(fields.String())
    extracted_thumbnails = fields.List(fields.String())
    selected_thumbnail = fields.String()

    # Output
    output_video_url = fields.String()
    output_video_size = fields.Integer()
    output_quality = fields.String()
    applied_styles = fields.List(fields.String())

    # Translation
    translated_transcription = fields.String()
    translation_language = fields.String()
    translated_title = fields.String()

    # NEW RESPONSE FIELDS
    thumbnail_style = fields.String()
    fps = fields.String()
    audio_quality = fields.String()
    auto_transcribe = fields.Boolean()
    generate_chapters = fields.Boolean()
    remove_silence = fields.Boolean()

    # Metadata
    processed_tier = fields.String()
    processing_time = fields.Float()
    total_cost = fields.Float()

    # Timestamps
    created_at = fields.DateTime()
    processing_started = fields.DateTime()
    processing_completed = fields.DateTime()
    scheduled_for_deletion = fields.DateTime()

    # Error handling
    error_message = fields.String()
    retry_count = fields.Integer()


class VideoListSchema(Schema):
    """Video list response schema."""

    videos = fields.List(fields.Nested(VideoResponseSchema))
    total = fields.Integer()
    page = fields.Integer()
    per_page = fields.Integer()
    total_pages = fields.Integer()


class ProcessingStatusSchema(Schema):
    """Processing status response schema."""

    video_id = fields.String()
    status = fields.String()
    progress = fields.Float()
    current_step = fields.String()
    estimated_time_remaining = fields.Float()
    error_message = fields.String()


class ThumbnailSchema(Schema):
    """Thumbnail schema."""

    url = fields.String()
    type = fields.String(validate=validate.OneOf(["ai", "extracted"]))
    selected = fields.Boolean()


class TranscriptionSchema(Schema):
    """Transcription schema."""

    text = fields.String()
    language = fields.String()
    segments = fields.List(fields.Dict())
    confidence = fields.Float()


class VideoAnalyticsSchema(Schema):
    """Video analytics schema."""

    video_id = fields.String()
    views = fields.Integer()
    processing_time = fields.Float()
    ai_costs = fields.Dict()
    user_feedback = fields.Dict()


class BatchProcessSchema(Schema):
    """Batch processing request schema."""

    video_ids = fields.List(
        fields.String(), required=True, validate=validate.Length(min=1, max=10)
    )
    options = fields.Dict()


class ExportSchema(Schema):
    """Export request schema."""

    format = fields.String(
        validate=validate.OneOf(["json", "csv", "srt", "vtt"]), missing="json"
    )
    include = fields.List(
        fields.String(
            validate=validate.OneOf(
                ["transcription", "metadata", "analytics", "thumbnails"]
            )
        )
    )
