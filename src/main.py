"""
Main application entry point with comprehensive setup.
"""

from patch_async import ASYNC_MODE
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import List, Dict, Any
from functools import wraps
import redis
import json
import uuid
import tempfile
import threading

# Adding the src directory to Python path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from flask import Flask, render_template, jsonify, request, flash
from flask_cors import CORS
from flask_socketio import SocketIO
from api.websocket import set_socketio_instance
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from app.config import Config
from app.extensions import init_extensions, jwt, limiter, celery
from app.middleware import register_middleware
from app.monitoring import init_monitoring
from api.v1.__main__ import register_api_routes
from api.websocket import register_websocket_handlers
from core.logging import setup_logging, logger
from core.exceptions import handle_exception
from core.websocket_manager import init_websocket, get_ws_manager

if os.path.exists(".env"):
    load_dotenv(".env")
else:
    load_dotenv()


def timeago_filter(date):
    """Convert datetime to human readable 'time ago' format."""
    if not date:
        return "Unknown"

    now = datetime.utcnow()

    # Handle both datetime objects and ISO strings
    if isinstance(date, str):
        try:
            date = datetime.fromisoformat(date.replace("Z", "+00:00"))
        except:
            return "Invalid date"

    diff = now - date

    seconds = diff.total_seconds()

    if seconds < 10:
        return "just now"
    elif seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif seconds < 604800:  # 7 days
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"
    elif seconds < 2592000:  # 30 days
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif seconds < 31536000:  # 365 days
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = int(seconds / 31536000)
        return f"{years} year{'s' if years > 1 else ''} ago"

def start_redis_listener(socketio):
    """Start Redis listener to forward messages to WebSocket clients."""
    
    redis_url = os.getenv('SOCKETIO_MESSAGE_QUEUE') or os.getenv('REDIS_URL')
    if not redis_url:
        logger.warning("⚠️ No REDIS_URL found, Redis listener disabled")
        return
    
    def listener_loop():
        try:
            import redis
            import json
            import time
            
            #Pre-resolve the hostname to IP
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            hostname = parsed.hostname
            
            # If it's a hostname (not IP), resolve it
            if hostname and not hostname.replace('.', '').isdigit():
                import socket
                try:
                    ip = socket.gethostbyname(hostname)
                    # Replace hostname with IP in the URL
                    redis_url_fixed = redis_url.replace(hostname, ip)
                    logger.info(f"✅ Resolved {hostname} -> {ip}")
                    redis_url = redis_url_fixed
                except Exception as e:
                    logger.warning(f"⚠️ DNS resolution failed: {e}, using original URL")
            
            # Connect with shorter timeout
            r = redis.from_url(
                redis_url, 
                decode_responses=True, 
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=False
            )
            
            # Test connection
            r.ping()
            logger.info("✅ Redis connected successfully")
            
            pubsub = r.pubsub()
            pubsub.subscribe('video_updates')
            logger.info("✅ Redis listener started for 'video_updates' channel")
            
            for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        video_id = data.get('video_id')
                        
                        if video_id:
                            # Forward to all clients in the video room
                            room = f"video:{video_id}"
                            socketio.emit('video_processing', data, room=room)
                            logger.debug(f"📤 Forwarded from Redis: {video_id}")
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Redis listener failed: {e}")
    
    # Start listener in background thread
    try:
        thread = threading.Thread(target=listener_loop, daemon=True)
        thread.start()
        logger.info("✅ Redis listener thread started")
        return thread
    except Exception as e:
        logger.error(f"❌ Failed to start Redis listener: {e}")
        return None

