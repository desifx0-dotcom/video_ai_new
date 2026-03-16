#!/bin/bash

# Video AI Studio Production Deployment Script
# Usage: ./production.sh [environment]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${1:-"production"}
PROJECT_NAME="video-ai-studio"
DOCKER_REGISTRY="ghcr.io"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/${TIMESTAMP}"

echo -e "${GREEN}🚀 Starting Video AI Studio Production Deployment${NC}"
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
echo -e "Timestamp: ${YELLOW}${TIMESTAMP}${NC}"

# Load environment variables
if [ -f ".env.${ENVIRONMENT}" ]; then
    echo -e "${GREEN}📁 Loading environment variables from .env.${ENVIRONMENT}${NC}"
    export $(cat .env.${ENVIRONMENT} | grep -v '^#' | xargs)
else
    echo -e "${RED}❌ Environment file .env.${ENVIRONMENT} not found${NC}"
    exit 1
fi

# Function to log messages
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# Function to log errors
error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check required commands
for cmd in docker docker-compose curl; do
    if ! command_exists $cmd; then
        error "Required command '$cmd' not found"
        exit 1
    fi
done

# Backup current deployment
backup() {
    log "📦 Creating backup..."
    
    mkdir -p ${BACKUP_DIR}
    
    # Backup Docker volumes if they exist
    if docker volume ls | grep -q "${PROJECT_NAME}_postgres_data"; then
        log "Backing up PostgreSQL data..."
        docker run --rm \
            -v ${PROJECT_NAME}_postgres_data:/source \
            -v ${BACKUP_DIR}:/backup \
            alpine tar czf /backup/postgres_data.tar.gz -C /source .
    fi
    
    if docker volume ls | grep -q "${PROJECT_NAME}_redis_data"; then
        log "Backing up Redis data..."
        docker run --rm \
            -v ${PROJECT_NAME}_redis_data:/source \
            -v ${BACKUP_DIR}:/backup \
            alpine tar czf /backup/redis_data.tar.gz -C /source .
    fi
    
    # Backup configuration files
    cp docker-compose.prod.yml ${BACKUP_DIR}/
    cp .env.production ${BACKUP_DIR}/
    
    log "✅ Backup created at ${BACKUP_DIR}"
}

# Pull latest Docker images
pull_images() {
    log "🐳 Pulling latest Docker images..."
    
    # Login to registry if credentials provided
    if [ ! -z "${DOCKER_REGISTRY_USER}" ] && [ ! -z "${DOCKER_REGISTRY_PASSWORD}" ]; then
        echo "${DOCKER_REGISTRY_PASSWORD}" | docker login ${DOCKER_REGISTRY} -u ${DOCKER_REGISTRY_USER} --password-stdin
    fi
    
    # Pull images
    docker-compose -f docker-compose.prod.yml pull
    
    log "✅ Docker images pulled successfully"
}

# Run database migrations
run_migrations() {
    log "🗄️ Running database migrations..."
    
    # Wait for database to be ready
    log "Waiting for database to be ready..."
    until docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U ${POSTGRES_USER:-postgres}; do
        sleep 2
    done
    
    # Run migrations
    docker-compose -f docker-compose.prod.yml run --rm web flask db upgrade
    
    log "✅ Database migrations completed"
}

# Deploy application
deploy() {
    log "🚀 Deploying application..."
    
    # Stop existing containers
    log "Stopping existing containers..."
    docker-compose -f docker-compose.prod.yml down --timeout 30
    
    # Start new containers
    log "Starting new containers..."
    docker-compose -f docker-compose.prod.yml up -d
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    
    # Wait for web service
    until curl -f http://localhost:${PORT:-5000}/health >/dev/null 2>&1; do
        sleep 5
    done
    
    # Wait for Celery workers
    until docker-compose -f docker-compose.prod.yml exec -T celery celery -A tasks.celery_app inspect ping >/dev/null 2>&1; do
        sleep 5
    done
    
    log "✅ Application deployed successfully"
}

