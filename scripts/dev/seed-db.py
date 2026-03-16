#!/usr/bin/env python3
"""
Database seeding script for development and testing.
"""
import os
import sys
import random
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from app.extensions import db
from core.domain.entities.user import User, Tier, UserStatus
from core.domain.entities.video import Video, VideoStatus, VideoType
from core.domain.entities.subscription import Subscription, SubscriptionStatus
from core.domain.entities.processing_job import ProcessingJob, JobStatus, JobType
from core.security import SecurityUtils
from faker import Faker

fake = Faker()

def seed_database():
    """Seed the database with test data."""
    print("🌱 Seeding database...")
    
    # Clear existing data
    print("🧹 Clearing existing data...")
    db.clear_all('users')
    db.clear_all('videos')
    db.clear_all('subscriptions')
    db.clear_all('processing_jobs')
    db.clear_all('credit_transactions')
    db.clear_all('api_logs')
    
    # Create test users
    print("👥 Creating test users...")
    users = []
    
    # Admin user
    admin_user = User(
        id="admin_001",
        email="admin@videoaistudio.com",
        hashed_password=SecurityUtils.hash_password("Admin123!"),
        tier=Tier.ENTERPRISE,
        full_name="Admin User",
        credits_remaining=1000,
        monthly_video_limit=10000,
        is_admin=True,
        email_verified_at=datetime.utcnow()
    )
    users.append(admin_user)
    db.save('users', admin_user.id, admin_user.to_dict())
    
    # Test users for each tier
    tiers = [Tier.FREE, Tier.STARTER, Tier.PRO, Tier.PLUS, Tier.ENTERPRISE]
    
    for i, tier in enumerate(tiers):
        for j in range(3 if tier == Tier.ENTERPRISE else 5):
            user_id = f"user_{tier.value}_{i*5 + j}"
            
            user = User(
                id=user_id,
                email=f"test_{tier.value}_{j}@example.com",
                hashed_password=SecurityUtils.hash_password("Test123!"),
                tier=tier,
                full_name=fake.name(),
                credits_remaining=random.randint(0, 100) if tier == Tier.FREE else 1000,
                monthly_video_limit={
                    Tier.FREE: 3,
                    Tier.STARTER: 50,
                    Tier.PRO: 100,
                    Tier.PLUS: 500,
                    Tier.ENTERPRISE: 10000
                }.get(tier, 3),
                videos_processed_this_month=random.randint(0, 10),
                total_videos_processed=random.randint(0, 100),
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 365)),
                last_login=datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
                email_verified_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
            )
            
            users.append(user)
            db.save('users', user.id, user.to_dict())
    
    print(f"✅ Created {len(users)} users")
    
    # Create subscriptions for paid users
    print("💰 Creating subscriptions...")
    subscriptions = []
    
    for user in users:
        if user.tier != Tier.FREE:
            subscription = Subscription(
                id=f"sub_{user.id}",
                user_id=user.id,
                tier=user.tier.value,
                status=SubscriptionStatus.ACTIVE,
                stripe_subscription_id=f"sub_{fake.uuid4()}",
                stripe_customer_id=f"cus_{fake.uuid4()}",
                stripe_price_id=f"price_{fake.uuid4()}",
                current_period_start=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
                current_period_end=datetime.utcnow() + timedelta(days=random.randint(1, 365)),
                amount={
                    Tier.STARTER: 24.00,
                    Tier.PRO: 79.00,
                    Tier.PLUS: 250.00,
                    Tier.ENTERPRISE: 999.00
                }.get(user.tier, 0.00),
                billing_cycle="monthly",
                features={}
            )
            
            subscriptions.append(subscription)
            db.save('subscriptions', subscription.id, subscription.to_dict())
    
    print(f"✅ Created {len(subscriptions)} subscriptions")
    
    # Create test videos
    print("🎥 Creating test videos...")
    videos = []
    video_statuses = [
        VideoStatus.UPLOADED,
        VideoStatus.PROCESSING,
        VideoStatus.COMPLETED,
        VideoStatus.FAILED
    ]
    
    video_types = [VideoType.SPEECH, VideoType.SILENT, VideoType.MUSIC]
    qualities = ["720p", "1080p", "4k", "4k+hdr"]
    styles = ["cinematic", "gaming", "educational", "vlog", "corporate"]
    
    for i, user in enumerate(users):
        # Create 0-5 videos per user
        num_videos = random.randint(0, 5)
        
        for j in range(num_videos):
            video_id = f"video_{user.id}_{j}"
            status = random.choice(video_statuses)
            video_type = random.choice(video_types)
            
            # Generate realistic video data
            duration = random.uniform(30, 600)  # 30 seconds to 10 minutes
            file_size = random.randint(10 * 1024 * 1024, 500 * 1024 * 1024)  # 10MB to 500MB
            
            video = Video(
                id=video_id,
                user_id=user.id,
                original_filename=f"test_video_{i}_{j}.mp4",
                file_size=file_size,
                duration=duration,
                mime_type="video/mp4",
                status=status,
                video_type=video_type,
                priority=random.randint(1, 10),
                
                # AI Processing Results
                transcription=fake.paragraph() if video_type == VideoType.SPEECH else None,
                transcription_language="en" if video_type == VideoType.SPEECH else None,
                title=fake.sentence(),
                description=fake.paragraph(),
                tags=[fake.word() for _ in range(random.randint(1, 5))],
                
                # Thumbnails
                ai_thumbnails=[f"https://example.com/thumb_{video_id}_{k}.jpg" for k in range(random.randint(1, 3))],
                extracted_thumbnails=[f"https://example.com/extracted_{video_id}_{k}.jpg" for k in range(random.randint(3, 8))],
                selected_thumbnail=f"https://example.com/thumb_{video_id}_0.jpg",
                
                # Video Processing
                output_quality=random.choice(qualities),
                output_format="mp4",
                applied_styles=random.sample(styles, random.randint(0, 2)) if status == VideoStatus.COMPLETED else [],
                output_video_url=f"https://storage.example.com/videos/{video_id}.mp4" if status == VideoStatus.COMPLETED else None,
                output_video_size=file_size // 2 if status == VideoStatus.COMPLETED else None,
                
                # Translation
                translated_transcription=fake.paragraph() if random.random() > 0.5 and video_type == VideoType.SPEECH else None,
                translation_language=random.choice(["es", "fr", "de"]) if random.random() > 0.5 else None,
                
                # Processing Metadata
                processing_started=datetime.utcnow() - timedelta(minutes=random.randint(1, 60)) if status != VideoStatus.UPLOADED else None,
                processing_completed=datetime.utcnow() - timedelta(minutes=random.randint(1, 30)) if status == VideoStatus.COMPLETED else None,
                processing_time=random.uniform(30, 300) if status == VideoStatus.COMPLETED else None,
                
                # Cost tracking
                ai_costs={
                    "transcription": random.uniform(0.01, 0.10) if video_type == VideoType.SPEECH else 0,
                    "title_generation": random.uniform(0.001, 0.01),
                    "thumbnail_generation": random.uniform(0.02, 0.05),
                    "translation": random.uniform(0.01, 0.05) if random.random() > 0.5 else 0,
                    "style_application": random.uniform(0.01, 0.10) if status == VideoStatus.COMPLETED and random.random() > 0.5 else 0,
                    "video_processing": random.uniform(0.001, 0.01)
                },
                total_cost=random.uniform(0.05, 0.50),
                
                # Tier Information
                processed_tier=user.tier.value,
                
                # Timestamps
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 30)),
                updated_at=datetime.utcnow() - timedelta(hours=random.randint(0, 24))
            )
            
            videos.append(video)
            db.save('videos', video.id, video.to_dict())
            
            # Create processing job for the video
            if status != VideoStatus.UPLOADED:
                job = ProcessingJob(
                    id=f"job_{video_id}",
                    video_id=video_id,
                    user_id=user.id,
                    job_type=JobType.VIDEO_PROCESSING,
                    status=JobStatus.SUCCESS if status == VideoStatus.COMPLETED else JobStatus.FAILURE if status == VideoStatus.FAILED else JobStatus.STARTED,
                    current_step="completed" if status == VideoStatus.COMPLETED else random.choice(["transcribing", "generating_thumbnails", "applying_styles"]),
                    progress=100 if status == VideoStatus.COMPLETED else random.randint(20, 90),
                    total_steps=7,
                    execution_time=video.processing_time,
                    created_at=video.created_at,
                    started_at=video.processing_started,
                    completed_at=video.processing_completed
                )
                
                db.save('processing_jobs', job.id, job.to_dict())
    
    print(f"✅ Created {len(videos)} videos")
    
    # Create credit transactions
    print("💳 Creating credit transactions...")
    credit_transactions = []
    
    for user in users:
        if user.tier != Tier.FREE:
            # Add credits transaction
            add_transaction = {
                "id": f"credit_add_{user.id}",
                "user_id": user.id,
                "amount": 1000,
                "description": "Initial credits",
                "created_at": datetime.utcnow() - timedelta(days=random.randint(1, 30))
            }
            credit_transactions.append(add_transaction)
            db.save('credit_transactions', add_transaction["id"], add_transaction)
            
            # Deduct credits for video processing
            user_videos = [v for v in videos if v.user_id == user.id]
            for video in user_videos:
                if video.status == VideoStatus.COMPLETED:
                    deduct_transaction = {
                        "id": f"credit_deduct_{video.id}",
                        "user_id": user.id,
                        "video_id": video.id,
                        "amount": -max(1, int(video.duration) // 60),
                        "description": f"Video processing: {video.original_filename}",
                        "created_at": video.processing_completed or video.updated_at
                    }
                    credit_transactions.append(deduct_transaction)
                    db.save('credit_transactions', deduct_transaction["id"], deduct_transaction)
    
    print(f"✅ Created {len(credit_transactions)} credit transactions")
    
    # Create API logs
    print("📝 Creating API logs...")
    api_logs = []
    endpoints = [
        ("/api/v1/videos/upload", "POST"),
        ("/api/v1/videos", "GET"),
        ("/api/v1/auth/login", "POST"),
        ("/api/v1/billing/subscribe", "POST"),
        ("/api/v1/users/profile", "GET")
    ]
    
    for i in range(100):
        endpoint, method = random.choice(endpoints)
        user = random.choice(users) if random.random() > 0.3 else None
        
        log = {
            "id": f"log_{i:06d}",
            "user_id": user.id if user else None,
            "endpoint": endpoint,
            "method": method,
            "status_code": random.choice([200, 200, 200, 201, 400, 401, 403, 404, 500]),
            "processing_time_ms": random.uniform(10, 1000),
            "user_agent": fake.user_agent(),
            "ip_address": fake.ipv4(),
            "created_at": datetime.utcnow() - timedelta(minutes=random.randint(0, 1440))
        }
        
        api_logs.append(log)
        db.save('api_logs', log["id"], log)
    
    print(f"✅ Created {len(api_logs)} API logs")
    
    # Print summary
    print("\n📊 Database seeding complete!")
    print("=" * 50)
    print(f"Users: {len(users)}")
    print(f"Subscriptions: {len(subscriptions)}")
    print(f"Videos: {len(videos)}")
    print(f"Processing Jobs: {len([v for v in videos if v.status != VideoStatus.UPLOADED])}")
    print(f"Credit Transactions: {len(credit_transactions)}")
    print(f"API Logs: {len(api_logs)}")
    print("=" * 50)
    
    # Print test credentials
    print("\n🔐 Test Credentials:")
    print("-" * 30)
    print("Admin: admin@videoaistudio.com / Admin123!")
    print("Free Tier: test_free_0@example.com / Test123!")
    print("Starter Tier: test_starter_0@example.com / Test123!")
    print("Pro Tier: test_pro_0@example.com / Test123!")
    print("Plus Tier: test_plus_0@example.com / Test123!")
    print("Enterprise Tier: test_enterprise_0@example.com / Test123!")
    print("-" * 30)
    
    return True

if __name__ == "__main__":
    try:
        seed_database()
        print("🎉 Database seeded successfully!")
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        sys.exit(1)