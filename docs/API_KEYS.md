
### **docs/API_KEYS.md**
```markdown
# 🔑 API Keys & External Services Setup

This guide explains how to set up all required API keys and external services for Video AI Studio.

## Required Services

### 1. OpenAI
**For**: Whisper transcription
**Cost**: $0.006 per minute
**Setup**:
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to API Keys
4. Click "Create new secret key"
5. Copy the key (it only shows once!)
6. Set in `.env`: `OPENAI_API_KEY=sk-...`

### 2. Google AI (Gemini)
**For**: Text generation, vision analysis
**Cost**: Free tier available, then pay-as-you-go
**Setup**:
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Click "Get API Key"
3. Create API key
4. Enable Gemini API in Google Cloud Console
5. Set in `.env`: `GOOGLE_API_KEY=...`

### 3. Stability AI
**For**: AI thumbnail generation
**Cost**: Credits-based, first 25 images free
**Setup**:
1. Go to [Stability AI Platform](https://platform.stability.ai/)
2. Sign up for an account
3. Navigate to Account → API Keys
4. Generate new API key
5. Set in `.env`: `STABILITY_API_KEY=sk-...`

### 4. Firebase
**For**: Database (alternative: PostgreSQL)
**Cost**: Free tier available (1GB storage, 50K reads/day)
**Setup**:
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create new project
3. Enable Firestore Database
4. Go to Project Settings → Service Accounts
5. Generate new private key
6. Save JSON file
7. Set in `.env`:


### 5. Stripe
**For**: Payment processing
**Cost**: 2.9% + $0.30 per transaction
**Setup**:
1. Go to [Stripe Dashboard](https://dashboard.stripe.com/)
2. Sign up or log in
3. Get API keys from Developers → API Keys
4. Create webhook endpoint for `https://yourdomain.com/api/v1/billing/webhook/stripe`
5. Set in `.env`:


### 6. Email Service (SendGrid/Resend)
**For**: Transactional emails
**Setup**:

#### Option A: SendGrid
1. Go to [SendGrid](https://sendgrid.com/)
2. Sign up for free tier (100 emails/day)
3. Create API key with "Full Access"
4. Set in `.env`:


#### Option B: Resend
1. Go to [Resend](https://resend.com/)
2. Sign up (free tier available)
3. Get API key
4. Set in `.env`:



## Optional Services

### 7. Redis
**For**: Caching and task queues
**Setup**:
- **Local**: Install Redis locally or use Docker
- **Cloud**: Redis Cloud, Upstash, AWS ElastiCache
- Set in `.env`: `REDIS_URL=redis://localhost:6379/0`

### 8. Cloud Storage
**For**: Video file storage
**Options**:
- **AWS S3**: `s3://bucket-name`
- **Google Cloud Storage**: `gs://bucket-name`
- **Cloudflare R2**: `r2://bucket-name`
- **Local**: `file:///path/to/storage`

### 9. CDN
**For**: Faster video delivery
**Options**:
- Cloudflare
- Bunny.net
- AWS CloudFront
- Google Cloud CDN

### 10. Monitoring
**For**: System monitoring
**Options**:
- **Uptime**: Uptime Robot (free)
- **Errors**: Sentry (free tier)
- **Metrics**: Datadog, New Relic, Prometheus
- **Logs**: Logtail, Papertrail

## Environment Variables Template

## Google Cloud Translate Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "Cloud Translation API"
4. Create Service Account credentials:
   - IAM & Admin → Service Accounts → Create Service Account
   - Add "Cloud Translation User" role
   - Create JSON key → Download
5. Set environment variable:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
Create `.env` file with:

```bash
# Flask
FLASK_APP=src.main:create_app
FLASK_ENV=production
SECRET_KEY=your-secret-key-here

# Database
DATABASE_PROVIDER=firebase
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=/path/to/credentials.json
# Alternative: POSTGRES_URL=postgresql://user:pass@localhost/db

# AI Services
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
STABILITY_API_KEY=sk-...

# Email
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG...
# Alternative: RESEND_API_KEY=re...

# Payment
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Redis
REDIS_URL=redis://localhost:6379/0

# Storage
STORAGE_PROVIDER=local
STORAGE_PATH=/tmp/video_ai

# CDN (optional)
CDN_URL=https://cdn.yourdomain.com

# Monitoring (optional)
SENTRY_DSN=https://...