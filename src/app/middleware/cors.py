"""
CORS middleware.
"""
from flask_cors import CORS

def setup_cors(app):
    """Configure CORS for the application."""
    
    CORS(app, resources={
        r"/api/*": {
            "origins": app.config.get("CORS_ORIGINS", ["*"]),
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "X-Requested-With",
                "Accept",
                "Origin",
                "X-CSRF-Token"
            ],
            "expose_headers": [
                "Content-Range",
                "X-Content-Range",
                "X-RateLimit-Limit",
                "X-RateLimit-Remaining",
                "X-RateLimit-Reset"
            ],
            "supports_credentials": True,
            "max_age": 600
        },
        r"/socket.io/*": {
            "origins": app.config.get("CORS_ORIGINS", ["*"]),
            "methods": ["GET", "POST"],
            "allow_headers": ["Authorization"],
            "credentials": True
        }
    })
    
    @app.after_request
    def after_request(response):
        """Add CORS headers to all responses."""
        response.headers.add('Access-Control-Allow-Origin', 
                            app.config.get("CORS_ORIGINS", "*"))
        response.headers.add('Access-Control-Allow-Headers', 
                            'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 
                            'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    
    return app