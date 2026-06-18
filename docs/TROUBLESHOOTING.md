🔧 Video AI Studio - Troubleshooting Guide

This guide helps you diagnose and fix common issues with the Video AI Studio SaaS platform.
🚨 Quick Troubleshooting Checklist
Before You Begin:

    ✅ Check if all services are running: docker-compose ps

    ✅ Verify environment variables are set: cat .env

    ✅ Check logs for errors: docker-compose logs --tail=50

    ✅ Ensure sufficient disk space: df -h

    ✅ Verify internet connectivity for external APIs

📋 Common Issues & Solutions

1. Application Won't Start
   Issue: "Port already in use"
   text

Error: Address already in use

Solution:
bash

# Find what's using the port

sudo lsof -i :5000
sudo lsof -i :6379
sudo lsof -i :5432

# Kill the process

sudo kill -9 <PID>

# Or change ports in .env

FLASK_PORT=5001
REDIS_PORT=6380

Issue: "Missing dependencies"
text

ModuleNotFoundError: No module named '...'

Solution:
bash

# Reinstall dependencies

pip install -r requirements.txt
pip install -r requirements-dev.txt

# Clear pip cache

pip cache purge

# Use virtual environment

python -m venv venv
source venv/bin/activate # Linux/Mac
venv\Scripts\activate # Windows

2. Video Upload Fails
   Issue: "File too large"
   text

FileUploadError: Video file too large. Maximum size is 2048MB

Solution:

    Check tier limits:

        Free: 100MB

        Starter: 500MB

        Pro: 2GB

        Plus: 5GB

        Enterprise: 10GB

    Compress video before upload:
    bash

# Using FFmpeg

ffmpeg -i input.mp4 -vcodec libx264 -crf 28 compressed.mp4

Increase limit in config:
yaml

# config/video_quality.yaml

max_file_size:
free: 100MB
starter: 500MB
pro: 2048MB
plus: 5120MB
enterprise: 10240MB

Issue: "Invalid file format"
text

InvalidVideoFormatError: File extension .mkv not allowed

Solution:

    Convert to supported format:
    bash

ffmpeg -i input.mkv -c:v libx264 -c:a aac output.mp4

Add format to allowed list:
python

# src/app/config.py

ALLOWED_EXTENSIONS = {
'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'mpeg', 'mpg',
'm4v', '3gp', 'ogv' # Add your format here
}

3. Video Processing Stuck
   Issue: "Processing stuck at 0%"
   text

Status: processing (0% for 10+ minutes)

Solution:

    Check Celery workers:
    bash

# View worker status

celery -A tasks.celery_app status

# Restart workers

docker-compose restart celery_worker

# Check queue

redis-cli -h localhost -p 6379

> KEYS _queue_
> LLEN celery

Check GPU availability (for style processing):
bash

# Test GPU

python -c "import torch; print(torch.cuda.is_available())"

# If GPU not available, fallback to CPU

export USE_GPU=false

Increase timeout limits:
python

# tasks/celery_app.py

task_time_limit = 60 _ 60 # 60 minutes
task_soft_time_limit = 50 _ 60 # 50 minutes

Issue: "Out of memory"
text

MemoryError: Unable to allocate array with shape...

Solution:

    Reduce video resolution:
    bash

ffmpeg -i input.mp4 -vf "scale=1280:720" -c:a copy output.mp4

Increase Docker memory:
yaml

# docker-compose.yml

services:
celery_worker:
deploy:
resources:
limits:
memory: 8G

Use memory-efficient processing:
python

# In video processing settings

settings = {
'chunk_size': 100, # Process in chunks
'use_streaming': True,
'max_memory_mb': 2048
}

4. AI Services Not Working
   Issue: "API key invalid"
   text

ExternalServiceError: OpenAI error: Invalid API key

Solution:

    Verify API keys:
    bash

# Check .env file

cat .env | grep API_KEY

# Test API keys

curl https://api.openai.com/v1/models \
 -H "Authorization: Bearer $OPENAI_API_KEY"

Check rate limits:
bash

# OpenAI rate limits

# Free trial: 3 RPM, 200 RPD

# Pay-as-you-go: 60 RPM, 10k RPD

# Reset if needed

# Wait 1 minute and retry

Use fallback providers:
python

# In providers configuration

AI_TEXT_PROVIDER=gemini-flash # Fallback to Gemini

Issue: "Translation service unavailable"
text

TranslationError: Service unavailable

Solution:

    googletrans fallback issues:
    python

# Use alternative translation service

from deep_translator import GoogleTranslator

translator = GoogleTranslator(source='auto', target='en')
result = translator.translate(text)

Install/update dependencies:
bash

pip install --upgrade googletrans==4.0.0rc1
pip install deep-translator

Disable translation temporarily:
bash

export ENABLE_TRANSLATION=false

5. Database Issues
   Issue: "Firebase connection failed"
   text

DatabaseError: Failed to connect to Firebase

Solution:

    Check credentials:
    bash

# Verify service account file

ls -la $FIREBASE_CREDENTIALS_PATH

# Test connection

python -c "
import firebase_admin
from firebase_admin import credentials, firestore
cred = credentials.Certificate('$FIREBASE_CREDENTIALS_PATH')
firebase_admin.initialize_app(cred)
db = firestore.client()
print('Connected successfully')
"

Switch to PostgreSQL (alternative):
bash

# Update .env

DATABASE_PROVIDER=postgresql
POSTGRES_URL=postgresql://user:pass@localhost:5432/video_ai

# Run migrations

alembic upgrade head

Use local SQLite for development:
python

# In development config

DATABASE_PROVIDER=sqlite
SQLITE_PATH=./data/video_ai.db

Issue: "Redis connection lost"
text

RedisError: Connection refused

Solution:

    Check Redis service:
    bash

# Is Redis running?

docker-compose ps redis

# Restart Redis

docker-compose restart redis

# Clear Redis cache

redis-cli FLUSHALL

Increase Redis memory:
yaml

# docker/redis/redis.conf

maxmemory 1gb
maxmemory-policy allkeys-lru

Use different Redis DB:
bash

REDIS_URL=redis://localhost:6379/1 # Use DB 1 instead of 0

6. Payment/Subscription Issues
   Issue: "Stripe webhook failing"
   text

PaymentError: Webhook signature verification failed

Solution:

    Verify webhook secret:
    bash

# Get webhook secret from Stripe dashboard

stripe listen --forward-to localhost:5000/api/v1/billing/webhook/stripe

# Update .env

STRIPE*WEBHOOK_SECRET=whsec*...

Test webhook locally:
bash

# Install Stripe CLI

stripe login
stripe listen --forward-to localhost:5000/webhook

# Trigger test event

stripe trigger payment_intent.succeeded

Check endpoint accessibility:
bash

# Webhook must be publicly accessible

ngrok http 5000 # For local testing

Issue: "Subscription not updating"
text

User tier not upgraded after payment

Solution:

    Check Stripe dashboard:
    bash

# View subscriptions

stripe subscriptions list

# Check webhook deliveries

stripe events list --type=invoice.payment_succeeded

Manual tier update:
bash

# Use CLI to update tier

flask upgrade-tier --user-id USER_ID --tier pro

Check billing tasks:
bash

# Run billing tasks manually

celery -A tasks.celery_app call tasks.billing_tasks.process_subscription_renewals

7. Email Service Issues
   Issue: "Emails not sending"
   text

EmailError: Failed to send email

Solution:

    Check email provider:
    bash

# Test SendGrid

curl --request GET \
 --url https://api.sendgrid.com/v3/user/email \
 --header "Authorization: Bearer $SENDGRID_API_KEY"

# Switch to Resend

EMAIL*PROVIDER=resend
RESEND_API_KEY=re*...

Use console for development:
bash

EMAIL_PROVIDER=console # Prints emails to console

    Check spam folder:

        Whitelist your domain

        Configure SPF/DKIM records

        Use verified sender email

8. Real-time Updates Not Working
   Issue: "WebSocket disconnected"
   text

WebSocketError: Connection closed

Solution:

    Check Socket.IO configuration:
    python

# In app config

SOCKETIO_MESSAGE_QUEUE=redis://redis:6379/0
SOCKETIO_ASYNC_MODE=gevent

Enable CORS for WebSocket:
python

socketio = SocketIO(
app,
cors_allowed_origins="\*",
async_mode='gevent',
message_queue='redis://'
)

Check client-side connection:
javascript

// In static/js/realtime-updates.js
const socket = io('http://localhost:5000', {
transports: ['websocket', 'polling'],
reconnection: true,
reconnectionDelay: 1000
});

9. Performance Issues
   Issue: "Slow video processing"
   text

Processing takes too long (>10 minutes for 5-minute video)

Solution:

    Optimize FFmpeg settings:
    python

# Use faster presets for lower tiers

PRESET_MAP = {
'free': 'ultrafast',
'starter': 'veryfast',
'pro': 'medium',
'plus': 'slow'
}

Enable parallel processing:
yaml

# docker-compose.yml

celery_worker:
command: celery -A tasks.celery_app worker --loglevel=info --concurrency=4

Use GPU acceleration:
bash

# Install GPU dependencies

pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Enable GPU

USE_GPU=true

Issue: "High memory usage"
text

Memory usage >80% during processing

Solution:

    Monitor memory:
    bash

# Monitor Docker containers

docker stats

# Monitor system

htop
free -h

Set memory limits:
yaml

# docker-compose.prod.yml

services:
web:
deploy:
resources:
limits:
memory: 2G
cpus: '1.0'

Optimize video processing:
python

# Process in chunks

chunk_size = 100 # frames
use_low_memory_mode = True

10. Deployment Issues
    Issue: "Docker build failing"
    text

Docker build error: Failed to build image

Solution:

    Clear Docker cache:
    bash

docker system prune -a
docker builder prune

Check Dockerfile syntax:
dockerfile

# Use specific Python version

FROM python:3.11-slim

# Copy requirements first for caching

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

Build with no cache:
bash

docker-compose build --no-cache

Issue: "Railway/Fly.io deployment failing"
text

Deployment failed: Build error

Solution:

    Check railway.toml/fly.toml:
    toml

# railway.toml

[build]
builder = "nixpacks"

[deploy]
startCommand = "gunicorn app:app"

Increase build timeout:
toml

# railway.toml

[build]
timeout = 600 # 10 minutes

Check build logs:
bash

# Railway

railway logs --tail=100

# Fly.io

fly logs

11. Monitoring & Logging Issues
    Issue: "No logs appearing"
    text

Application running but no logs in console/files

Solution:

    Check log configuration:
    python

# In app config

LOG_LEVEL = "DEBUG" # Change to DEBUG for more logs
LOG_FILE = "logs/video_ai_studio.log"

Enable verbose logging:
bash

# Start with debug mode

FLASK_ENV=development python app.py

# Or with Docker

docker-compose logs -f --tail=50 web

Check log permissions:
bash

# Ensure logs directory exists

mkdir -p logs
chmod 755 logs

Issue: "Metrics endpoint not working"
text

Prometheus metrics not available at /metrics

Solution:

    Enable metrics collection:
    python

# In app config

ENABLE_METRICS = True
PROMETHEUS_MULTIPROC_DIR = "/tmp"

Check Prometheus configuration:
yaml

# prometheus.yml

scrape_configs:

- job_name: 'video-ai-studio'
  static_configs:
  - targets: ['localhost:5000']

12. Security Issues
    Issue: "JWT tokens expiring too quickly"
    text

UnauthorizedError: Token has expired

Solution:

    Increase token expiration:
    python

# In app config

JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

Implement token refresh:
python

# In auth endpoints

@app.route('/auth/refresh', methods=['POST'])
def refresh_token():
refresh_token = request.json.get('refresh_token') # Validate and issue new access token

Issue: "CORS errors"
text

CORS error: No 'Access-Control-Allow-Origin' header

Solution:

    Configure CORS properly:
    python

CORS_ORIGINS = [
"http://localhost:3000",
"http://localhost:5000",
"https://yourdomain.com"
]

Allow specific headers:
python

CORS_ALLOW_HEADERS = [
"Content-Type",
"Authorization",
"X-Requested-With",
"Accept"
]

🔍 Diagnostic Tools
Quick Health Check Script
bash

#!/bin/bash

# save as check_health.sh

echo "🔍 Video AI Studio Health Check"
echo "================================"

# Check Docker services

echo "1. Checking Docker services..."
docker-compose ps

# Check Redis

echo -e "\n2. Checking Redis..."
redis-cli -h localhost -p 6379 ping

# Check Celery

echo -e "\n3. Checking Celery..."
celery -A tasks.celery_app inspect active

# Check API

echo -e "\n4. Checking API..."
curl -s http://localhost:5000/health | jq .

# Check disk space

echo -e "\n5. Checking disk space..."
df -h /tmp

# Check memory

echo -e "\n6. Checking memory..."
free -h

echo -e "\n✅ Health check complete!"

Log Analysis Commands
bash

# Tail logs from all services

docker-compose logs -f --tail=100

# Search for errors

docker-compose logs web | grep -i error
docker-compose logs celery_worker | grep -i error

# Count errors by type

docker-compose logs web | grep -o "ERROR.\*" | sort | uniq -c

# Monitor in real-time

watch -n 5 'docker-compose logs --tail=10'

Performance Monitoring
bash

# Monitor Docker resources

docker stats

# Monitor CPU/Memory

htop

# Monitor network

iftop

# Monitor disk I/O

iotop

# Check queue length

redis-cli -h localhost -p 6379 LLEN celery

📞 Getting Help

1. Collect Debug Information

Before asking for help, collect this information:
bash

# System information

./scripts/dev/setup.sh --info

# Logs (last 100 lines)

docker-compose logs --tail=100 > debug_logs.txt

# Configuration

cat .env > config.txt
cat docker-compose.yml > docker_config.txt

# Network info

ifconfig > network.txt
netstat -tulpn > ports.txt

2. Common Support Channels

   GitHub Issues: For bug reports and feature requests

   Email Support: support@videoaistudio.com

   Documentation: https://docs.videoaistudio.com

   Community Forum: https://community.videoaistudio.com

3. When to Contact Support

Contact support when:

    ❌ All troubleshooting steps failed

    ❌ Critical security issue found

    ❌ Data loss occurred

    ❌ Production system down > 15 minutes

    ❌ Payment/billing issues affecting users

🛠️ Maintenance Procedures
Weekly Maintenance
bash

# Backup database

./scripts/database/backup.sh

# Cleanup temporary files

./scripts/dev/cleanup.sh

# Update dependencies

pip install -r requirements.txt --upgrade

# Restart services

docker-compose restart

Monthly Maintenance
bash

# Review logs for patterns

./scripts/monitoring/analyze_logs.sh

# Check security updates

./scripts/monitoring/security-scan.sh

# Review and clean old data

./scripts/database/cleanup_old_data.sh

# Update SSL certificates

./docker/nginx/ssl/generate_certs.sh --renew

Emergency Procedures
bash

# 1. Stop all services

docker-compose down

# 2. Backup critical data

tar -czf backup*$(date +%Y%m%d*%H%M%S).tar.gz data/

# 3. Check system health

./scripts/monitoring/check_system.sh

# 4. Restart with clean state

docker-compose up --build --force-recreate

📈 Performance Optimization Tips
For Development:
yaml

# docker-compose.dev.yml

services:
web:
environment: - DEBUG=true - CELERY_ALWAYS_EAGER=true # Run tasks synchronously - USE_GPU=false # Disable GPU in dev

redis:
command: redis-server --maxmemory 256mb

For Production:
yaml

# docker-compose.prod.yml

services:
web:
deploy:
resources:
limits:
memory: 4G
cpus: '2.0'

    environment:
      - WORKER_COUNT=4
      - USE_GPU=true
      - ENABLE_CACHE=true

celery_worker:
deploy:
replicas: 3 # Multiple workers
resources:
limits:
memory: 8G
cpus: '4.0'

Database Optimization:
sql

-- Firebase/PostgreSQL indexes
CREATE INDEX idx_videos_user_id ON videos(user_id);
CREATE INDEX idx_videos_status ON videos(status);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);

🔄 Recovery Procedures
Data Recovery
bash

# 1. Stop services

docker-compose down

# 2. Restore from backup

./scripts/database/restore.sh latest_backup.tar.gz

# 3. Run migrations

./scripts/database/migrate.sh

# 4. Restart services

docker-compose up -d

Service Recovery
bash

# If Redis fails

docker-compose restart redis
redis-cli --cluster check localhost:6379

# If Celery fails

docker-compose restart celery_worker
celery -A tasks.celery_app purge -f

# If web server fails

docker-compose restart web
curl -f http://localhost:5000/health

✅ Final Checklist

Before marking an issue as resolved:

    Issue is reproducible

    Root cause identified

    Solution implemented

    Tested in development

    Tested in staging (if applicable)

    Documentation updated

    No regressions introduced

    Performance not degraded

    Security not compromised

Remember: Always backup your data before making significant changes to the system. If you're unsure about a solution, test it in a development environment first.

For additional help, refer to:

    API Documentation

    Deployment Guide

    Architecture Overview

    GitHub Issues

Last Updated: $(date)
Maintained by: Video AI Studio Team
Version: 1.0.0
