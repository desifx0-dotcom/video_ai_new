"""
Flask application package.
"""
from flask import Flask
from .config import Config
from .extensions import init_extensions
from .middleware import register_middleware

__version__ = "1.0.0"
__author__ = "Video AI Studio Team"

def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Initialize extensions
    init_extensions(app)
    
    # Register middleware
    register_middleware(app)
    
    # Register blueprints
    from api.v1 import api_v1
    app.register_blueprint(api_v1, url_prefix='/api/v1')
    
    return app