def create_app(config_class=Config):
    """Application factory function - PRODUCTION OPTIMIZED ORDER."""

    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logging(level=log_level)

    logger.info("🚀 Starting Video AI Studio application...")

    # ========== 1. CREATE FLASK APP FIRST ==========
    app = Flask(__name__, static_folder="../static", template_folder="../templates")

    # ========== 2. LOAD CONFIGURATION ==========
    app.config.from_object(config_class)
    config_class.init_app(app)

    # ========== 3. SESSION & JWT CONFIGURATION ==========
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-key-change-in-production"),
        SESSION_COOKIE_NAME="video_ai_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,  #set True in production with HTTps
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        SESSION_REFRESH_EACH_REQUEST=True,
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY")),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=1),
        JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=30),
        JWT_TOKEN_LOCATION=["headers"],
        JWT_HEADER_NAME="Authorization",
        JWT_HEADER_TYPE="Bearer",
        WTF_CSRF_CHECK_DEFAULT=False,
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=3600,
        # Large file upload settings
        MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,
        UPLOAD_FOLDER=tempfile.gettempdir(),
        MAX_FORM_MEMORY_SIZE=500 * 1024,
        MAX_FORM_PARTS=1000,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )

    # ========== 4. INITIALIZE REDIS (for rate limiting & caching) ==========
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis_client = None
    try:
        redis_client = redis.from_url(redis_url)
        redis_client.ping()
        app.config["REDIS_CLIENT"] = redis_client
        logger.info("✅ Redis connected successfully")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed: {e}. Some features will be limited.")

    # ========== 5. INITIALIZE JWT ==========
    jwt = JWTManager(app)
    logger.info("✅ JWT Manager initialized")

    # ========== 6. INITIALIZE CSRF PROTECTION ==========
    csrf = CSRFProtect()
    csrf.init_app(app)

    logger.info("✅ CSRF protection initialized")

    # ========== 7. INITIALIZE CORS ==========
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config.get("CORS_ORIGINS", ["*"]),
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
                "allow_headers": [
                    "Content-Type", "Authorization", "X-Requested-With",
                    "Accept", "Origin", "X-CSRF-Token",
                ],
                "expose_headers": [
                    "Content-Range", "X-Content-Range",
                    "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset",
                ],
                "supports_credentials": True,
                "max_age": 600,
            },
            r"/socket.io/*": {
                "origins": app.config.get("CORS_ORIGINS", ["*"]),
                "methods": ["GET", "POST"],
                "allow_headers": ["Authorization"],
                "credentials": True,
            },
        },
    )
    logger.info("✅ CORS configured")

    # ========== 8. INITIALIZE RATE LIMITER ==========
    try:
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["2000 per day", "500 per hour"],
            storage_uri=redis_url if redis_client else "memory://",
            strategy="fixed-window",
        )
        logger.info("✅ Rate limiter initialized")
    except TypeError as e:
        logger.warning(f"Rate limiter fallback: {e}")
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri=redis_url if redis_client else "memory://",
        )

    # ========== 9. INITIALIZE SOCKETIO ==========
    # Initialize WebSocket Manager
    socketio = init_websocket(app)  # ← This creates socketio
    logger.info("✅ WebSocket Manager initialized")

    # START REDIS LISTENER FOR CELERY COMMUNICATION
    # start_redis_listener(socketio)

    # Set global instance BEFORE registering handlers
    from api.websocket import set_socketio_instance, register_websocket_handlers
    set_socketio_instance(socketio)
    logger.info("✅ SocketIO instance set globally")
    
    # Register WebSocket handlers
    register_websocket_handlers(socketio)
    logger.info("✅ WebSocket handlers registered")

    # ========== 10. INITIALIZE MONITORING & EXTENSIONS ==========
    init_monitoring(app)
    init_extensions(app)
    register_middleware(app)
    logger.info("✅ Monitoring and extensions initialized")

    # ========== 11. REGISTER API ROUTES (AFTER SocketIO) ==========
    register_api_routes(app)
    logger.info("✅ API routes registered")

    # ========== 12. REGISTER TEMPLATE FILTERS & CONTEXT PROCESSORS ==========

    # Make csrf_token available to all templates
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=lambda: generate_csrf())

    @app.template_filter("format_duration")
    def format_duration(seconds):
        """Format duration in seconds to MM:SS format."""
        if not seconds:
            return "00:00"
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes:02d}:{remaining_seconds:02d}"

    @app.template_filter("datetimeformat")
    def datetimeformat(value, format="%Y-%m-%d %H:%M:%S"):
        """Format datetime for templates."""
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                from datetime import datetime
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except:
                return value
        return value.strftime(format)

    @app.template_filter("currency")
    def currency_format(value):
        """Format currency."""
        if value is None:
            return "$0.00"
        return f"${value:,.2f}"

    #  User context processor (adds current_user to all templates)
    def inject_user():
        """Make current_user available to all templates."""
        from flask import session
        from services.user_service import UserService

        user_id = session.get("user_id")
        user = None

        if user_id:
            try:
                user_service = UserService()
                user = user_service.get_user_by_id(user_id)
            except Exception as e:
                logger.error(f"Failed to load user from session: {e}")

        # Also try JWT token if session doesn't work
        if not user:
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id:
                    user_service = UserService()
                    user = user_service.get_user_by_id(user_id)
            except Exception:
                pass

        return {"current_user": user}

    # Register user context processor
    app.context_processor(inject_user)
    logger.info("✅ User context processor registered")

    # Register template filters
    app.jinja_env.filters["timeago"] = timeago_filter
    app.jinja_env.filters["datetimeformat"] = datetimeformat
    app.jinja_env.filters["currency"] = currency_format
    app.jinja_env.filters["format_duration"] = format_duration

    # ========== 13. REGISTER PAGE ROUTES (HTML pages) ==========

    # Register CLI commands
    from app.cli import register_cli_commands

    register_cli_commands(app)

    # In main.py, after socketio initialization
    import threading
    from providers.redis_provider import RedisProvider

    def process_redis_notifications():
        """Background thread to process notifications from Redis."""
        from providers.redis_provider import RedisProvider
        import time
        import json

        redis = RedisProvider()
        logger.info("✅ Redis notification processor started for ws_notify:* keys")

        while True:
            try:
                # Check if Redis client is available
                if not hasattr(redis, "_client") or redis._client is None:
                    logger.warning("⚠️ Redis client not available, waiting...")
                    time.sleep(5)
                    continue

                redis_client = redis._client
                
                # Get keys for pending notifications
                keys = redis_client.keys("ws_notify:*")
                
                # If no keys, just sleep and continue (no error)
                if not keys:
                    time.sleep(1)
                    continue

                for key in keys:
                    # Handle both bytes and string keys
                    if isinstance(key, bytes):
                        key_str = key.decode()
                    else:
                        key_str = key
                    
                    user_id = key_str.split(":")[-1]
                    notifications = redis_client.lrange(key, 0, -1)

                    for notif in notifications:
                        if isinstance(notif, bytes):
                            notif = notif.decode()
                        try:
                            data = json.loads(notif)
                            
                            # Emit to the user's room
                            if socketio:
                                socketio.emit(
                                    "notification",
                                    data,
                                    room=user_id,
                                )
                                logger.debug(f"📤 Emitted notification to user {user_id}")
                            else:
                                logger.debug(f"⚠️ SocketIO not available for notification")
                        except json.JSONDecodeError as e:
                            logger.debug(f"Invalid JSON in notification: {e}")

                    # Clear the key after processing
                    redis_client.delete(key)

                time.sleep(1)  # Don't hammer Redis

            except Exception as e:
                logger.debug(f"Redis notification processor: {e}")
                time.sleep(5)  # Wait before retry


    def _send_websocket_notification(self, user_id, notification_type, data):
        """Send WebSocket notification."""
        try:
            socketio = self.get_socketio()

            # Check if we're in a Celery worker
            if os.environ.get("CELERY_WORKER", "false").lower() == "true":
                # Store in Redis instead of sending directly
                from providers.redis_provider import RedisProvider

                redis = RedisProvider()

                if hasattr(redis, "_client"):
                    redis._client.lpush(
                        f"ws_notify:{user_id}",
                        json.dumps(
                            {
                                "type": notification_type.value,
                                "data": data,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        ),
                    )
                    redis._client.expire(f"ws_notify:{user_id}", 60)

                return {"status": "stored", "channel": "redis"}

            # Emit to user's room
            socketio.emit(
                "notification",
                {
                    "type": notification_type.value,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=user_id,
            )

            return {"status": "sent", "channel": "websocket"}

        except Exception as e:
            logger.error(f"WebSocket notification failed: {e}")
            return {"status": "error", "error": str(e)}

    # Start background thread (only in Flask server, not in Celery worker)
    if not os.environ.get("CELERY_WORKER", "false").lower() == "true":
        # Check if already running to prevent duplicates
        import threading
        for thread in threading.enumerate():
            if thread.name == "RedisNotificationProcessor":
                logger.info("ℹ️ Redis notification processor already running")
                break
        else:
            thread = threading.Thread(
                target=process_redis_notifications, 
                daemon=True,
                name="RedisNotificationProcessor"  # Give it a name to track
            )
            thread.start()
            logger.info("✅ Redis notification processor thread started")
            
    from api.v1 import api_v1_bp
    from api.v1.routers.auth_public import public_auth_bp

    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
    from api.v1.routers.refresh import refresh_bp
    app.register_blueprint(refresh_bp, url_prefix="/api/v1/auth")
    logger.info("✅ Registered refresh blueprint")

    # ===== IMPORTANT: Exempt ALL API routes from CSRF protection =====
    # Since we're using JWT tokens for API authentication, CSRF is not needed
    # This will fix upload issue while maintaining security
    csrf.exempt(api_v1_bp)
    logger.info("✅ Exempted all API routes from CSRF protection")

    logger.info("✅ Registered API v1 blueprint at /api/v1")
    
    # Health check endpoint
    @app.route("/health")
    def health_check():
        """Comprehensive health check."""
        from providers.redis_provider import RedisProvider
        from providers.firebase_provider import FirebaseProvider

        health_status = {
            "status": "healthy",
            "service": "video-ai-studio",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
        }

        # Check Redis connection
        try:
            redis = RedisProvider()
            redis.ping()
            health_status["checks"]["redis"] = {"status": "healthy", "latency": "ok"}
        except Exception as e:
            health_status["checks"]["redis"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"

        # Check database connection
        try:
            db = FirebaseProvider()
            db.ping()
            # Simple query to test connection
            db.get("health_check", "test", raise_not_found=False)
            health_status["checks"]["database"] = {"status": "healthy"}
        except Exception as e:
            health_status["checks"]["database"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            health_status["status"] = "degraded"

        # Check Celery worker status
        try:
            from tasks.celery_app import celery

            i = celery.control.inspect()
            active_workers = i.active() or {}
            health_status["checks"]["celery"] = {
                "status": "healthy",
                "workers": len(active_workers),
                "active_tasks": sum(len(tasks) for tasks in active_workers.values()),
            }
        except Exception as e:
            health_status["checks"]["celery"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"

        # Check storage directory
        try:
            upload_dir = Path(app.config["UPLOAD_FOLDER"])
            if upload_dir.exists() and os.access(upload_dir, os.W_OK):
                health_status["checks"]["storage"] = {
                    "status": "healthy",
                    "writable": True,
                }
            else:
                health_status["checks"]["storage"] = {
                    "status": "unhealthy",
                    "writable": False,
                }
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["checks"]["storage"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            health_status["status"] = "degraded"

        # Add system metrics
        import psutil

        health_status["system"] = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage("/").percent,
        }

        return jsonify(health_status)

    @app.route("/auth/login", methods=["GET", "POST"])
    def login_page():
        """Login page."""
        from flask import session, redirect, url_for, request, jsonify, render_template
        from services.user_service import UserService
        from services.video_service import VideoService
        import secrets
        import logging

        logger = logging.getLogger(__name__)

        # Generate CSRF token for the form
        if request.method == "GET" and "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)

        # If already logged in, check if user actually exists
        if session.get("user_id"):
            try:
                user_service = UserService()
                user = user_service.get_user_by_id(session["user_id"])
                if user:
                    logger.info(
                        f"Already logged in user {session['user_id']} tried to access login page"
                    )
                    return redirect(url_for("dashboard"))
                else:
                    # User doesn't exist in database, clear session
                    logger.warning(
                        f"User {session['user_id']} not found in database, clearing session"
                    )
                    session.clear()
            except Exception as e:
                logger.error(f"Error checking user session: {e}")
                session.clear()

        # Get sidebar counts (0 for non-logged-in users)
        video_service = VideoService()
        unprocessed_videos_count = 0
        processing_count = 0

        if request.method == "POST":
            try:
                email = request.form.get("email", "").strip()
                password = request.form.get("password", "")
                remember = request.form.get("remember") == "on"

                logger.info(f"Login attempt for: {email}")

                # Validate input
                if not email or not password:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": "Email and password are required",
                            }
                        ),
                        400,
                    )

                user_service = UserService()
                user = user_service.authenticate_user(email, password)

                if user:
                    # Clear any existing session
                    # session.clear()

                    # Set session (still useful for template rendering)
                    session["user_id"] = user.id
                    session["user_email"] = user.email
                    session["user_tier"] = getattr(user, "tier", "free")

                    # Set session permanence
                    session.permanent = remember
                    if remember:
                        app.permanent_session_lifetime = timedelta(days=30)

                    session.modified = True

                    # 🔥 Create JWT tokens for API authentication
                    tier_value = (
                        user.tier.value if hasattr(user.tier, "value") else user.tier
                    )

                    access_token = create_access_token(
                        identity=user.id,
                        expires_delta=timedelta(hours=1),
                        additional_claims={
                            "email": user.email,
                            "tier": tier_value,
                        },
                    )

                    refresh_token = create_refresh_token(
                        identity=user.id, expires_delta=timedelta(days=30)
                    )

                    print(f"✅ Stored tokens in session for user {user.id}")

                    session["access_token"] = access_token
                    session["refresh_token"] = refresh_token

                    logger.info(f"✅ Login successful for: {email}")

                    # Return both session data AND JWT tokens
                    return jsonify(
                        {
                            "success": True,
                            "message": "Login successful",
                            "redirect": url_for("dashboard"),
                            "access_token": access_token,
                            "refresh_token": refresh_token,
                            "user": {
                                "id": user.id,
                                "email": user.email,
                                "tier": tier_value,
                            },
                        }
                    )
                else:
                    logger.warning(f"❌ Login failed for: {email}")
                    return (
                        jsonify(
                            {"success": False, "message": "Invalid email or password"}
                        ),
                        401,
                    )

            except Exception as e:
                logger.error(f"Login error: {str(e)}", exc_info=True)
                return (
                    jsonify(
                        {"success": False, "message": "An error occurred during login"}
                    ),
                    500,
                )

        # GET request - show login page
        return render_template(
            "auth/login.html",
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,
            form_csrf_token=session.get("csrf_token", ""),
        )

    @app.route("/auth/set-session", methods=["POST"])
    def set_session():
        """Set session from API login."""
        from flask import session, request, jsonify

        data = request.get_json()

        if not data or not data.get("user_id"):
            return jsonify({"success": False, "error": "Missing user_id"}), 400

        session["user_id"] = data.get("user_id")
        session["user_email"] = data.get("email")
        session["user_tier"] = data.get("tier", "free")
        session.permanent = True

        print(f"Session set for user: {data.get('user_id')}")

        return jsonify({"success": True})

    @app.route("/api/ws-status")
    def ws_status():
        """Check WebSocket server status."""
        from api.websocket import get_socketio
        socketio = get_socketio()
        return jsonify({
            "websocket_initialized": socketio is not None,
            "status": "ready" if socketio else "not_initialized"
        })

    @app.route("/api/v1/auth/session-check", methods=["GET"])
    def session_check():
        """Check if user has an active session."""
        from flask import session, jsonify

        user_id = session.get("user_id")
        return jsonify({"authenticated": user_id is not None, "user_id": user_id})

    @app.route("/debug-session")
    def debug_session():
        """Debug endpoint to check session."""
        from flask import session, jsonify

        return jsonify(
            {
                "session": dict(session),
                "has_user_id": "user_id" in session,
                "user_id": session.get("user_id"),
                "cookies": dict(request.cookies),
            }
        )

    @app.route("/api/v1/auth/refresh-session", methods=["POST"])
    def refresh_session():
        """Get new JWT tokens using session cookie."""
        from flask import session, jsonify
        from services.user_service import UserService
        from flask_jwt_extended import create_access_token, create_refresh_token

        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "No active session"}), 401

        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        tier_value = user.tier.value if hasattr(user.tier, "value") else user.tier

        access_token = create_access_token(
            identity=user.id,
            additional_claims={
                "email": user.email,
                "tier": tier_value,
            },
        )

        refresh_token = create_refresh_token(identity=user.id)

        return jsonify({"access_token": access_token, "refresh_token": refresh_token})

    @app.route("/auth/logout", methods=["POST"])
    def logout():
        """Logout user and clear session."""
        from flask import session, jsonify, url_for

        # Log the logout attempt
        print(f"Logout request received, session before clear: {dict(session)}")

        # Clear the session completely
        session.clear()

        # Return success - the frontend will handle redirect
        return jsonify(
            {
                "success": True,
                "message": "Logged out successfully",
                "redirect": url_for("index"),
            }
        )

    @app.route("/auth/register", methods=["GET", "POST"])
    def register_page():
        """Registration page."""
        from flask import session, redirect, url_for, request, jsonify, render_template
        from services.user_service import UserService
        from services.video_service import VideoService
        from datetime import timedelta
        import logging

        logger = logging.getLogger(__name__)

        # If already logged in, redirect to dashboard
        if session.get("user_id"):
            logger.info(
                f"Already logged in user {session['user_id']} tried to access register page"
            )
            return redirect(url_for("dashboard"))

        # Get sidebar counts (0 for non-logged-in users)
        video_service = VideoService()
        unprocessed_videos_count = 0
        processing_count = 0

        if request.method == "POST":
            try:
                # Validate input
                email = request.form.get("email", "").strip()
                password = request.form.get("password", "")
                name = request.form.get("name", "User").strip()

                if not email or not password:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": "Email and password are required",
                            }
                        ),
                        400,
                    )

                if len(password) < 8:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": "Password must be at least 8 characters",
                            }
                        ),
                        400,
                    )

                user_service = UserService()

                # Check if user already exists
                existing_user = user_service.get_user_by_email(email)
                if existing_user:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": "User with this email already exists",
                            }
                        ),
                        400,
                    )

                # Create user
                user = user_service.create_user(
                    email=email,
                    password=password,
                    full_name=name,
                    tier="free",
                    credits_remaining=10,
                )

                if user:
                    # Set session
                    session.clear()
                    session["user_id"] = user.id
                    session["user_email"] = user.email
                    session.permanent = False
                    session.modified = True

                    # 🔥 Create JWT tokens for API authentication
                    tier_value = (
                        user.tier.value if hasattr(user.tier, "value") else user.tier
                    )

                    access_token = create_access_token(
                        identity=user.id,
                        expires_delta=timedelta(hours=1),
                        additional_claims={
                            "email": user.email,
                            "tier": tier_value,
                        },
                    )

                    refresh_token = create_refresh_token(
                        identity=user.id, expires_delta=timedelta(days=30)
                    )

                    logger.info(f"✅ New user registered: {email}")

                    return jsonify(
                        {
                            "success": True,
                            "message": "Registration successful",
                            "redirect": url_for("dashboard"),
                            "access_token": access_token,
                            "refresh_token": refresh_token,
                            "user": {
                                "id": user.id,
                                "email": user.email,
                                "tier": tier_value,
                            },
                        }
                    )
                else:
                    logger.error(f"User creation failed for {email}")
                    return (
                        jsonify({"success": False, "message": "Registration failed"}),
                        500,
                    )

            except Exception as e:
                logger.error(f"Registration error: {str(e)}", exc_info=True)
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "An error occurred during registration",
                        }
                    ),
                    500,
                )

        # GET request - show register page
        return render_template(
            "auth/register.html",
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,
            form_csrf_token=session.get("csrf_token", ""),
        )

    @app.route("/auth/forgot-password", methods=["GET", "POST"])
    def forgot_password_page():
        """Forgot password page."""

        from flask import session, request, jsonify, render_template, redirect, url_for
        from services.user_service import UserService
        from services.video_service import VideoService
        import logging

        logger = logging.getLogger(__name__)

        # If already logged in, redirect to dashboard
        if session.get("user_id"):
            return redirect(url_for("dashboard"))

        # Get sidebar counts (0 for non-logged-in users)
        video_service = VideoService()
        unprocessed_videos_count = 0
        processing_count = 0

        if request.method == "POST":
            try:
                email = request.form.get("email", "").strip()

                if not email:
                    return (
                        jsonify({"success": False, "message": "Email is required"}),
                        400,
                    )

                # Always return success for security (don't reveal if email exists)
                user_service = UserService()
                user = user_service.get_user_by_email(email)

                if user:
                    # Generate reset token and send email
                    # This should be implemented in your UserService
                    # user_service.send_password_reset_email(email)
                    logger.info(f"Password reset requested for: {email}")

                return jsonify(
                    {
                        "success": True,
                        "message": "If an account exists with this email, a password reset link has been sent",
                    }
                )

            except Exception as e:
                logger.error(f"Password reset error: {str(e)}")
                return jsonify({"success": False, "message": "An error occurred"}), 500

        return render_template(
            "auth/forgot_password.html",
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,
        )

    # Metrics endpoint for Prometheus
    @app.route("/metrics")
    def metrics():
        """Prometheus metrics endpoint."""
        from app.monitoring.metrics import generate_latest

        return generate_latest(), 200, {"Content-Type": "text/plain"}

    @app.route("/debug/add-credits")
    def add_credits_debug():
        """Temporary route to add credits to your user."""
        from flask import session, jsonify
        from services.user_service import UserService

        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Add 10 credits
        success = user_service.add_credits(user_id, 10, "Debug credits")

        if success:
            # Get updated user
            updated_user = user_service.get_user_by_id(user_id)
            return jsonify(
                {
                    "success": True,
                    "message": f"Added 10 credits to {user.email}",
                    "credits_remaining": updated_user.credits_remaining,
                }
            )
        else:
            return jsonify({"error": "Failed to add credits"}), 500

    # Status endpoint
    @app.route("/status")
    def status_page():
        """Status page for monitoring."""
        return render_template("status.html")

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        error_details = None
        if app.config.get("DEBUG", False):
            import traceback

            error_details = traceback.format_exc()
        return render_template("errors/500.html", error_details=error_details), 500

    # Main landing page
    @app.route("/")
    def index():
        """Main landing page."""
        from flask import session, redirect, url_for, render_template
        from services.user_service import UserService
        from services.video_service import VideoService
        import logging

        logger = logging.getLogger(__name__)

        # If user is logged in, verify user exists before redirecting
        if session.get("user_id"):
            try:
                user_service = UserService()
                user = user_service.get_user_by_id(session["user_id"])
                if user:
                    logger.info(
                        f"Logged in user {session['user_id']} redirected to dashboard"
                    )
                    return redirect(url_for("dashboard"))
                else:
                    # User doesn't exist, clear session
                    session.clear()
            except Exception as e:
                logger.error(f"Error checking user: {e}")
                session.clear()

        # Get sidebar counts (0 for non-logged-in users)
        video_service = VideoService()
        unprocessed_videos_count = 0
        processing_count = 0

        return render_template(
            "index.html",
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,
        )

    @app.route("/dashboard")
    def dashboard():
        """User dashboard."""
        from flask import session
        from services.user_service import UserService
        from services.video_service import VideoService
        from datetime import datetime
        from flask import redirect, url_for

        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login_page"))

        user_service = UserService()
        video_service = VideoService()

        try:
            user = user_service.get_user_by_id(user_id)

            if not user:
                print(f"❌ User not found in database: {user_id}")
                session.clear()  # Clear invalid session
                return redirect(url_for("login_page"))

            print(f"✅ User authenticated: {user.email}")

            # Get recent videos and counts
            recent_videos = video_service.get_recent_videos(user_id, limit=10)

            # Get unprocessed videos count for sidebar badge
            unprocessed_videos_count = video_service.get_unprocessed_count(user_id)
            processing_count = video_service.get_processing_count(user_id)

            # Get user's video processing stats
            videos_processed = getattr(user, "videos_processed_this_month", 0)

            # Get monthly limit based on user's tier
            monthly_limits = {
                "free": 3,
                "starter": 50,
                "pro": 100,
                "plus": 500,
                "enterprise": 10000,
            }
            monthly_limit = monthly_limits.get(
                user.tier if hasattr(user, "tier") else "free", 3
            )

            # Get statistics for dashboard
            total_videos = video_service.get_user_videos_count(user_id)
            completed_videos = video_service.get_completed_count(user_id)
            failed_videos = video_service.get_failed_count(user_id)

            return render_template(
                "dashboard/dashboard.html",
                current_user=user,
                recent_videos=recent_videos,
                current_date=datetime.now().strftime("%A, %B %d, %Y"),
                unprocessed_videos_count=unprocessed_videos_count,
                processing_count=processing_count,
                videos_processed=videos_processed,
                monthly_limit=monthly_limit,
                total_videos=total_videos,
                completed_videos=completed_videos,
                failed_videos=failed_videos,
            )

        except Exception as e:
            print(f"❌ Dashboard error: {e}")
            import traceback

            traceback.print_exc()
            session.clear()  # Clear session on error
            return redirect(url_for("login_page"))

    @app.route("/upload")
    def upload():
        """Video upload page."""
        from flask import redirect, url_for, session
        from services.user_service import UserService
        from services.video_service import VideoService
        from services.style_service import StyleService
        from services.thumbnail_service import ThumbnailService
        import json
        from pathlib import Path

        # Get user's credit balance
        from services.credit_service import CreditService

        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login_page"))

        user_service = UserService()
        video_service = VideoService()
        style_service = StyleService()
        thumbnail_service = ThumbnailService()

        user = user_service.get_user_by_id(user_id)
        user_tier = user.tier.value if hasattr(user.tier, "value") else user.tier

        # Get ALL video styles with availability info (not filtered)
        all_video_styles = style_service.get_all_styles_with_availability(user.tier)

        # Get ALL thumbnail styles with availability info (not filtered)
        all_thumbnail_styles = thumbnail_service.get_all_thumbnail_styles(user.tier)

        # 🔥 SEPARATE AVAILABLE AND UNAVAILABLE THUMBNAIL STYLES
        available_styles = [
            s for s in all_thumbnail_styles if s.get("available", False)
        ]
        unavailable_styles = [
            s for s in all_thumbnail_styles if not s.get("available", False)
        ]

        # 🔥 SORT EACH GROUP ALPHABETICALLY BY NAME
        available_styles.sort(key=lambda x: x["name"].lower())
        unavailable_styles.sort(key=lambda x: x["name"].lower())

        # 🔥 COMBINE: AVAILABLE FIRST, THEN UNAVAILABLE
        sorted_thumbnail_styles = available_styles + unavailable_styles

        credit_balance = user.credits_remaining

        quality_options = [
            {
                "value": "original",
                "label": "Original Quality",
                "tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            {
                "value": "480p",
                "label": "480p",
                "tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            {
                "value": "720p",
                "label": "720p HD",
                "tiers": ["free", "starter", "pro", "plus", "enterprise"],
            },
            {
                "value": "1080p",
                "label": "1080p Full HD",
                "tiers": ["starter", "pro", "plus", "enterprise"],
            },
            {
                "value": "2K",
                "label": "2K",
                "tiers": ["pro", "plus", "enterprise"],
            },
            {
                "value": "3K",
                "label": "3K",
                "tiers": ["pro", "plus", "enterprise"],
            },
            {
                "value": "4k",
                "label": "4K Ultra HD",
                "tiers": ["pro", "plus", "enterprise"],
            },
            {"value": "8k", "label": "8K Ultra HD", "tiers": ["plus", "enterprise"]},
        ]

        available_qualities = []

        for quality in quality_options:
            if user_tier in quality["tiers"]:
                available_qualities.append(
                    {
                        "value": quality["value"],
                        "label": quality["label"],
                        "available": True,
                    }
                )

        # Load all languages from config file (sorted alphabetically)
        languages = []
        config_path = Path(__file__).parent.parent / "config" / "languages.json"

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                languages = data.get("languages", [])
                languages.sort(key=lambda x: x["name"])

        # Get tokens from session
        access_token = session.get("access_token")
        refresh_token = session.get("refresh_token")

        unprocessed_videos_count = video_service.get_unprocessed_count(user_id)
        processing_count = video_service.get_processing_count(user_id)
        videos_processed = getattr(user, "videos_processed_this_month", 0)

        monthly_limits = {
            "free": 3,
            "starter": 50,
            "pro": 100,
            "plus": 250,
            "enterprise": 1000,
        }
        monthly_limit = monthly_limits.get(user_tier, 3)
        has_unlimited_credits = False

        return render_template(
            "dashboard/upload.html",
            current_user=user,
            available_qualities=available_qualities,
            available_styles=all_video_styles,
            thumbnail_styles=sorted_thumbnail_styles,  # 🔥 USE THE SORTED VERSION
            languages=languages,
            default_quality="original",
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,
            videos_processed=videos_processed,
            monthly_limit=monthly_limit,
            access_token=access_token,
            refresh_token=refresh_token,
            credits_remaining=(credit_balance),
        )

    @app.route("/processing")
    def processing():
        """Video processing status page."""
        from flask import session, redirect, url_for, render_template, request
        from services.user_service import UserService
        from services.video_service import VideoService
        
        # Get video_id from query parameter
        video_id = request.args.get('video_id')
        
        if not video_id:
            # Try to get from session
            video_id = session.get('processing_video_id')
        
        if not video_id:
            return redirect(url_for('upload'))
        
        # Verify user is logged in and owns this video
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login_page"))
        
        user_service = UserService()
        video_service = VideoService()
        
        user = user_service.get_user_by_id(user_id)
        video = video_service.get_video_by_id(video_id)
        
        if not video or video.user_id != user_id:
            return redirect(url_for('upload'))
        
        return render_template(
            "dashboard/processing.html",
            current_user=user,
            video=video,
            video_id=video_id
        )

    @app.route("/history")
    def history():
        """Video history page."""
        from services.user_service import UserService
        from services.video_service import VideoService
        from flask import Flask, url_for, redirect, session

        user_id = session.get("user_id")

        if not user_id:
            return redirect(url_for("login_page"))

            # Get query parameters
        page = request.args.get("page", 1, type=int)
        search = request.args.get("search", "")
        status = request.args.get("status", "")
        sort = request.args.get("sort", "newest")

        user_service = UserService()
        video_service = VideoService()

        user = user_service.get_user_by_id(user_id)

        # Get user's video processing stats
        videos_processed = getattr(user, "videos_processed_this_month", 0)

        # Get monthly limit based on user's tier
        monthly_limits = {
            "free": 3,
            "starter": 50,
            "pro": 100,
            "plus": 500,
            "enterprise": 10000,
        }
        monthly_limit = monthly_limits.get(
            user.tier if hasattr(user, "tier") else "free", 3
        )

        # Get paginated videos
        result = video_service.get_user_videos_paginated(
            user_id=user_id,
            page=page,
            per_page=10,
            search=search,
            status=status,
            sort=sort,
        )
        # Get counts for sidebar
        videos = video_service.get_user_videos(user_id)
        unprocessed_videos_count = video_service.get_unprocessed_count(user_id)
        processing_count = video_service.get_processing_count(user_id)

        return render_template(
            "dashboard/history.html",
            current_user=user,
            videos=result["videos"],
            total_pages=result["total_pages"],
            page=page,
            search_query=search,
            status_filter=status,
            sort_by=sort,
            videos_processed=videos_processed,
            monthly_limit=monthly_limit,
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,  # ADD
            total_videos=result["total"],
            completed_videos=video_service.get_completed_count(user_id),
            processing_videos=processing_count,
            failed_videos=video_service.get_failed_count(user_id),
        )

    @app.route("/uploads/<path:video_id>/original.mp4")
    def serve_original_video(video_id):
        """Serve original uploaded video for preview."""
        from flask import send_file, session, jsonify
        from services.video_service import VideoService

        # Get user from session
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        video_service = VideoService()
        video = video_service.get_video(video_id, user_id)

        if not video or not video.original_path:
            return jsonify({"error": "Video not found"}), 404

        if not os.path.exists(video.original_path):
            return jsonify({"error": "Video file not found"}), 404

        return send_file(
            video.original_path,
            mimetype="video/mp4",
            as_attachment=False,
            conditional=True,
        )

    @app.route("/processed/<video_id>/output.mp4")
    def serve_processed_video(video_id):
        """Serve processed video file."""
        from flask import send_file, abort
        from services.video_service import VideoService
        import os
        import tempfile
        import glob
        import logging

        logger = logging.getLogger(__name__)

        video_service = VideoService()
        video = video_service.get_video_by_id(video_id)

        if not video:
            logger.error(f"Video not found: {video_id}")
            abort(404)

        file_path = None

        # Check output_path first
        if hasattr(video, "output_path") and video.output_path:
            if os.path.exists(video.output_path):
                file_path = video.output_path
                logger.info(f"Found video at output_path: {file_path}")

        # Check output_video_url (which stores the actual path)
        if (
            not file_path
            and hasattr(video, "output_video_url")
            and video.output_video_url
        ):
            if os.path.exists(video.output_video_url):
                file_path = video.output_video_url
                logger.info(f"Found video at output_video_url: {file_path}")

        # Search in the upload directory
        if not file_path:
            base_dir = os.path.join(
                tempfile.gettempdir(), "video_ai", "uploads", video_id
            )
            logger.info(f"Searching for video in: {base_dir}")

            if os.path.exists(base_dir):
                # Look for mp4 files (excluding original.mp4)
                mp4_files = glob.glob(os.path.join(base_dir, "*.mp4"))
                # Filter out original.mp4 if present
                processed_files = [f for f in mp4_files if "original" not in f.lower()]

                if processed_files:
                    # Get the most recently modified file
                    file_path = max(processed_files, key=os.path.getmtime)
                    logger.info(f"Found processed video: {file_path}")
                elif mp4_files:
                    # Fallback to any mp4 file
                    file_path = max(mp4_files, key=os.path.getmtime)
                    logger.info(f"Found video (fallback): {file_path}")

        if not file_path or not os.path.exists(file_path):
            logger.error(f"Video file not found for {video_id}. Base dir: {base_dir}")
            return jsonify({"error": "Video file not found", "video_id": video_id}), 404

        logger.info(f"Serving video: {file_path}")
        logger.info(f"File size: {os.path.getsize(file_path)} bytes")

        return send_file(
            file_path,
            mimetype="video/mp4",
            as_attachment=False,
            conditional=True,
            download_name=f"processed_video_{video_id}.mp4",
        )

    @app.route("/results")
    def results_page():
        """Video results page."""
        from flask import session, redirect, url_for, render_template, request
        from services.video_service import VideoService
        from services.user_service import UserService
        from services.style_service import StyleService
        import uuid
        import os
        import logging

        logger = logging.getLogger(__name__)

        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login_page"))
        
        # Get video_id from query parameter
        video_id = request.args.get("video_id")
        
        if not video_id:
            return redirect(url_for("dashboard"))

        video_service = VideoService()
        user_service = UserService()

        video = video_service.get_video(video_id, user_id)
        if not video:
            return redirect(url_for("dashboard"))
        
        # Log the actual settings from database
        logger.info(f"📊 RESULTS PAGE - Video settings from DB:")
        logger.info(f"   output_quality: {video.output_quality}")
        logger.info(f"   fps: {video.fps}")
        logger.info(f"   audio_quality: {video.audio_quality}")
        logger.info(f"   aspect_ratio: {video.aspect_ratio}")
        logger.info(f"   applied_styles: {video.applied_styles}")

        user = user_service.get_user_by_id(user_id)

        # Process thumbnails to have proper URLs
        thumbnails = []

        # Process AI thumbnails
        if hasattr(video, "ai_thumbnails") and video.ai_thumbnails:
            for thumb in video.ai_thumbnails:
                if isinstance(thumb, dict):
                    thumb_path = thumb.get("path", "")
                else:
                    thumb_path = thumb

                normalized_path = thumb_path.replace("\\", "/")

                thumbnails.append(
                    {
                        "id": str(uuid.uuid4()),
                        "url": f"/api/v1/videos/thumbnails/{normalized_path}",
                        "type": "ai",
                        "selected": thumb_path == getattr(video, "selected_thumbnail", ""),
                    }
                )

        # Process extracted thumbnails
        if hasattr(video, "extracted_thumbnails") and video.extracted_thumbnails:
            for i, thumb_path in enumerate(video.extracted_thumbnails[:12]):
                normalized_path = thumb_path.replace("\\", "/")

                thumbnails.append(
                    {
                        "id": f"extracted_{i}",
                        "url": f"/api/v1/videos/thumbnails/{normalized_path}",
                        "type": "extracted",
                        "selected": False,
                    }
                )

        style_service = StyleService()
        available_styles = style_service.get_all_styles_with_availability(user.tier)

        return render_template(
            "dashboard/results.html",
            video=video,
            current_user=user,
            thumbnails=thumbnails,
            available_styles=available_styles,
            engagement_score=75,
            transcription_confidence="High",
        )

    @app.route("/settings")
    def settings():
        """User settings page."""
        from flask import session, redirect, url_for
        from services.user_service import UserService
        from services.video_service import VideoService
        from core.tier_utils import (
            get_languages,
            get_timezones,
            get_available_qualities,
            get_available_styles,
            get_rate_limits,
            get_tier_color,
            get_max_duration,
            get_retention_days,
            get_max_quality,
            get_ai_thumbnails_count,
            get_queue_priority,
            get_monthly_video_limit,
            can_use_feature,
            get_upgrade_options,
        )

        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login_page"))

        user_service = UserService()
        video_service = VideoService()

        user = user_service.get_user_by_id(user_id)

        # Ensure user.settings exists and has the expected structure
        if not hasattr(user, "settings") or user.settings is None:
            user.settings = {}

        # Ensure email_notifications exists in settings
        if "email_notifications" not in user.settings:
            user.settings["email_notifications"] = {
                "processing_complete": True,
                "newsletter": False,
                "marketing": False,
            }

        # Get counts for sidebar
        unprocessed_videos_count = video_service.get_unprocessed_count(user_id)
        processing_count = video_service.get_processing_count(user_id)
        total_videos = video_service.get_user_videos_count(user_id)

        return render_template(
            "dashboard/settings.html",
            current_user=user,
            unprocessed_videos_count=unprocessed_videos_count,
            processing_count=processing_count,
            total_videos=total_videos,
            # Add other settings data as needed
            languages=get_languages() if "get_languages" in globals() else [],
            timezones=get_timezones() if "get_timezones" in globals() else [],
            available_qualities=(
                get_available_qualities(user.tier)
                if "get_available_qualities" in globals()
                else []
            ),
            available_styles=(
                get_available_styles(user.tier)
                if "get_available_styles" in globals()
                else []
            ),
            rate_limits=get_rate_limits() if "get_rate_limits" in globals() else {},
            tier_color=(
                get_tier_color(user.tier)
                if "get_tier_color" in globals()
                else "primary"
            ),
            max_duration=(
                get_max_duration(user.tier) if "get_max_duration" in globals() else 3
            ),
            retention_days=(
                get_retention_days(user.tier)
                if "get_retention_days" in globals()
                else 1
            ),
            max_quality=(
                get_max_quality(user.tier) if "get_max_quality" in globals() else "720p"
            ),
            ai_thumbnails=(
                get_ai_thumbnails_count(user.tier)
                if "get_ai_thumbnails_count" in globals()
                else 1
            ),
            queue_priority=(
                get_queue_priority(user.tier)
                if "get_queue_priority" in globals()
                else "normal"
            ),
        )
    
    @app.route("/debug/video-db/<video_id>")
    def debug_video_db(video_id):
        """Debug endpoint to check video values in database."""
        from flask import session, jsonify
        from services.video_service import VideoService
        from providers.firebase_provider import FirebaseProvider
        
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        
        # Get from database directly
        db = FirebaseProvider()
        video_data = db.get("videos", video_id)
        
        if not video_data:
            return jsonify({"error": "Video not found"}), 404
        
        # Check if user owns this video
        if video_data.get("user_id") != user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        return jsonify({
            "output_quality": video_data.get("output_quality"),
            "fps": video_data.get("fps"),
            "audio_quality": video_data.get("audio_quality"),
            "aspect_ratio": video_data.get("aspect_ratio"),
            "thumbnail_style": video_data.get("thumbnail_style"),
            "applied_styles": video_data.get("applied_styles"),
            "output_video_url": video_data.get("output_video_url"),
            "processing_time": video_data.get("processing_time"),
            "processing_started": video_data.get("processing_started"),
            "processing_completed": video_data.get("processing_completed"),
        })

    # Pricing page
    @app.route("/pricing")
    def pricing():
        """Pricing and tiers page."""
        return render_template("billing/pricing.html")

    # Tier limit page
    @app.route("/tier-limit")
    def tier_limit():
        """Tier limit reached page."""
        from services.tier_service import TierService
        from services.user_service import UserService

        # This  come from session/authentication
        user_id = request.args.get("user_id")
        tier_service = TierService()
        user_service = UserService()

        if user_id:
            user = user_service.get_user(user_id)
            current_tier = tier_service.get_tier(user.tier)

            # Get usage stats
            usage_stats = {
                "videos_processed": user.videos_processed_this_month,
                "credits_remaining": user.credits_remaining,
            }

            # Get upgrade options
            upgrade_options = tier_service.get_upgrade_options(user.tier)

            return render_template(
                "errors/tier_limit.html",
                current_tier=current_tier,
                current_usage=usage_stats,
                upgrade_options=upgrade_options,
            )

        return render_template("errors/tier_limit.html")

    @app.errorhandler(Exception)
    def handle_all_exceptions(error):
        """Handle all uncaught exceptions."""
        logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
        return handle_exception(error)

    # Request logging middleware
    @app.before_request
    def before_request():
        """Log incoming requests."""
        if request.path not in ["/health", "/metrics"]:
            logger.info(
                f"Request: {request.method} {request.path} from {request.remote_addr}"
            )

    @app.after_request
    def after_request(response):
        """Log outgoing responses."""
        if request.path not in ["/health", "/metrics"]:
            logger.info(
                f"Response: {request.method} {request.path} - {response.status_code}"
            )
        return response

    @app.route("/preview/<video_id>")
    @jwt_required(optional=True)
    def preview_video(video_id):
        """Serve video for preview."""
        from flask import send_file, session
        from services.video_service import VideoService

        # Get user from session or JWT
        user_id = session.get("user_id")
        if not user_id:
            try:
                from flask_jwt_extended import get_jwt_identity

                user_id = get_jwt_identity()
            except:
                pass

        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        video_service = VideoService()
        video = video_service.get_video(video_id, user_id)

        if not video or not video.original_path:
            return jsonify({"error": "Video not found"}), 404

        if not os.path.exists(video.original_path):
            return jsonify({"error": "Video file not found"}), 404

        return send_file(video.original_path, mimetype="video/mp4", as_attachment=False)

    logger.info("✅ Application setup completed")

    return app, socketio


# Create app instances
app, socketio = create_app()

if __name__ == "__main__":

    logger.info("🎬 Starting Video AI Studio server...")
    logger.info(f"🌐 Server URL: http://0.0.0.0:5000")
    logger.info(f"📅 Start time: {datetime.utcnow().isoformat()}")

    # Start the server
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=app.config.get("DEBUG", False),
        # allow_unsafe_werkzeug=True,
        use_reloader=False
    )
