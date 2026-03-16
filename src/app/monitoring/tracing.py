"""
OpenTelemetry tracing for distributed tracing.
"""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor

def init_tracing(app):
    """Initialize OpenTelemetry tracing."""
    
    # Skip if tracing is disabled
    if not app.config.get('ENABLE_TRACING', False):
        return app
    
    # Set up tracing
    trace.set_tracer_provider(
        TracerProvider(
            resource=Resource.create({
                "service.name": "video-ai-studio",
                "service.version": "1.0.0",
                "environment": app.config.get('FLASK_ENV', 'development')
            })
        )
    )
    
    # Configure exporter
    if app.config.get('OTLP_ENDPOINT'):
        otlp_exporter = OTLPSpanExporter(
            endpoint=app.config['OTLP_ENDPOINT'],
            insecure=app.config.get('OTLP_INSECURE', True)
        )
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)
    
    # Instrument Flask
    FlaskInstrumentor().instrument_app(app)
    
    # Instrument requests
    RequestsInstrumentor().instrument()
    
    # Instrument Redis
    RedisInstrumentor().instrument()
    
    # Instrument Celery
    CeleryInstrumentor().instrument()
    
    return app

def trace_span(name, attributes=None):
    """Decorator for creating spans."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(name, attributes=attributes) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator