#!/bin/bash

# Video AI Studio Development Environment Setup Script

set -e

echo "🚀 Setting up Video AI Studio development environment..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "🐍 Checking Python version..."
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
REQUIRED_VERSION="3.11"

if printf '%s\n%s\n' "${REQUIRED_VERSION}" "${PYTHON_VERSION}" | sort -V -C; then
    echo -e "${GREEN}✅ Python ${PYTHON_VERSION} is compatible${NC}"
else
    echo -e "${RED}❌ Python ${PYTHON_VERSION} is too old. Please install Python ${REQUIRED_VERSION} or higher${NC}"
    exit 1
fi

# Create virtual environment
echo "📁 Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${YELLOW}⚠️ Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
echo "🔧 Setting up pre-commit hooks..."
pre-commit install

# Create environment file
echo "📄 Creating environment file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✅ Environment file created${NC}"
    echo -e "${YELLOW}⚠️ Please update .env with your API keys${NC}"
else
    echo -e "${YELLOW}⚠️ Environment file already exists${NC}"
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data/uploads
mkdir -p data/processing
mkdir -p data/outputs
mkdir -p data/logs
mkdir -p data/cache

# Setup Redis (if Docker is available)
if command -v docker &> /dev/null; then
    echo "🐳 Setting up Redis with Docker..."
    
    if ! docker ps | grep -q redis; then
        docker run -d \
            --name video-ai-redis \
            -p 6379:6379 \
            redis:7-alpine
        
        echo -e "${GREEN}✅ Redis container started${NC}"
    else
        echo -e "${YELLOW}⚠️ Redis container already running${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ Docker not found, skipping Redis setup${NC}"
    echo -e "${YELLOW}⚠️ Please install Redis manually or update .env to use a different Redis URL${NC}"
fi

# Setup PostgreSQL (if Docker is available)
if command -v docker &> /dev/null; then
    echo "🐳 Setting up PostgreSQL with Docker..."
    
    if ! docker ps | grep -q postgres; then
        docker run -d \
            --name video-ai-postgres \
            -p 5432:5432 \
            -e POSTGRES_USER=videoai \
            -e POSTGRES_PASSWORD=development123 \
            -e POSTGRES_DB=videoaistudio \
            postgres:15-alpine
        
        # Wait for PostgreSQL to start
        echo "⏳ Waiting for PostgreSQL to start..."
        sleep 5
        
        echo -e "${GREEN}✅ PostgreSQL container started${NC}"
    else
        echo -e "${YELLOW}⚠️ PostgreSQL container already running${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ Docker not found, skipping PostgreSQL setup${NC}"
fi

# Initialize database
echo "🗄️ Initializing database..."
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
    
    # Run migrations
    flask db upgrade
    
    # Seed database with test data
    echo "🌱 Seeding database with test data..."
    python scripts/dev/seed-db.py
    
    echo -e "${GREEN}✅ Database initialized${NC}"
else
    echo -e "${RED}❌ No .env file found${NC}"
fi

# Install FFmpeg
echo "🎬 Installing FFmpeg..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y ffmpeg
elif command -v brew &> /dev/null; then
    brew install ffmpeg
elif command -v yum &> /dev/null; then
    sudo yum install -y ffmpeg
else
    echo -e "${YELLOW}⚠️ Package manager not found. Please install FFmpeg manually${NC}"
fi

# Test FFmpeg installation
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}✅ FFmpeg installed successfully${NC}"
else
    echo -e "${RED}❌ FFmpeg installation failed${NC}"
fi

# Run tests
echo "🧪 Running tests..."
pytest tests/unit/ -v

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Tests failed${NC}"
fi

# Create git hooks directory
echo "🔧 Setting up git hooks..."
mkdir -p .git/hooks

# Development configuration
echo "⚙️ Creating development configuration..."
cat > config/development.yaml << EOF
# Video AI Studio Development Configuration

logging:
  level: DEBUG
  format: json
  output: console

database:
  provider: postgresql
  url: postgresql://videoai:development123@localhost:5432/videoaistudio

redis:
  url: redis://localhost:6379/0

ai:
  # Use mock services in development to avoid API costs
  use_mock: true
  mock_delay: 1.0

video_processing:
  max_concurrent: 2
  temp_dir: ./data/processing

email:
  provider: console  # Print emails to console in development

features:
  enable_silent_detection: true
  enable_translation: true
  enable_video_styles: true
  enable_ai_thumbnails: true

limits:
  free_tier:
    videos_per_month: 10  # Increased for development
    max_video_length: 300  # 5 minutes
  development_override: true
EOF

echo -e "${GREEN}✅ Development configuration created${NC}"

# Create VS Code settings
echo "⚙️ Configuring VS Code..."
mkdir -p .vscode

cat > .vscode/settings.json << EOF
{
    "python.defaultInterpreterPath": "\${workspaceFolder}/.venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "files.exclude": {
        "**/__pycache__": true,
        "**/.pytest_cache": true
    }
}
EOF

echo -e "${GREEN}✅ VS Code configured${NC}"

# Final instructions
echo ""
echo -e "${GREEN}🎉 Development environment setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Update API keys in .env file:"
echo "   - OpenAI API key"
echo "   - Google API key"
echo "   - Stability AI API key"
echo "   - Stripe keys (test mode)"
echo "   - Firebase credentials"
echo ""
echo "2. Start the development server:"
echo "   flask run"
echo ""
echo "3. Start Celery worker (in separate terminal):"
echo "   celery -A tasks.celery_app worker --loglevel=info"
echo ""
echo "4. Access the application at: http://localhost:5000"
echo ""
echo "Happy coding! 🚀"