# Run health checks
health_check() {
    log "🏥 Running health checks..."
    
    # Check web service
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT:-5000}/health)
    if [ "$RESPONSE" -eq 200 ]; then
        log "✅ Web service is healthy"
    else
        error "❌ Web service health check failed: HTTP $RESPONSE"
        return 1
    fi
    
    # Check database
    if docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U ${POSTGRES_USER:-postgres} >/dev/null 2>&1; then
        log "✅ Database is healthy"
    else
        error "❌ Database health check failed"
        return 1
    fi
    
    # Check Redis
    if docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping >/dev/null 2>&1; then
        log "✅ Redis is healthy"
    else
        error "❌ Redis health check failed"
        return 1
    fi
    
    # Check Celery
    if docker-compose -f docker-compose.prod.yml exec -T celery celery -A tasks.celery_app inspect ping >/dev/null 2>&1; then
        log "✅ Celery workers are healthy"
    else
        error "❌ Celery health check failed"
        return 1
    fi
    
    log "✅ All health checks passed"
}

# Run cleanup tasks
cleanup() {
    log "🧹 Running cleanup tasks..."
    
    # Remove old Docker images
    docker image prune -f --filter "until=24h"
    
    # Remove stopped containers
    docker container prune -f
    
    # Remove unused volumes
    docker volume prune -f
    
    # Remove old backups (keep last 7 days)
    find /backup -type d -mtime +7 -exec rm -rf {} \;
    
    log "✅ Cleanup completed"
}

# Send deployment notification
send_notification() {
    log "📢 Sending deployment notification..."
    
    # Send to Slack if configured
    if [ ! -z "${SLACK_WEBHOOK_URL}" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"✅ Video AI Studio deployed to ${ENVIRONMENT} at ${TIMESTAMP}\"}" \
            ${SLACK_WEBHOOK_URL} >/dev/null 2>&1
    fi
    
    # Send email if configured
    if [ ! -z "${EMAIL_FROM}" ] && [ ! -z "${EMAIL_TO}" ] && [ ! -z "${SMTP_SERVER}" ]; then
        echo "Video AI Studio has been successfully deployed to ${ENVIRONMENT} at ${TIMESTAMP}" | \
        mail -s "Video AI Studio Deployment Notification" -r "${EMAIL_FROM}" "${EMAIL_TO}"
    fi
    
    log "✅ Notification sent"
}

# Main deployment flow
main() {
    log "🏁 Starting deployment process..."
    
    # Run backup
    backup
    
    # Pull latest images
    pull_images
    
    # Run migrations
    run_migrations
    
    # Deploy application
    deploy
    
    # Run health checks
    if health_check; then
        # Run cleanup
        cleanup
        
        # Send notification
        send_notification
        
        log "🎉 Deployment completed successfully!"
    else
        error "❌ Health checks failed, rolling back..."
        rollback
        exit 1
    fi
}

# Rollback function
rollback() {
    error "🔄 Rolling back deployment..."
    
    # Stop current deployment
    docker-compose -f docker-compose.prod.yml down --timeout 30
    
    # Restore from backup if available
    if [ -d "${BACKUP_DIR}" ]; then
        log "Restoring from backup..."
        
        # Restore volumes
        if [ -f "${BACKUP_DIR}/postgres_data.tar.gz" ]; then
            docker run --rm \
                -v ${PROJECT_NAME}_postgres_data:/target \
                -v ${BACKUP_DIR}:/backup \
                alpine sh -c "rm -rf /target/* && tar xzf /backup/postgres_data.tar.gz -C /target"
        fi
        
        if [ -f "${BACKUP_DIR}/redis_data.tar.gz" ]; then
            docker run --rm \
                -v ${PROJECT_NAME}_redis_data:/target \
                -v ${BACKUP_DIR}:/backup \
                alpine sh -c "rm -rf /target/* && tar xzf /backup/redis_data.tar.gz -C /target"
        fi
        
        # Restore configuration files
        cp ${BACKUP_DIR}/docker-compose.prod.yml .
        cp ${BACKUP_DIR}/.env.production .
        
        # Start previous version
        docker-compose -f docker-compose.prod.yml up -d
    else
        error "No backup found, cannot rollback"
    fi
}

# Trap errors
trap 'error "Deployment failed"; rollback; exit 1' ERR

# Run main deployment
main