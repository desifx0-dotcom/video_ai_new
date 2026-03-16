#!/bin/bash

# Video AI Studio Rollback Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${1:-"production"}
PROJECT_NAME="video-ai-studio"
BACKUP_DIR="/backup"

echo -e "${GREEN}🔄 Starting Video AI Studio Rollback${NC}"
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Find latest backup
LATEST_BACKUP=$(ls -td ${BACKUP_DIR}/*/ | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    error "No backups found"
    exit 1
fi

log "📦 Found latest backup: ${LATEST_BACKUP}"

# Confirm rollback
read -p "Are you sure you want to rollback to this backup? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "Rollback cancelled"
    exit 0
fi

# Stop current deployment
log "⏹️ Stopping current deployment..."
docker-compose -f docker-compose.prod.yml down --timeout 30

# Restore from backup
log "🔄 Restoring from backup..."

# Restore PostgreSQL data if exists
if [ -f "${LATEST_BACKUP}/postgres_data.tar.gz" ]; then
    log "Restoring PostgreSQL data..."
    docker run --rm \
        -v ${PROJECT_NAME}_postgres_data:/target \
        -v ${LATEST_BACKUP}:/backup \
        alpine sh -c "rm -rf /target/* && tar xzf /backup/postgres_data.tar.gz -C /target"
fi

# Restore Redis data if exists
if [ -f "${LATEST_BACKUP}/redis_data.tar.gz" ]; then
    log "Restoring Redis data..."
    docker run --rm \
        -v ${PROJECT_NAME}_redis_data:/target \
        -v ${LATEST_BACKUP}:/backup \
        alpine sh -c "rm -rf /target/* && tar xzf /backup/redis_data.tar.gz -C /target"
fi

# Restore configuration files
log "Restoring configuration files..."
cp ${LATEST_BACKUP}/docker-compose.prod.yml .
cp ${LATEST_BACKUP}/.env.production .

# Start previous version
log "🚀 Starting previous version..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to be ready
log "⏳ Waiting for services to be ready..."
sleep 10

# Verify rollback
if curl -f http://localhost:${PORT:-5000}/health >/dev/null 2>&1; then
    log "✅ Rollback completed successfully!"
    
    # Send notification
    if [ ! -z "${SLACK_WEBHOOK_URL}" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"🔄 Video AI Studio rolled back to backup from $(basename ${LATEST_BACKUP})\"}" \
            ${SLACK_WEBHOOK_URL} >/dev/null 2>&1
    fi
else
    error "❌ Rollback failed - services not healthy"
    exit 1
fi