# Video AI Studio API Documentation

## Overview

Video AI Studio provides a RESTful API for AI-powered video processing. All API endpoints return JSON responses and require authentication via JWT tokens unless otherwise specified.

**Base URL:** `https://api.videoaistudio.com/api/v1`

## Authentication

### Login
```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}