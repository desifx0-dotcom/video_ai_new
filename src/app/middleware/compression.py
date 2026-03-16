"""
Response compression middleware.
"""
from flask_compress import Compress

compress = Compress()

def setup_compression(app):
    """Configure response compression."""
    
    compress.init_app(app)
    
    # Compression settings
    app.config['COMPRESS_MIMETYPES'] = [
        'text/html',
        'text/css',
        'text/xml',
        'application/json',
        'application/javascript',
        'image/svg+xml'
    ]
    
    app.config['COMPRESS_LEVEL'] = 6
    app.config['COMPRESS_MIN_SIZE'] = 500
    
    return app