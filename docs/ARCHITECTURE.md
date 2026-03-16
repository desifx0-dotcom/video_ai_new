
### **docs/ARCHITECTURE.md**
```markdown
# System Architecture

## Overview

Video AI Studio is a cloud-native SaaS platform for AI-powered video processing. The system is designed for high scalability, cost efficiency, and 95%+ profit margins.

## Architecture Principles

1. **Stateless Services**: All services are stateless for horizontal scaling
2. **Cost Optimization**: Smart routing to minimize AI processing costs
3. **Zero Persistent Storage**: Videos are processed and deleted automatically
4. **Provider Abstraction**: Easy switching between external services
5. **Real-time Updates**: WebSocket-based progress updates

## System Architecture Diagram
────────────────────────────────────────────────────────────────────────────┐
│ Client Applications │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────────┐ │
│ │ Web Browser│ │ Mobile App │ │ API │ │ WebSocket │ │
│ │ (SPA) │ │ (Future) │ │ Clients │ │ Clients │ │
│ └────────────┘ └────────────┘ └────────────┘ └────────────────────┘ │
│ │ │ │ │ │
│ └──────────────┼──────────────┼─────────────────────┘ │
│ │ │ │
└────────────────────────┼──────────────┼─────────────────────────────────────┘
│ │
▼ ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Load Balancer / API Gateway │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Cloudflare / Nginx / API Gateway │ │
│ │ • SSL Termination • Rate Limiting • Request Routing │ │
│ │ • CORS Management • Caching • WebSocket Proxying │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
│ │ │
▼ ▼ ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Application Layer │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────────┐ │
│ │ Flask API │ │ WebSocket │ │ Static File Serving │ │
│ │ (Python) │ │ Server │ │ (Nginx / CDN) │ │
│ │ │ │ (Socket.IO) │ │ │ │
│ └──────────────┘ └──────────────┘ └──────────────────────────────────┘ │
│ │ │ │ │
│ └─────────────────────┼─────────────────────┘ │
│ │ │
└───────────────────────────────┼─────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Processing Layer │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Celery Task Queue (Redis) │ │
│ │ ┌─────────────┐ ┌─────────────┐ ┌────────────────────────────┐ │ │
│ │ │ Default │ │ Processing │ │ Priority Queue │ │ │
│ │ │ Queue │ │ Queue │ │ (Pro/Plus/Enterprise) │ │ │
│ │ └─────────────┘ └─────────────┘ └────────────────────────────┘ │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Celery Workers │ │
│ │ ┌─────────────┐ ┌─────────────┐ ┌────────────────────────────┐ │ │
│ │ │ Video │ │ Style │ │ GPU Workers │ │ │
│ │ │ Processing │ │ Processing │ │ (Stable Diffusion) │ │ │
│ │ │ Workers │ │ Workers │ │ │ │ │
│ │ └─────────────┘ └─────────────┘ └────────────────────────────┘ │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ External Services Layer │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────────┐ │
│ │ AI/ML │ │ Storage & │ │ Payment & │ │
│ │ Services │ │ Database │ │ Communication │ │
│ │ • OpenAI │ │ • Firebase │ │ • Stripe │ │
│ │ • Google AI │ │ • PostgreSQL │ │ • SendGrid/Resend │ │
│ │ • Stability │ │ • Redis │ │ • Twilio (SMS) │ │
│ │ AI │ │ • S3/R2 │ │ │ │
│ └──────────────┘ └──────────────┘ └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────

## Component Details

### 1. Web Application (Flask)

**Responsibilities:**
- Handle HTTP requests
- User authentication and authorization
- Request validation
- API routing
- Static file serving

**Key Features:**
- JWT-based authentication
- Rate limiting per tier
- CORS support
- Request/response logging
- Error handling middleware

### 2. WebSocket Server (Socket.IO)

**Responsibilities:**
- Real-time communication
- Processing status updates
- Live progress tracking
- Notification delivery

**Key Features:**
- Room-based communication (per user, per video)
- Automatic reconnection
- Heartbeat monitoring
- Fallback to polling if needed

### 3. Task Queue (Celery + Redis)

**Responsibilities:**
- Asynchronous task processing
- Task prioritization
- Retry logic
- Rate limiting

**Queues:**
- `default`: Free tier videos
- `processing`: Paid tier videos
- `priority`: Pro/Plus/Enterprise videos
- `email`: Email notifications
- `cleanup`: File cleanup tasks

### 4. Worker Services

#### Video Processing Workers
- Handle video upload validation
- Extract metadata
- Detect silent videos
- Coordinate processing pipeline

#### Style Processing Workers
- Apply video styles using FFmpeg
- GPU-accelerated processing
- Quality optimization

#### AI Workers
- Transcription (Whisper API)
- Text generation (Gemini/GPT)
- Image generation (Stable Diffusion)
- Vision analysis (Gemini Vision)

### 5. Database Layer

#### Primary Database (Firebase)
- User data
- Video metadata
- Processing jobs
- Subscriptions

**Why Firebase:**
- Real-time capabilities
- Scalability
- Free tier available
- Easy prototyping

#### Cache (Redis)
- Session storage
- Rate limiting data
- Task queue
- Real-time notifications

#### Future Migration Path:
```yaml
Phase 1: Firebase (prototyping)
Phase 2: Firebase + Redis Cache (scaling)
Phase 3: PostgreSQL + Redis (cost optimization)