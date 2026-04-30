"""
Admin endpoints for system management.
"""

import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from functools import wraps

from app.middleware.auth import admin_required
from core.exceptions import ValidationError
from services.user_service import UserService
from services.video_service import VideoService
from services.billing_service import BillingService
from services.tier_service import TierService
from providers.firebase_provider import FirebaseProvider
from tasks.cleanup_tasks import cleanup_expired_data

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

user_service = UserService()
video_service = VideoService()
billing_service = BillingService()
tier_service = TierService()

# Initialize database provider
if (
    os.getenv("FLASK_ENV") == "development"
    and os.getenv("DATABASE_PROVIDER") == "memory"
):
    db = None
    print("✅ Admin using mock Firebase")
else:
    try:
        db = FirebaseProvider()
        print("✅ Admin using Firebase")
    except Exception as e:
        print(f"⚠️ Admin Firebase init failed: {e}")
        db = None


def admin_required_decorator(f):
    """Decorator to ensure admin access."""

    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = get_jwt_identity()
        user = user_service.get_user_by_id(user_id)

        if not user or not getattr(user, "is_admin", False):
            return jsonify({"error": "Admin access required"}), 403

        return f(*args, **kwargs)

    return decorated_function


# Use the decorator from middleware if available, otherwise use our fallback
try:
    from app.middleware.auth import admin_required
except ImportError:
    admin_required = admin_required_decorator


