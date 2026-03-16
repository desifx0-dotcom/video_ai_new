#!/bin/bash

# Video AI Studio Database Migration Script

set -e

echo "🗄️ Starting database migration..."

# Configuration
ENVIRONMENT=${1:-"production"}
APP_DIR="/opt/video-ai-studio"

# Load environment variables
if [ -f "${APP_DIR}/.env.${ENVIRONMENT}" ]; then
    source ${APP_DIR}/.env.${ENVIRONMENT}
elif [ -f "${APP_DIR}/.env" ]; then
    source ${APP_DIR}/.env
else
    echo "❌ No environment file found"
    exit 1
fi

# Activate virtual environment
if [ -f "${APP_DIR}/venv/bin/activate" ]; then
    source ${APP_DIR}/venv/bin/activate
else
    echo "❌ Virtual environment not found"
    exit 1
fi

# Change to app directory
cd ${APP_DIR}

# Check database connection
echo "🔌 Testing database connection..."
if [ ! -z "${DATABASE_URL}" ]; then
    python3 -c "
import sqlalchemy
from sqlalchemy import create_engine, text

try:
    engine = create_engine('${DATABASE_URL}')
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
    "
else
    echo "❌ No database URL configured"
    exit 1
fi

# Run database migrations
echo "🔄 Running database migrations..."
flask db upgrade

if [ $? -eq 0 ]; then
    echo "✅ Database migrations completed successfully"
    
    # Run data migrations if they exist
    if [ -f "scripts/data_migrations.py" ]; then
        echo "📊 Running data migrations..."
        python scripts/data_migrations.py
        
        if [ $? -eq 0 ]; then
            echo "✅ Data migrations completed successfully"
        else
            echo "⚠️ Data migrations completed with warnings"
        fi
    fi
    
    # Update search paths if needed
    echo "🔍 Updating search paths..."
    python3 -c "
import sqlalchemy
from sqlalchemy import create_engine, text

engine = create_engine('${DATABASE_URL}')
with engine.connect() as conn:
    # Update search path for current session
    conn.execute(text('SET search_path TO public'))
    conn.commit()
print('✅ Search paths updated')
    "
    
    # Create indexes if they don't exist
    echo "📈 Creating/updating indexes..."
    python3 -c "
import sqlalchemy
from sqlalchemy import create_engine, text

engine = create_engine('${DATABASE_URL}')
with engine.connect() as conn:
    # Index for users table
    conn.execute(text('''
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
        CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
    '''))
    
    # Index for videos table
    conn.execute(text('''
        CREATE INDEX IF NOT EXISTS idx_videos_user_id ON videos(user_id);
        CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
        CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(created_at);
        CREATE INDEX IF NOT EXISTS idx_videos_processed_tier ON videos(processed_tier);
    '''))
    
    # Index for processing_jobs table
    conn.execute(text('''
        CREATE INDEX IF NOT EXISTS idx_processing_jobs_video_id ON processing_jobs(video_id);
        CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at ON processing_jobs(created_at);
    '''))
    
    # Index for subscriptions table
    conn.execute(text('''
        CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_current_period_end ON subscriptions(current_period_end);
    '''))
    
    conn.commit()
print('✅ Indexes created/updated')
    "
    
    # Update statistics
    echo "📊 Updating database statistics..."
    python3 -c "
import sqlalchemy
from sqlalchemy import create_engine, text

engine = create_engine('${DATABASE_URL}')
with engine.connect() as conn:
    conn.execute(text('ANALYZE'))
    conn.commit()
print('✅ Database statistics updated')
    "
    
    # Verify migration
    echo "🔍 Verifying migration..."
    python3 -c "
import sqlalchemy
from sqlalchemy import create_engine, inspect, text

engine = create_engine('${DATABASE_URL}')
inspector = inspect(engine)

required_tables = ['users', 'videos', 'processing_jobs', 'subscriptions', 'credit_transactions', 'api_logs']
existing_tables = inspector.get_table_names()

missing_tables = [table for table in required_tables if table not in existing_tables]

if missing_tables:
    print(f'❌ Missing tables: {missing_tables}')
    exit(1)
else:
    print('✅ All required tables exist')
    
# Check table structures
with engine.connect() as conn:
    for table in required_tables:
        result = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
        count = result.scalar()
        print(f'  - {table}: {count} rows')
    "
    
    echo "🎉 Database migration completed successfully!"
    
    # Send notification
    if [ ! -z "${SLACK_WEBHOOK_URL}" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"✅ Database migration completed successfully for ${ENVIRONMENT} environment\"}" \
            ${SLACK_WEBHOOK_URL} > /dev/null 2>&1
    fi
    
else
    echo "❌ Database migration failed"
    exit 1
fi