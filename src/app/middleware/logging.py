"""
Request/response logging middleware.
"""
import time
import json
from flask import request, g
import logging

logger = logging.getLogger(__name__)

def log_request():
    """Log incoming request."""
    g.start_time = time.time()
    
    # Skip health checks and metrics
    if request.path in ['/health', '/metrics']:
        return
    
    log_data = {
        'type': 'request',
        'method': request.method,
        'path': request.path,
        'endpoint': request.endpoint,
        'remote_addr': request.remote_addr,
        'user_agent': request.user_agent.string,
        'content_type': request.content_type,
        'content_length': request.content_length,
    }
    
    # Add query parameters (excluding sensitive data)
    if request.args:
        safe_args = {k: v for k, v in request.args.items() 
                    if k not in ['password', 'token', 'api_key']}
        log_data['query_params'] = safe_args
    
    logger.info('Incoming request', extra=log_data)

def log_response(response):
    """Log outgoing response."""
    # Skip health checks and metrics
    if request.path in ['/health', '/metrics']:
        return response
    
    processing_time = 0
    if hasattr(g, 'start_time'):
        processing_time = (time.time() - g.start_time) * 1000
    
    log_data = {
        'type': 'response',
        'method': request.method,
        'path': request.path,
        'status_code': response.status_code,
        'processing_time_ms': processing_time,
        'content_length': response.content_length,
    }
    
    # Add user info if available
    if hasattr(g, 'current_user'):
        log_data['user_id'] = g.current_user.id
    
    logger.info('Outgoing response', extra=log_data)
    
    return response