"""
Prometheus metrics for monitoring.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import time
from flask import request, g

# HTTP Metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP Request Latency',
    ['method', 'endpoint']
)

REQUEST_SIZE = Histogram(
    'http_request_size_bytes',
    'HTTP Request Size',
    ['method', 'endpoint'],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

RESPONSE_SIZE = Histogram(
    'http_response_size_bytes',
    'HTTP Response Size',
    ['method', 'endpoint'],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

# Business Metrics
VIDEO_PROCESSED = Counter(
    'videos_processed_total',
    'Total Videos Processed',
    ['tier', 'video_type', 'status']
)

VIDEO_PROCESSING_TIME = Histogram(
    'video_processing_duration_seconds',
    'Video Processing Duration',
    ['tier', 'video_type']
)

AI_COST = Counter(
    'ai_processing_cost_total',
    'Total AI Processing Cost in USD',
    ['service', 'tier']
)

USER_SIGNUP = Counter(
    'user_signups_total',
    'Total User Signups',
    ['tier']
)

TIER_UPGRADE = Counter(
    'tier_upgrades_total',
    'Total Tier Upgrades',
    ['from_tier', 'to_tier']
)

# System Metrics
ACTIVE_USERS = Gauge(
    'active_users_current',
    'Current Active Users'
)

QUEUE_LENGTH = Gauge(
    'processing_queue_length',
    'Current Processing Queue Length'
)

MEMORY_USAGE = Gauge(
    'memory_usage_bytes',
    'Current Memory Usage'
)

CPU_USAGE = Gauge(
    'cpu_usage_percent',
    'Current CPU Usage'
)

DATABASE_CONNECTIONS = Gauge(
    'database_connections_current',
    'Current Database Connections'
)

def init_metrics(app):
    """Initialize metrics collection."""
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
        if request.content_length:
            REQUEST_SIZE.labels(
                method=request.method,
                endpoint=request.endpoint or request.path
            ).observe(request.content_length)
    
    @app.after_request
    def after_request(response):
        # Skip metrics endpoint
        if request.path == '/metrics':
            return response
        
        # Record request latency
        if hasattr(g, 'start_time'):
            latency = time.time() - g.start_time
            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=request.endpoint or request.path
            ).observe(latency)
        
        # Record request count
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.endpoint or request.path,
            status=response.status_code
        ).inc()
        
        # Record response size
        if response.content_length:
            RESPONSE_SIZE.labels(
                method=request.method,
                endpoint=request.endpoint or request.path
            ).observe(response.content_length)
        
        return response
    
    return app

def record_video_processing(tier, video_type, duration, status='completed'):
    """Record video processing metrics."""
    VIDEO_PROCESSED.labels(
        tier=tier,
        video_type=video_type,
        status=status
    ).inc()
    
    VIDEO_PROCESSING_TIME.labels(
        tier=tier,
        video_type=video_type
    ).observe(duration)

def record_ai_cost(service, tier, cost):
    """Record AI processing cost."""
    AI_COST.labels(
        service=service,
        tier=tier
    ).inc(cost)

def record_user_signup(tier):
    """Record user signup."""
    USER_SIGNUP.labels(tier=tier).inc()

def record_tier_upgrade(from_tier, to_tier):
    """Record tier upgrade."""
    TIER_UPGRADE.labels(
        from_tier=from_tier,
        to_tier=to_tier
    ).inc()

def update_system_metrics():
    """Update system metrics (call periodically)."""
    import psutil
    import os
    
    # Update memory usage
    process = psutil.Process(os.getpid())
    MEMORY_USAGE.set(process.memory_info().rss)
    
    # Update CPU usage
    CPU_USAGE.set(process.cpu_percent())
    
    # Update active users (example - implement your own logic)
    # ACTIVE_USERS.set(get_active_user_count())
    
    # Update queue length
    from tasks.celery_app import celery
    i = celery.control.inspect()
    active = i.active() or {}
    QUEUE_LENGTH.set(sum(len(tasks) for tasks in active.values()))

# ADD THESE FUNCTIONS AT THE BOTTOM OF metrics.py:

def record_metric(metric_name, labels=None, value=1, metric_type='counter'):
    """Generic metric recording function.
    
    Args:
        metric_name: Name of the metric
        labels: Dictionary of labels
        value: Value to record
        metric_type: Type of metric ('counter', 'gauge', 'histogram')
    """
    if labels is None:
        labels = {}
    
    # Map metric_name to actual metric objects
    metric_map = {
        'http_requests': REQUEST_COUNT,
        'http_latency': REQUEST_LATENCY,
        'http_request_size': REQUEST_SIZE,
        'http_response_size': RESPONSE_SIZE,
        'videos_processed': VIDEO_PROCESSED,
        'video_processing_time': VIDEO_PROCESSING_TIME,
        'ai_cost': AI_COST,
        'user_signups': USER_SIGNUP,
        'tier_upgrades': TIER_UPGRADE,
        'active_users': ACTIVE_USERS,
        'queue_length': QUEUE_LENGTH,
        'memory_usage': MEMORY_USAGE,
        'cpu_usage': CPU_USAGE,
        'database_connections': DATABASE_CONNECTIONS
    }
    
    metric = metric_map.get(metric_name)
    
    if metric:
        try:
            if metric_type == 'counter':
                metric.labels(**labels).inc(value)
            elif metric_type == 'gauge':
                metric.labels(**labels).set(value)
            elif metric_type == 'histogram':
                metric.labels(**labels).observe(value)
        except Exception as e:
            print(f"Error recording metric {metric_name}: {e}")
    else:
        print(f"Warning: Unknown metric {metric_name}")

def get_metrics():
    """Get all metrics in Prometheus format."""
    return generate_latest(REGISTRY)