"""
Custom error handlers for the Flask application.
"""
from flask import jsonify, current_app, request, render_template
from werkzeug.exceptions import HTTPException

from core.exceptions import VideoAIException, handle_exception

def register_error_handlers(app):
    """Register all error handlers with the Flask app."""
    
    @app.errorhandler(VideoAIException)
    def handle_videoai_exception(error):
        """Handle custom VideoAIException."""
        response, status_code = handle_exception(error)
        return jsonify(response), status_code
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle HTTP exceptions."""
        response = {
            "error": {
                "code": error.code,
                "name": error.name,
                "description": error.description,
                "status_code": error.code
            }
        }
        
        # Add request ID if available
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        current_app.logger.warning(
            f"HTTP Exception: {error.code} {error.name}",
            extra={
                "type": "http_exception",
                "status_code": error.code,
                "path": request.path,
                "method": request.method
            }
        )
        
        return jsonify(response), error.code
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 Not Found errors."""
        if request.path.startswith('/api/'):
            # API 404 response
            response = {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "The requested resource was not found",
                    "status_code": 404
                }
            }
            
            if hasattr(request, 'request_id'):
                response['request_id'] = request.request_id
            
            return jsonify(response), 404
        else:
            # Web page 404 response
            return render_template('errors/404.html'), 404
    
    @app.errorhandler(429)
    def handle_rate_limit(error):
        """Handle 429 Rate Limit Exceeded errors."""
        response = {
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded. Please try again later.",
                "status_code": 429,
                "retry_after": getattr(error, 'retry_after', None)
            }
        }
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        current_app.logger.warning(
            f"Rate limit exceeded for {request.path}",
            extra={
                "type": "rate_limit",
                "client_ip": request.remote_addr,
                "path": request.path,
                "method": request.method
            }
        )
        
        return jsonify(response), 429
    
    @app.errorhandler(413)
    def handle_request_entity_too_large(error):
        """Handle 413 Request Entity Too Large errors."""
        response = {
            "error": {
                "code": "FILE_TOO_LARGE",
                "message": "The uploaded file exceeds the maximum allowed size",
                "status_code": 413,
                "max_size": current_app.config.get('MAX_CONTENT_LENGTH', 0)
            }
        }
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        return jsonify(response), 413
    
    @app.errorhandler(500)
    def handle_internal_server_error(error):
        """Handle 500 Internal Server Error."""
        # Log the error
        current_app.logger.error(
            f"Internal Server Error: {str(error)}",
            extra={
                "type": "internal_error",
                "path": request.path,
                "method": request.method,
                "error": str(error),
                "traceback": getattr(error, 'traceback', None)
            }
        )
        
        if request.path.startswith('/api/'):
            # API 500 response
            response = {
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred",
                    "status_code": 500
                }
            }
            
            # Include error details in development mode
            if current_app.config.get('DEBUG', False):
                response['error']['detail'] = str(error)
                if hasattr(error, 'traceback'):
                    response['error']['traceback'] = error.traceback
            
            if hasattr(request, 'request_id'):
                response['request_id'] = request.request_id
            
            return jsonify(response), 500
        else:
            # Web page 500 response
            return render_template('errors/500.html'), 500
    
    @app.errorhandler(Exception)
    def handle_generic_exception(error):
        """Handle all other exceptions."""
        # Convert to VideoAIException if not already
        if not isinstance(error, (VideoAIException, HTTPException)):
            error = VideoAIException(
                message=str(error),
                code="INTERNAL_ERROR",
                status_code=500
            )
        
        return handle_videoai_exception(error)
    
    @app.errorhandler(400)
    def handle_bad_request(error):
        """Handle 400 Bad Request errors."""
        if request.path.startswith('/api/'):
            response = {
                "error": {
                    "code": "BAD_REQUEST",
                    "message": "The request could not be understood or was missing required parameters",
                    "status_code": 400
                }
            }
            
            # Try to extract validation errors from description
            if hasattr(error, 'description'):
                import json
                try:
                    errors = json.loads(error.description)
                    if isinstance(errors, dict):
                        response['error']['details'] = errors
                except:
                    response['error']['details'] = error.description
            
            if hasattr(request, 'request_id'):
                response['request_id'] = request.request_id
            
            return jsonify(response), 400
        else:
            return render_template('errors/400.html'), 400
    
    @app.errorhandler(401)
    def handle_unauthorized(error):
        """Handle 401 Unauthorized errors."""
        response = {
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Authentication is required to access this resource",
                "status_code": 401
            }
        }
        
        # Add WWW-Authenticate header for API requests
        if request.path.startswith('/api/'):
            response['headers'] = {
                'WWW-Authenticate': 'Bearer realm="Video AI Studio API"'
            }
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        return jsonify(response), 401
    
    @app.errorhandler(403)
    def handle_forbidden(error):
        """Handle 403 Forbidden errors."""
        response = {
            "error": {
                "code": "FORBIDDEN",
                "message": "You do not have permission to access this resource",
                "status_code": 403
            }
        }
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        # Check if it's a tier limit error
        if "tier" in str(error).lower() or "limit" in str(error).lower():
            response['error']['code'] = "TIER_LIMIT_EXCEEDED"
            response['error']['message'] = "This feature requires a higher subscription tier"
            
            # Don't render template for API requests
            if not request.path.startswith('/api/'):
                return render_template('errors/tier_limit.html'), 403
        
        return jsonify(response), 403
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """Handle 405 Method Not Allowed errors."""
        response = {
            "error": {
                "code": "METHOD_NOT_ALLOWED",
                "message": f"The {request.method} method is not allowed for this resource",
                "status_code": 405,
                "allowed_methods": getattr(error, 'valid_methods', [])
            }
        }
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        return jsonify(response), 405
    
    @app.errorhandler(422)
    def handle_unprocessable_entity(error):
        """Handle 422 Unprocessable Entity errors."""
        response = {
            "error": {
                "code": "UNPROCESSABLE_ENTITY",
                "message": "The request was well-formed but contains semantic errors",
                "status_code": 422
            }
        }
        
        # Try to extract validation errors
        if hasattr(error, 'data') and 'messages' in error.data:
            response['error']['validation_errors'] = error.data['messages']
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        return jsonify(response), 422
    
    @app.before_request
    def assign_request_id():
        """Assign a unique request ID to each request."""
        import uuid
        request.request_id = str(uuid.uuid4())
    
    @app.after_request
    def add_request_id_header(response):
        """Add request ID to response headers."""
        if hasattr(request, 'request_id'):
            response.headers['X-Request-ID'] = request.request_id
        return response
    
    # Register a custom error for maintenance mode
    class MaintenanceModeError(VideoAIException):
        """Exception for maintenance mode."""
        def __init__(self):
            super().__init__(
                message="The service is currently under maintenance. Please try again later.",
                code="MAINTENANCE_MODE",
                status_code=503
            )
    
    @app.errorhandler(MaintenanceModeError)
    def handle_maintenance_mode(error):
        """Handle maintenance mode errors."""
        response = {
            "error": {
                "code": error.code,
                "message": error.message,
                "status_code": error.status_code
            }
        }
        
        # Add maintenance information
        maintenance_info = current_app.config.get('MAINTENANCE_INFO', {})
        if maintenance_info:
            response['maintenance'] = maintenance_info
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        current_app.logger.info(
            "Maintenance mode request",
            extra={
                "type": "maintenance",
                "path": request.path,
                "method": request.method
            }
        )
        
        return jsonify(response), error.status_code
    
    # Register a teapot error for fun (418 I'm a teapot)
    @app.errorhandler(418)
    def handle_teapot(error):
        """Handle 418 I'm a teapot errors."""
        response = {
            "error": {
                "code": "IM_A_TEAPOT",
                "message": "I'm a teapot. This server refuses to brew coffee because it is, permanently, a teapot.",
                "status_code": 418
            }
        }
        
        if hasattr(request, 'request_id'):
            response['request_id'] = request.request_id
        
        # Add some fun headers
        response['headers'] = {
            'X-Tea-Type': 'Earl Grey',
            'X-Brewing-Temperature': '95°C',
            'X-Steeping-Time': '3-5 minutes'
        }
        
        return jsonify(response), 418