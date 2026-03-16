#!/bin/bash

# Video AI Studio Staging Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="staging"
PROJECT_NAME="video-ai-studio-staging"

echo -e "${GREEN}🚀 Starting Video AI Studio Staging Deployment${NC}"
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"

# Load environment variables
if [ -f ".env.${ENVIRONMENT}" ]; then
    echo -e "${GREEN}📁 Loading environment variables from .env.${ENVIRONMENT}${NC}"
    export $(cat .env.${ENVIRONMENT} | grep -v '^#' | xargs)
else
    echo -e "${RED}❌ Environment file .env.${ENVIRONMENT} not found${NC}"
    exit 1
fi

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# Deploy to staging
log "🐳 Building and deploying staging environment..."

# Build and deploy using docker-compose
docker-compose -f docker-compose.staging.yml down
docker-compose -f docker-compose.staging.yml build --no-cache
docker-compose -f docker-compose.staging.yml up -d

# Wait for services to be ready
log "⏳ Waiting for services to be ready..."
sleep 10

# Run health check
if curl -f http://localhost:${STAGING_PORT:-5001}/health >/dev/null 2>&1; then
    log "✅ Staging deployment successful!"
    
    # Run staging tests
    log "🧪 Running staging tests..."
    docker-compose -f docker-compose.staging.yml exec -T web pytest tests/e2e/ -v
    
    log "🎉 Staging environment is ready for testing!"
else
    echo -e "${RED}❌ Staging deployment failed${NC}"
    exit 1
fi