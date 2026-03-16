FROM redis:7-alpine

# Copy custom Redis configuration
COPY redis.conf /usr/local/etc/redis/redis.conf

# Create directory for persistence
RUN mkdir -p /data && chown redis:redis /data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD redis-cli ping | grep -q PONG || exit 1

# Run Redis with custom configuration
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]