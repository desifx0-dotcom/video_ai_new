# Deployment Guide

This guide covers deployment options for Video AI Studio.

## Overview

Video AI Studio can be deployed using multiple methods:
1. **Docker Compose** (Recommended for production)
2. **Railway.app** (Simplest deployment)
3. **Fly.io** (Good for global scaling)
4. **Manual Deployment** (For custom setups)

## Prerequisites

### Required Services
- **Firebase/Firestore** - Database (Free tier available)
- **Redis** - Cache and message queue
- **External Storage** (Optional) - S3, GCS, or Azure Blob for video storage

### API Keys Required
- **OpenAI API Key** - For Whisper transcription
- **Google AI API Key** - For Gemini text generation
- **Stability AI API Key** - For image generation
- **Stripe API Keys** - For payment processing

## Deployment Methods

### 1. Docker Compose (Production)

#### 1.1 Clone the Repository
```bash
git clone https://github.com/yourusername/video-ai-studio.git
cd video-ai-studio

--concurrency=4 --queues=video_processing,email,default

# Use multiple web servers with load balancer
# Configure Nginx as load balancer
upstream video_ai_servers {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
    }