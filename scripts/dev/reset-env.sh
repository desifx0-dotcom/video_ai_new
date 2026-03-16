#!/bin/bash

# Video AI Studio Development Environment Reset Script

set -e

echo "🔄 Resetting development environment..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Confirm reset
read -p "Are you sure you want to reset the development environment? This will delete all data. (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Reset cancelled"
    exit 0
fi

# Stop any running services
echo "⏹️ Stopping services..."
if command -v docker &> /dev/null; then
    docker stop video-ai-redis video-ai-postgres 2>/dev/null || true
    docker rm video-ai-redis video-ai-postgres 2>/dev/null || true
fi

pkill -f "flask run" 2>/dev/null || true
pkill -f "celery" 2>/dev/null || true

# Remove virtual environment
echo "🗑️ Removing virtual environment..."
if [ -d ".venv" ]; then
    rm -rf .venv
    echo -e "${GREEN}✅ Virtual environment removed${NC}"
else
    echo -e "${YELLOW}⚠️ Virtual environment not found${NC}"
fi

# Clear data directories
echo "🧹 Clearing data directories..."
rm -rf data/uploads/*
rm -rf data/processing/*
rm -rf data/outputs/*
rm -rf data/logs/*
rm -rf data/cache/*

# Remove cached files
echo "🗑️ Removing cached files..."
rm -rf __pycache__ 2>/dev/null || true
rm -rf src/__pycache__ 2>/dev/null || true
rm -rf tests/__pycache__ 2>/dev/null || true
rm -rf .pytest_cache 2>/dev/null || true
rm -rf .mypy_cache 2>/dev/null || true
rm -rf .coverage 2>/dev/null || true
rm -rf htmlcov 2>/dev/null || true

# Remove environment file
echo "🗑️ Removing environment file..."
if [ -f ".env" ]; then
    rm .env
    echo -e "${GREEN}✅ Environment file removed${NC}"
else
    echo -e "${YELLOW}⚠️ Environment file not found${NC}"
fi

# Remove database files
echo "🗑️ Removing database files..."
if [ -d "instance" ]; then
    rm -rf instance
    echo -e "${GREEN}✅ Database files removed${NC}"
fi

# Remove migrations
echo "🗑️ Removing migrations..."
if [ -d "migrations" ]; then
    rm -rf migrations
    echo -e "${GREEN}✅ Migration files removed${NC}"
fi

# Remove Docker containers and volumes
echo "🐳 Cleaning up Docker..."
if command -v docker &> /dev/null; then
    docker system prune -f --volumes 2>/dev/null || true
    echo -e "${GREEN}✅ Docker cleanup complete${NC}"
fi

# Re-run setup
echo "🚀 Re-running setup..."
./scripts/dev/setup.sh

echo ""
echo -e "${GREEN}🎉 Development environment reset complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Start the development server:"
echo "   flask run"
echo ""
echo "2. Start Celery worker (in separate terminal):"
echo "   celery -A tasks.celery_app worker --loglevel=info"
echo ""
echo "3. Access the application at: http://localhost:5000"