@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    """Get admin dashboard statistics."""
    try:
        if not db:
            return (
                jsonify(
                    {
                        "error": "Database not available",
                        "message": "Admin dashboard requires database connection",
                    }
                ),
                503,
            )

        # Get user statistics
        total_users = db.count("users") if db else 0
        active_users = db.count("users", {"status": "active"}) if db else 0
        users_by_tier = {}

        for tier in ["free", "starter", "pro", "plus", "enterprise"]:
            users_by_tier[tier] = db.count("users", {"tier": tier}) if db else 0

        # Get video statistics
        total_videos = db.count("videos") if db else 0
        completed_videos = db.count("videos", {"status": "completed"}) if db else 0
        failed_videos = db.count("videos", {"status": "failed"}) if db else 0

        # Get processing statistics
        videos_by_tier = {}
        for tier in ["free", "starter", "pro", "plus"]:
            videos_by_tier[tier] = (
                db.count("videos", {"processed_tier": tier}) if db else 0
            )

        # Get revenue statistics (would come from Stripe)
        try:
            revenue_stats = (
                billing_service.get_revenue_stats() if billing_service else {"total": 0}
            )
        except:
            revenue_stats = {"total": 0}

        # Get system metrics
        try:
            from tasks.monitoring_tasks import check_system_health_task

            system_health = (
                check_system_health_task.apply().get(timeout=5)
                if check_system_health_task
                else {}
            )
        except:
            system_health = {"status": "unknown"}

        return (
            jsonify(
                {
                    "users": {
                        "total": total_users,
                        "active": active_users,
                        "by_tier": users_by_tier,
                    },
                    "videos": {
                        "total": total_videos,
                        "completed": completed_videos,
                        "failed": failed_videos,
                        "by_tier": videos_by_tier,
                    },
                    "revenue": revenue_stats,
                    "system_health": system_health,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Admin dashboard error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    """List all users with pagination."""
    try:
        if not db:
            return jsonify({"error": "Database not available"}), 503

        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        search = request.args.get("search", "")
        tier = request.args.get("tier")
        active_only = request.args.get("active_only", "true").lower() == "true"

        # Build filters
        filters = {}
        if tier:
            filters["tier"] = tier
        if active_only:
            filters["status"] = "active"

        # Get users with pagination
        try:
            users_data = db.query(
                "users",
                filters=filters,
                order_by="created_at",
                descending=True,
                limit=per_page,
                offset=(page - 1) * per_page,
            )
        except:
            users_data = []

        # Filter by search if provided
        if search and users_data:
            users_data = [
                user
                for user in users_data
                if search.lower() in user.get("email", "").lower()
                or search.lower() in user.get("id", "").lower()
            ]

        # Get total count
        total = db.count("users", filters) if db else 0

        return (
            jsonify(
                {
                    "users": users_data,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total,
                        "total_pages": (
                            (total + per_page - 1) // per_page if total > 0 else 1
                        ),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"List users error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>", methods=["GET"])
@admin_required
def get_user(user_id):
    """Get detailed user information."""
    try:
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Get user's videos
        videos = video_service.get_user_videos(user_id) if video_service else []
        recent_videos = videos[:10] if videos else []

        # Get user's subscription info
        try:
            subscription = (
                billing_service.get_user_subscription(user_id)
                if billing_service
                else None
            )
        except:
            subscription = None

        # Get user's credit transactions
        try:
            from services.credit_service import CreditService

            credit_service = CreditService()
            transactions = (
                credit_service.get_transaction_history(user_id, limit=20)
                if credit_service
                else []
            )
        except:
            transactions = []

        return (
            jsonify(
                {
                    "user": user.to_dict(),
                    "videos": {
                        "total": len(videos),
                        "recent": [
                            v.to_dict() if hasattr(v, "to_dict") else v
                            for v in recent_videos
                        ],
                    },
                    "subscription": (
                        subscription.to_dict()
                        if subscription and hasattr(subscription, "to_dict")
                        else None
                    ),
                    "credit_transactions": transactions[:20],
                    "statistics": {
                        "total_videos_processed": getattr(
                            user, "total_videos_processed", 0
                        ),
                        "total_processing_time": getattr(
                            user, "total_processing_time", 0
                        ),
                        "videos_this_month": getattr(
                            user, "videos_processed_this_month", 0
                        ),
                        "monthly_limit": getattr(user, "monthly_video_limit", 0),
                        "credits_remaining": getattr(user, "credits_remaining", 0),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Get user error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>", methods=["PUT"])
@admin_required
def update_user(user_id):
    """Update user information."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate update data
        allowed_fields = {
            "tier",
            "credits_remaining",
            "monthly_video_limit",
            "status",
            "is_admin",
            "settings",
            "full_name",
        }

        updates = {}
        for field, value in data.items():
            if field in allowed_fields:
                updates[field] = value

        if not updates:
            return jsonify({"error": "No valid fields to update"}), 400

        # Update user
        updated_user = user_service.update_user(user_id, updates)

        if not updated_user:
            return jsonify({"error": "User not found"}), 404

        # Log the admin action
        current_app.logger.info(
            f"Admin updated user {user_id}: {updates}",
            extra={
                "admin_action": "update_user",
                "user_id": user_id,
                "updates": updates,
            },
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "User updated successfully",
                    "user": updated_user.to_dict(),
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Update user error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>/impersonate", methods=["POST"])
@admin_required
def impersonate_user(user_id):
    """Generate a token to impersonate a user (for support)."""
    try:
        # Get the user
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Generate impersonation token
        from flask_jwt_extended import create_access_token

        impersonation_token = create_access_token(
            identity=user.id,
            additional_claims={
                "impersonated_by": get_jwt_identity(),
                "is_impersonation": True,
            },
            expires_delta=timedelta(hours=1),
        )

        # Log the impersonation
        current_app.logger.warning(
            f"Admin impersonating user {user_id}",
            extra={
                "admin_action": "impersonate",
                "admin_id": get_jwt_identity(),
                "user_id": user_id,
            },
        )

        return (
            jsonify(
                {
                    "token": impersonation_token,
                    "user": user.to_dict(),
                    "expires_in": 3600,
                    "warning": "This token should only be used for legitimate support purposes",
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Impersonate user error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/videos", methods=["GET"])
@admin_required
def list_videos():
    """List all videos with filtering."""
    try:
        if not db:
            return jsonify({"error": "Database not available"}), 503

        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        status = request.args.get("status")
        tier = request.args.get("tier")
        user_id = request.args.get("user_id")

        # Build filters
        filters = {}
        if status:
            filters["status"] = status
        if tier:
            filters["processed_tier"] = tier
        if user_id:
            filters["user_id"] = user_id

        # Get videos with pagination
        try:
            videos_data = db.query(
                "videos",
                filters=filters,
                order_by="created_at",
                descending=True,
                limit=per_page,
                offset=(page - 1) * per_page,
            )
        except:
            videos_data = []

        # Get total count
        total = db.count("videos", filters) if db else 0

        return (
            jsonify(
                {
                    "videos": videos_data,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total,
                        "total_pages": (
                            (total + per_page - 1) // per_page if total > 0 else 1
                        ),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"List videos error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/videos/<video_id>", methods=["GET"])
@admin_required
def get_video(video_id):
    """Get detailed video information."""
    try:
        if not db:
            return jsonify({"error": "Database not available"}), 503

        video_data = db.get("videos", video_id)
        if not video_data:
            return jsonify({"error": "Video not found"}), 404

        # Get user information
        user = user_service.get_user_by_id(video_data.get("user_id"))

        # Get processing job information
        try:
            jobs = db.query("processing_jobs", {"video_id": video_id})
        except:
            jobs = []

        return (
            jsonify(
                {
                    "video": video_data,
                    "user": user.to_dict() if user else None,
                    "processing_jobs": jobs,
                    "statistics": {
                        "processing_time": video_data.get("processing_time"),
                        "total_cost": video_data.get("total_cost", 0),
                        "ai_costs": video_data.get("ai_costs", {}),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Get video error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/videos/<video_id>/reprocess", methods=["POST"])
@admin_required
def reprocess_video(video_id):
    """Reprocess a video (admin override)."""
    try:
        if not db:
            return jsonify({"error": "Database not available"}), 503

        # Get video
        video_data = db.get("videos", video_id)
        if not video_data:
            return jsonify({"error": "Video not found"}), 404

        # Get user
        user = user_service.get_user_by_id(video_data.get("user_id"))
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Check if user has credits for reprocessing
        if user.tier not in ["plus", "enterprise"]:
            duration = video_data.get("duration", 0)
            credits_needed = max(1, int(duration) // 60)

            if getattr(user, "credits_remaining", 0) < credits_needed:
                # Admin override: add credits if needed
                user_service.add_credits(user.id, credits_needed)
                current_app.logger.info(
                    f"Added {credits_needed} credits to user {user.id} for reprocessing"
                )

        # Reprocess video
        from tasks.video_tasks import process_video_async

        process_video_async.delay(
            video_id,
            user.id,
            {
                "quality": video_data.get("output_quality", "720p"),
                "styles": video_data.get("applied_styles", []),
                "translation_language": video_data.get("translation_language"),
            },
        )

        # Log the admin action
        current_app.logger.info(
            f"Admin reprocessing video {video_id}",
            extra={
                "admin_action": "reprocess_video",
                "video_id": video_id,
                "user_id": user.id,
            },
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Video queued for reprocessing",
                    "video_id": video_id,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Reprocess video error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/system/cleanup", methods=["POST"])
@admin_required
def run_cleanup():
    """Run system cleanup tasks."""
    try:
        days = int(request.args.get("days", 30))

        # Run cleanup task synchronously for admin view
        from tasks.cleanup_tasks import cleanup_expired_data

        result = cleanup_expired_data(days)

        current_app.logger.info(f"Admin triggered cleanup: {result}")

        return (
            jsonify(
                {"status": "success", "message": "Cleanup completed", "result": result}
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Cleanup error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/system/maintenance", methods=["POST"])
@admin_required
def toggle_maintenance():
    """Toggle maintenance mode."""
    try:
        data = request.get_json()
        enabled = data.get("enabled", True)
        message = data.get("message", "System under maintenance")

        # Update maintenance mode in Redis
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()

        if enabled:
            redis.set(
                "maintenance_mode",
                {
                    "enabled": True,
                    "message": message,
                    "started_at": datetime.utcnow().isoformat(),
                    "started_by": get_jwt_identity(),
                },
            )
        else:
            redis.delete("maintenance_mode")

        # Log the action
        current_app.logger.warning(
            f"Maintenance mode {'enabled' if enabled else 'disabled'}",
            extra={
                "admin_action": "toggle_maintenance",
                "enabled": enabled,
                "message": message,
            },
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"Maintenance mode {'enabled' if enabled else 'disabled'}",
                    "maintenance_mode": enabled,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Toggle maintenance error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/system/config", methods=["GET"])
@admin_required
def get_config():
    """Get system configuration (non-sensitive)."""
    try:
        config = {
            "tiers": tier_service.get_all_tiers() if tier_service else [],
            "rate_limits": current_app.config.get("RATE_LIMITS", {}),
            "feature_flags": current_app.config.get("FEATURE_FLAGS", {}),
            "max_file_sizes": current_app.config.get("FILE_SIZE_LIMITS", {}),
            "video_duration_limits": current_app.config.get("DURATION_LIMITS", {}),
            "retention_periods": current_app.config.get("RETENTION_PERIODS", {}),
            "environment": current_app.config.get("ENV", "production"),
        }

        return jsonify(config), 200

    except Exception as e:
        current_app.logger.error(f"Get config error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/system/config/tiers", methods=["PUT"])
@admin_required
def update_tier_config():
    """Update tier configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate tier configuration
        required_fields = ["price_monthly", "videos_per_month", "max_video_length"]

        for tier_name, tier_config in data.items():
            if tier_name not in ["free", "starter", "pro", "plus", "enterprise"]:
                return jsonify({"error": f"Invalid tier: {tier_name}"}), 400

            for field in required_fields:
                if field not in tier_config:
                    return (
                        jsonify(
                            {"error": f"Missing field {field} for tier {tier_name}"}
                        ),
                        400,
                    )

        # Update tier configuration
        from core.config.settings import settings

        settings.set("tiers", data)

        # Log the action
        current_app.logger.info(
            f"Tier configuration updated",
            extra={"admin_action": "update_tier_config", "updates": data},
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Tier configuration updated",
                    "tiers": data,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Update tier config error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/analytics", methods=["GET"])
@admin_required
def get_analytics():
    """Get system analytics."""
    try:
        period = request.args.get("period", "day")  # day, week, month, year

        # Get analytics data
        analytics = {
            "users": get_user_analytics(period),
            "videos": get_video_analytics(period),
            "revenue": get_revenue_analytics(period),
            "system": get_system_analytics(period),
        }

        return jsonify(analytics), 200

    except Exception as e:
        current_app.logger.error(f"Get analytics error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def get_user_analytics(period):
    """Get user analytics for period."""
    try:
        from datetime import datetime, timedelta

        end_date = datetime.utcnow()

        if period == "day":
            start_date = end_date - timedelta(days=1)
        elif period == "week":
            start_date = end_date - timedelta(weeks=1)
        elif period == "month":
            start_date = end_date - timedelta(days=30)
        elif period == "year":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=7)

        if not db:
            return {
                "total": 0,
                "by_tier": {},
                "period": period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

        # Query users created in period
        users = (
            db.query(
                "users",
                filters={
                    "created_at": {
                        ">=": start_date.isoformat(),
                        "<=": end_date.isoformat(),
                    }
                },
            )
            or []
        )

        # Calculate metrics
        total = len(users)
        by_tier = {}
        for user in users:
            tier = user.get("tier", "free")
            by_tier[tier] = by_tier.get(tier, 0) + 1

        return {
            "total": total,
            "by_tier": by_tier,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    except Exception as e:
        current_app.logger.error(f"Get user analytics error: {e}", exc_info=True)
        return {"total": 0, "by_tier": {}, "period": period, "error": str(e)}


def get_video_analytics(period):
    """Get video analytics for period."""
    try:
        from datetime import datetime, timedelta

        end_date = datetime.utcnow()

        if period == "day":
            start_date = end_date - timedelta(days=1)
        elif period == "week":
            start_date = end_date - timedelta(weeks=1)
        elif period == "month":
            start_date = end_date - timedelta(days=30)
        elif period == "year":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=7)

        if not db:
            return {
                "total": 0,
                "total_cost": 0,
                "average_processing_time": 0,
                "by_tier": {},
                "by_type": {},
                "period": period,
            }

        # Query videos processed in period
        videos = (
            db.query(
                "videos",
                filters={
                    "processing_completed": {
                        ">=": start_date.isoformat(),
                        "<=": end_date.isoformat(),
                    },
                    "status": "completed",
                },
            )
            or []
        )

        # Calculate metrics
        total = len(videos)
        total_cost = sum(v.get("total_cost", 0) for v in videos)
        avg_processing_time = (
            sum(v.get("processing_time", 0) for v in videos) / total if total > 0 else 0
        )

        by_tier = {}
        by_type = {}

        for video in videos:
            tier = video.get("processed_tier", "free")
            video_type = video.get("video_type", "unknown")

            by_tier[tier] = by_tier.get(tier, 0) + 1
            by_type[video_type] = by_type.get(video_type, 0) + 1

        return {
            "total": total,
            "total_cost": total_cost,
            "average_processing_time": avg_processing_time,
            "by_tier": by_tier,
            "by_type": by_type,
            "period": period,
        }

    except Exception as e:
        current_app.logger.error(f"Get video analytics error: {e}", exc_info=True)
        return {
            "total": 0,
            "total_cost": 0,
            "average_processing_time": 0,
            "by_tier": {},
            "by_type": {},
            "period": period,
            "error": str(e),
        }


def get_revenue_analytics(period):
    """Get revenue analytics for period."""
    try:
        # This would typically query Stripe or billing database
        # For now, return mock data with proper structure
        return {
            "total_revenue": 0,
            "recurring_revenue": 0,
            "one_time_revenue": 0,
            "by_tier": {},
            "period": period,
            "message": "Revenue analytics will be available after Stripe integration",
        }

    except Exception as e:
        current_app.logger.error(f"Get revenue analytics error: {e}", exc_info=True)
        return {
            "total_revenue": 0,
            "recurring_revenue": 0,
            "one_time_revenue": 0,
            "by_tier": {},
            "period": period,
            "error": str(e),
        }


def get_system_analytics(period):
    """Get system performance analytics."""
    try:
        from providers.redis_provider import RedisProvider

        redis = RedisProvider()

        # Get system metrics from Redis
        system_health = {}
        business_metrics = {}

        try:
            system_health = redis.get("system_health") or {}
            business_metrics = redis.get("business_metrics_24h") or {}
        except:
            pass

        return {
            "system_health": system_health,
            "business_metrics": business_metrics,
            "period": period,
        }

    except Exception as e:
        current_app.logger.error(f"Get system analytics error: {e}", exc_info=True)
        return {
            "system_health": {},
            "business_metrics": {},
            "period": period,
            "error": str(e),
        }


@admin_bp.route("/logs", methods=["GET"])
@admin_required
def get_logs():
    """Get system logs."""
    try:
        lines = int(request.args.get("lines", 100))
        level = request.args.get("level", "INFO")
        search = request.args.get("search", "")

        # Read log file
        log_file = "logs/video_ai_studio.log"
        logs = []

        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                # Read last N lines efficiently
                total_lines_wanted = lines

                BLOCK_SIZE = 1024
                f.seek(0, 2)  # Seek to end
                block_end_byte = f.tell()
                lines_to_go = total_lines_wanted
                block_number = -1

                while lines_to_go > 0 and block_end_byte > 0:
                    if block_end_byte - BLOCK_SIZE > 0:
                        f.seek(block_number * BLOCK_SIZE, 2)
                        lines_found = f.read(BLOCK_SIZE).count("\n")
                    else:
                        f.seek(0)
                        lines_found = f.read(block_end_byte).count("\n")

                    lines_to_go -= lines_found
                    block_end_byte -= BLOCK_SIZE
                    block_number -= 1

                f.seek(block_end_byte)

                # Read and filter logs
                for line in f:
                    # Filter by level
                    if level and level not in line:
                        continue

                    # Filter by search
                    if search and search.lower() not in line.lower():
                        continue

                    logs.append(line.strip())

        return (
            jsonify(
                {
                    "logs": logs[-lines:],  # Return requested number of lines
                    "total": len(logs),
                    "level": level,
                    "search": search,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Get logs error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/health", methods=["GET"])
def health_check():
    """Simple health check (no auth required)."""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "video-ai-studio",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ),
        200,
    )
