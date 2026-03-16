#!/bin/bash

# Video AI Studio Database Backup Script

set -e

echo "💾 Starting database backup..."

# Configuration
BACKUP_DIR="/backup/database"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="backup_${TIMESTAMP}.sql.gz"
S3_BUCKET="video-ai-studio-backups"
RETENTION_DAYS=30

# Load environment variables
if [ -f "/opt/video-ai-studio/.env" ]; then
    source /opt/video-ai-studio/.env
fi

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Backup PostgreSQL
if [ ! -z "${DATABASE_URL}" ]; then
    echo "📦 Backing up PostgreSQL database..."
    
    # Extract database connection details
    DB_NAME=$(echo ${DATABASE_URL} | sed -e 's/.*\/\([^?]*\).*/\1/')
    DB_USER=$(echo ${DATABASE_URL} | sed -e 's/.*\/\/\([^:]*\):.*/\1/')
    DB_PASS=$(echo ${DATABASE_URL} | sed -e 's/.*\/\/[^:]*:\([^@]*\)@.*/\1/')
    DB_HOST=$(echo ${DATABASE_URL} | sed -e 's/.*@\([^:]*\):.*/\1/')
    DB_PORT=$(echo ${DATABASE_URL} | sed -e 's/.*:\([0-9]*\)\/.*/\1/')
    
    # Create backup
    PGPASSWORD=${DB_PASS} pg_dump \
        -h ${DB_HOST} \
        -p ${DB_PORT} \
        -U ${DB_USER} \
        -d ${DB_NAME} \
        --clean \
        --if-exists \
        --no-owner \
        --no-privileges \
        --exclude-table-data='api_logs' \
        --exclude-table-data='system_metrics' \
        | gzip > ${BACKUP_DIR}/${FILENAME}
    
    echo "✅ PostgreSQL backup created: ${BACKUP_DIR}/${FILENAME}"
    
    # Backup Redis if enabled
    if [ ! -z "${REDIS_URL}" ]; then
        echo "🔴 Backing up Redis data..."
        REDIS_BACKUP="redis_backup_${TIMESTAMP}.rdb"
        
        # Get Redis host and port
        REDIS_HOST=$(echo ${REDIS_URL} | sed -e 's/.*\/\/\([^:]*\):.*/\1/')
        REDIS_PORT=$(echo ${REDIS_URL} | sed -e 's/.*:\([0-9]*\)\/.*/\1/')
        
        # Save Redis data
        redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} SAVE
        cp /var/lib/redis/dump.rdb ${BACKUP_DIR}/${REDIS_BACKUP}
        
        echo "✅ Redis backup created: ${BACKUP_DIR}/${REDIS_BACKUP}"
    fi
    
    # Backup Firebase if enabled
    if [ ! -z "${FIREBASE_PROJECT_ID}" ] && [ -f "${FIREBASE_CREDENTIALS_PATH}" ]; then
        echo "🔥 Backing up Firebase data..."
        FIREBASE_BACKUP="firebase_backup_${TIMESTAMP}.json"
        
        # Export Firebase data
        python3 -c "
import firebase_admin
from firebase_admin import credentials, firestore
import json
import sys

cred = credentials.Certificate('${FIREBASE_CREDENTIALS_PATH}')
firebase_admin.initialize_app(cred)
db = firestore.client()

collections = ['users', 'videos', 'subscriptions', 'processing_jobs', 'credit_transactions']
backup_data = {}

for collection in collections:
    docs = db.collection(collection).stream()
    backup_data[collection] = [doc.to_dict() for doc in docs]

with open('${BACKUP_DIR}/${FIREBASE_BACKUP}', 'w') as f:
    json.dump(backup_data, f, indent=2)
        "
        
        echo "✅ Firebase backup created: ${BACKUP_DIR}/${FIREBASE_BACKUP}"
    fi
    
    # Upload to S3 if configured
    if [ ! -z "${AWS_ACCESS_KEY_ID}" ] && [ ! -z "${AWS_SECRET_ACCESS_KEY}" ]; then
        echo "☁️ Uploading backups to S3..."
        
        # Upload PostgreSQL backup
        aws s3 cp ${BACKUP_DIR}/${FILENAME} s3://${S3_BUCKET}/database/${FILENAME}
        
        # Upload Redis backup if exists
        if [ -f "${BACKUP_DIR}/${REDIS_BACKUP}" ]; then
            aws s3 cp ${BACKUP_DIR}/${REDIS_BACKUP} s3://${S3_BUCKET}/redis/${REDIS_BACKUP}
        fi
        
        # Upload Firebase backup if exists
        if [ -f "${BACKUP_DIR}/${FIREBASE_BACKUP}" ]; then
            aws s3 cp ${BACKUP_DIR}/${FIREBASE_BACKUP} s3://${S3_BUCKET}/firebase/${FIREBASE_BACKUP}
        fi
        
        echo "✅ Backups uploaded to S3"
    fi
    
    # Clean up old backups
    echo "🧹 Cleaning up old backups..."
    find ${BACKUP_DIR} -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    find ${BACKUP_DIR} -name "*.rdb" -mtime +${RETENTION_DAYS} -delete
    find ${BACKUP_DIR} -name "*.json" -mtime +${RETENTION_DAYS} -delete
    
    # Clean S3 backups
    if [ ! -z "${AWS_ACCESS_KEY_ID}" ]; then
        aws s3 ls s3://${S3_BUCKET}/database/ | \
            awk '{print $4}' | \
            sort -r | \
            tail -n +$((RETENTION_DAYS + 1)) | \
            while read file; do
                aws s3 rm s3://${S3_BUCKET}/database/${file}
            done
    fi
    
    echo "✅ Backup completed successfully!"
    
else
    echo "❌ No database configuration found"
    exit 1
fi