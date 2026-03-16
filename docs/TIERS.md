### **docs/TIERS.md**
```markdown
# 🎯 Tier Specifications

This document details the tier specifications for Video AI Studio.

## Overview

Video AI Studio offers 5 tiers:
- **Free**: Limited features for testing
- **Starter** ($24/month): For casual creators
- **Pro** ($79/month): For professionals
- **Plus** ($250/month): For power users and small teams
- **Enterprise** (Custom): For large organizations

## Detailed Specifications

### Free Tier
- **Price**: $0/month
- **Monthly Videos**: 3
- **Max Video Length**: 3 minutes
- **Output Quality**: 720p
- **AI Thumbnails**: 1 image (SD3.5-medium, 20 steps)
- **Extracted Thumbnails**: 5 frames
- **Video Styles**: 3 basic styles (Cinematic, Educational, Gaming)
- **Text Generation**: Gemini 1.5 Flash
- **Translation**: All 100+ languages (googletrans)
- **Retention**: 24 hours
- **Processing Queue**: Normal priority
- **Cost to Process**: ~$0.037 (speech) / ~$0.012 (silent)

### Starter Tier ($24/month)
- **Monthly Videos**: "Process more videos" (~50/month)
- **Max Video Length**: 30 minutes
- **Output Quality**: 1080p
- **AI Thumbnails**: 3 images (SD3.5-medium, 30 steps)
- **Extracted Thumbnails**: 8 frames
- **Video Styles**: All 20+ styles
- **Text Generation**: Gemini 1.5 Flash
- **Translation**: All 100+ languages
- **Retention**: 7 days
- **Processing Queue**: Priority
- **Silent Video Analysis**: 2 frames with Gemini Vision

### Pro Tier ($79/month)
- **Monthly Videos**: 100
- **Max Video Length**: 60 minutes
- **Output Quality**: 4K
- **AI Thumbnails**: 5 images (SD-XL, 40 steps)
- **Extracted Thumbnails**: 15 frames
- **Video Styles**: All premium styles
- **Text Generation**: Gemini 1.5 Pro + GPT-4 fallback
- **Translation**: All 100+ languages
- **Retention**: 30 days
- **Processing Queue**: Express
- **Silent Video Analysis**: 3 frames analysis
- **Max FPS**: Up to 60fps interpolation

### Plus Tier ($250/month)
- **Monthly Videos**: 500
- **Max Video Length**: 120 minutes (2 hours)
- **Output Quality**: 4K + HDR
- **AI Thumbnails**: 10 images (SD3.6-Turbo, 50 steps)
- **Extracted Thumbnails**: 25 frames
- **Video Styles**: All premium + custom requests
- **Text Generation**: GPT-4 Turbo primary
- **Translation**: All 100+ languages + batch translation
- **Retention**: 90 days
- **Processing Queue**: VIP (always first)
- **Silent Video Analysis**: 5 frames + full video analysis
- **Priority Support**: Dedicated channel

### Enterprise Tier (Custom Pricing)
- **Everything**: Unlimited
- **Quality**: Highest available
- **White-label**: Option available
- **On-premise**: Deployment option
- **Support**: Dedicated account manager
- **SLAs**: Guaranteed uptime
- **Custom Features**: On request

## Feature Comparison Matrix

| Feature | Free | Starter | Pro | Plus | Enterprise |
|---------|------|---------|-----|------|------------|
| **Price/month** | $0 | $24 | $79 | $250 | Custom |
| **Monthly Videos** | 3 | ~50 | 100 | 500 | Unlimited |
| **Max Length** | 3 min | 30 min | 60 min | 120 min | Custom |
| **Output Quality** | 720p | 1080p | 4K | 4K+HDR | Highest |
| **AI Thumbnails** | 1 (20 steps) | 3 (30 steps) | 5 (40 steps) | 10 (50 steps) | Unlimited |
| **Video Styles** | 3 basic | All | All premium | All + custom | Custom |
| **Text Model** | Gemini Flash | Gemini Flash | Gemini Pro + GPT-4 | GPT-4 Turbo | Custom |
| **Retention** | 24h | 7 days | 30 days | 90 days | Custom |
| **Priority** | Normal | Priority | Express | VIP | Highest |
| **Translation** | ✓ 100+ langs | ✓ 100+ langs | ✓ 100+ langs | ✓ Batch | ✓ Advanced |
| **Silent Analysis** | - | 2 frames | 3 frames | 5 frames | Full |

## Cost Analysis

### Processing Costs (5-minute video)

| Tier | Speech Video | Silent Video | Savings |
|------|--------------|--------------|---------|
| Free | $0.037 | $0.012 | 69% |
| Starter | $0.037 | $0.012 | 69% |
| Pro | $0.045 | $0.015 | 67% |
| Plus | $0.055 | $0.018 | 67% |

### Profit Margins (at 500 users)

| Tier | Users | Revenue | Cost | Profit | Margin |
|------|-------|---------|------|--------|--------|
| Free | 200 | $0 | $74 | -$74 | N/A |
| Starter | 150 | $3,600 | $555 | $3,045 | 84.6% |
| Pro | 100 | $7,900 | $1,500 | $6,400 | 81.0% |
| Plus | 40 | $10,000 | $720 | $9,280 | 92.8% |
| Enterprise | 10 | $9,990 | $300 | $9,690 | 97.0% |
| **Total** | **500** | **$31,490** | **$3,149** | **$28,341** | **90.0%** |

## Upgrade Paths

### Free → Starter
- **Cost**: $24/month
- **Benefits**: 16x more videos, 10x longer videos, 1080p quality, priority processing
- **Best for**: Users consistently hitting free tier limits

### Starter → Pro
- **Cost**: $55/month additional
- **Benefits**: 2x more videos, 4K quality, better AI models, express processing
- **Best for**: Professionals needing higher quality and volume

### Pro → Plus
- **Cost**: $171/month additional
- **Benefits**: 5x more videos, 4K+HDR, GPT-4 Turbo, VIP processing
- **Best for**: Power users and small teams

### Plus → Enterprise
- **Cost**: Custom (starts at $999/month)
- **Benefits**: Unlimited everything, white-label, dedicated support, SLAs
- **Best for**: Large organizations and agencies

## Tier Enforcement

### Soft Limits
- **Monthly Videos**: Users see "Process more videos" message when nearing limits
- **Video Length**: Uploads are rejected if exceeding tier limits
- **Quality**: Automatically downgraded to tier maximum

### Hard Limits
- **API Rate Limits**: Strictly enforced per tier
- **Concurrent Processing**: Limited based on tier priority
- **Storage Retention**: Automatic deletion after retention period

## Configuration

Tier specifications are configured in `config/tier_config.yaml`:

```yaml
free:
  price: 0
  videos_per_month: 3
  max_length_minutes: 3
  quality: 720p
  ai_thumbnails: 1
  extracted_thumbnails: 5
  video_styles: ["cinematic", "educational", "gaming"]
  text_model: gemini-flash
  retention_days: 1
  priority: 1

starter:
  price: 24
  videos_per_month: 50
  max_length_minutes: 30
  quality: 1080p
  ai_thumbnails: 3
  extracted_thumbnails: 8
  video_styles: all
  text_model: gemini-flash
  retention_days: 7
  priority: 3