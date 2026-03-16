#!/bin/bash

# Video AI Studio Database Restore Script

set -e

echo "🔄 Starting database restore..."

# Configuration
BACKUP_DIR="/backup/database"
RESTORE_FILE=$1

if [ -z "$RESTORE_FILE" ]; then
    echo "❌ Please specify a backup file to restore"
    echo "Usage: $0 <backup_file.sql.gz>"
    exit 1
fi

# Load environment variables
if [ -f "/opt/video-ai-studio/.env" ]; then
    source /opt/video-ai-studio/.env
fi

# Check if backup file exists
if [ ! -f "${BACKUP_DIR}/${RESTORE_FILE}" ]; then
    echo "❌ Backup file not found: ${BACKUP_DIR}/${RESTORE_FILE}"
    
    # Check S3 if local file doesn't exist
    if [ ! -z "${AWS_ACCESS_KEY_ID}" ] && [ ! -z "${AWS_SECRET_ACCESS_KEY}" ]; then
        echo "☁️ Checking S3 for backup file..."
        S3_BUCKET="video-ai-studio-backups"
        
        if aws s3 ls s3://${S3_BUCKET}/database/${RESTORE_FILE} > /dev/null 2>&1; then
            echo "📥 Downloading from S3..."
            aws s3 cp s3://${S3_BUCKET}/database/${RESTORE_FILE} ${BACKUP_DIR}/${RESTORE_FILE}
        else
            echo "❌ Backup file not found in S3 either"
            exit 1
        fi
    else
        exit 1
    fi
fi

# Confirm restore
read -p "Are you sure you want to restore from ${RESTORE_FILE}? This will overwrite current data. (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled"
    exit 0
fi

# Create temporary database for verification
echo "🔍 Verifying backup file..."
TEMP_DB="verify_$(date +%s)"

# Extract database connection details
DB_NAME=$(echo ${DATABASE_URL} | sed -e 's/.*\/\([^?]*\).*/\1/')
DB_USER=$(echo ${DATABASE_URL} | sed -e 's/.*\/\/\([^:]*\):.*/\1/')
DB_PASS=$(echo ${DATABASE_URL} | sed -e 's/.*\/\/[^:]*:\([^@]*\)@.*/\1/')
DB_HOST=$(echo ${DATABASE_URL} | sed -e 's/.*@\([^:]*\):.*/\1/')
DB_PORT=$(echo ${DATABASE_URL} | sed -e 's/.*:\([0-9]*\)\/.*/\1/')

# Create temporary database
PGPASSWORD=${DB_PASS} createdb \
    -h ${DB_HOST} \
    -p ${DB_PORT} \
    -U ${DB_USER} \
    ${TEMP_DB}

# Test restore to temporary database
echo "🧪 Testing restore..."
gunzip -c ${BACKUP_DIR}/${RESTORE_FILE} | \
    PGPASSWORD=${DB_PASS} psql \
        -h ${DB_HOST} \
        -p ${DB_PORT} \
        -U ${DB_USER} \
        -d ${TEMP_DB} \
        --quiet > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Backup file is valid"
    
    # Drop temporary database
    PGPASSWORD=${DB_PASS} dropdb \
        -h ${DB_HOST} \
        -p ${DB_PORT} \
        -U ${DB_USER} \
        ${TEMP_DB}
    
    # Stop application services
    echo "⏹️ Stopping application services..."
    systemctl stop video-ai-studio-web
    systemctl stop video-ai-studio-celery
    systemctl stop video-ai-studio-celery-beat
    
    # Create pre-restore backup
    echo "💾 Creating pre-restore backup..."
    ./scripts/database/backup.sh
    
    # Restore to production database
    echo "🔄 Restoring production database..."
    gunzip -c ${BACKUP_DIR}/${RESTORE_FILE} | \
        PGPASSWORD=${DB_PASS} psql \
            -h ${DB_HOST} \
            -p ${DB_PORT} \
            -U ${DB_USER} \
            -d ${DB_NAME} \
            --quiet
    
    if [ $? -eq 0 ]; then
        echo "✅ Database restored successfully!"
        
        # Run database migrations
        echo "🗄️ Running database migrations..."
        cd /opt/video-ai-studio
        source venv/bin/activate
        flask db upgrade
        
        # Clear Redis cache
        if [ ! -z "${REDIS_URL}" ]; then
            echo "🔴 Clearing Redis cache..."
            REDIS_HOST=$(echo ${REDIS_URL} | sed -e 's/.*\/\/\([^:]*\):.*/\1/')
            REDIS_PORT=$(echo ${REDIS_URL} | sed -e 's/.*:\([0-9]*\)\/.*/\1/')
            redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} FLUSHALL
        fi
        
        # Start application services
        echo "▶️ Starting application services..."
        systemctl start video-ai-studio-web
        systemctl start video-ai-studio-celery
        systemctl start video-ai-studio-celery-beat
        
        # Wait for services to be healthy
        echo "⏳ Waiting for services to be healthy..."
        sleep 10
        
        if curl -f http://localhost/health > /dev/null 2>&1; then
            echo "🎉 Restore completed successfully!"
            
            # Send notification
            if [ ! -z "${SLACK_WEBHOOK_URL}" ]; then
                curl -X POST -H 'Content-type: application/json' \
                    --data "{\"text\":\"✅ Database restored from ${RESTORE_FILE} at $(date)\"}" \
                    ${SLACK_WEBHOOK_URL} > /dev/null 2>&1
            fi
        else
            echo "⚠️ Services started but health check failed"
        fi
        
    else
        echo "❌ Database restore failed"
        
        # Restore from pre-restore backup
        echo "🔄 Restoring from pre-restore backup..."
        LATEST_BACKUP=$(ls -t ${BACKUP_DIR}/*.sql.gz | head -1)
        if [ -f "${LATEST_BACKUP}" ]; then
            gunzip -c ${LATEST_BACKUP} | \
                PGPASSWORD=${DB_PASS} psql \
                    -h ${DB_HOST} \
                    -p ${DB_PORT} \
                    -U ${DB_USER} \
                    -d ${DB_NAME} \
                    --quiet
            
            # Start services
            systemctl start video-ai-studio-web
            systemctl start video-ai-studio-celery
            systemctl start video-ai-studio-celery-beat
            
            echo "✅ Rolled back to pre-restore state"
        fi
        
        exit 1
    fi
    
else
    echo "❌ Backup file verification failed"
    
    # Drop temporary database
    PGPASSWORD=${DB_PASS} dropdb \
        -h ${DB_HOST} \
        -p ${DB_PORT} \
        -U ${DB_USER} \
        ${TEMP_DB}
    
    exit 1
fi