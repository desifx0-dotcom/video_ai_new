"""
Cleanup tasks for temporary files and expired data.
"""
import os
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from .celery_app import celery_app as celery
from providers.firebase_provider import FirebaseProvider
from services.storage_service import StorageService

logger = logging.getLogger(__name__)

@celery.task
def cleanup_expired_data(days: int = 30) -> Dict[str, Any]:
    """
    Cleanup expired data from the database.
    
    Args:
        days: Delete data older than this many days
    
    Returns:
        Dict with cleanup statistics
    """
    db = FirebaseProvider()
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    stats = {
        'videos_deleted': 0,
        'processing_jobs_deleted': 0,
        'api_logs_deleted': 0,
        'error_logs_deleted': 0,
        'space_freed_mb': 0
    }
    
    try:
        # Cleanup expired videos (soft deleted or scheduled for deletion)
        videos = db.query(
            'videos',
            filters={
                '$or': [
                    {'is_deleted': True},
                    {'scheduled_for_deletion': {'$lt': cutoff_date.isoformat()}}
                ]
            }
        )
        
        for video_data in videos:
            video = dict(video_data)
            
            # Delete from storage
            if video.get('output_video_url'):
                storage_service = StorageService()
                storage_service.delete_video(video['output_video_url'])
            
            # Delete from database
            db.delete('videos', video['id'])
            stats['videos_deleted'] += 1
            
            # Estimate space freed (rough estimate)
            if video.get('output_video_size'):
                stats['space_freed_mb'] += video['output_video_size'] / (1024 * 1024)
        
        # Cleanup old processing jobs
        processing_jobs = db.query(
            'processing_jobs',
            filters={'created_at': {'$lt': cutoff_date.isoformat()}}
        )
        
        for job_data in processing_jobs:
            db.delete('processing_jobs', job_data['id'])
            stats['processing_jobs_deleted'] += 1
        
        # Cleanup old API logs
        api_logs = db.query(
            'api_logs',
            filters={'created_at': {'$lt': cutoff_date.isoformat()}}
        )
        
        for log_data in api_logs:
            db.delete('api_logs', log_data['id'])
            stats['api_logs_deleted'] += 1
        
        # Cleanup old error logs
        error_logs = db.query(
            'error_logs',
            filters={'created_at': {'$lt': cutoff_date.isoformat()}}
        )
        
        for log_data in error_logs:
            db.delete('error_logs', log_data['id'])
            stats['error_logs_deleted'] += 1
        
        logger.info(f"Cleanup completed: {stats}")
        return {'status': 'completed', 'stats': stats}
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'stats': stats}

@celery.task
def cleanup_temporary_files() -> Dict[str, Any]:
    """
    Cleanup temporary files from local filesystem.
    """
    temp_dirs = [
        Path('/tmp/video_ai/uploads'),
        Path('/tmp/video_ai/processing'),
        Path('/tmp/video_ai/outputs'),
        Path('data/uploads'),
        Path('data/processing'),
        Path('data/outputs')
    ]
    
    stats = {
        'directories_cleaned': 0,
        'files_deleted': 0,
        'space_freed_mb': 0,
        'errors': []
    }
    
    try:
        for temp_dir in temp_dirs:
            if temp_dir.exists() and temp_dir.is_dir():
                try:
                    # Delete files older than 24 hours
                    cutoff_time = datetime.now().timestamp() - (24 * 3600)
                    
                    for file_path in temp_dir.rglob('*'):
                        if file_path.is_file():
                            try:
                                file_stat = file_path.stat()
                                
                                # Delete if older than 24 hours
                                if file_stat.st_mtime < cutoff_time:
                                    file_size = file_stat.st_size
                                    file_path.unlink()
                                    
                                    stats['files_deleted'] += 1
                                    stats['space_freed_mb'] += file_size / (1024 * 1024)
                            except Exception as e:
                                stats['errors'].append(f"Error deleting {file_path}: {str(e)}")
                    
                    stats['directories_cleaned'] += 1
                    
                except Exception as e:
                    stats['errors'].append(f"Error cleaning {temp_dir}: {str(e)}")
        
        logger.info(f"Temporary files cleanup completed: {stats}")
        return {'status': 'completed', 'stats': stats}
        
    except Exception as e:
        logger.error(f"Error during temporary files cleanup: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'stats': stats}

@celery.task
def cleanup_failed_videos(max_retries: int = 3) -> Dict[str, Any]:
    """
    Cleanup videos that have failed multiple times.
    
    Args:
        max_retries: Maximum number of retries before cleanup
    """
    db = FirebaseProvider()
    
    stats = {
        'videos_cleaned': 0,
        'videos_retried': 0,
        'errors': []
    }
    
    try:
        # Find videos with status 'failed' and retry_count >= max_retries
        failed_videos = db.query(
            'videos',
            filters={
                'status': 'failed',
                'retry_count': {'$gte': max_retries}
            }
        )
        
        for video_data in failed_videos:
            video = dict(video_data)
            
            try:
                # Delete from storage if exists
                if video.get('output_video_url'):
                    storage_service = StorageService()
                    storage_service.delete_video(video['output_video_url'])
                
                # Mark as permanently failed
                video['status'] = 'failed_permanently'
                video['updated_at'] = datetime.utcnow().isoformat()
                
                db.update('videos', video['id'], video)
                stats['videos_cleaned'] += 1
                
                # Send notification to user
                from .notification_tasks import send_notification
                send_notification.delay(
                    user_id=video['user_id'],
                    notification_type='video_failed_permanently',
                    title='Video Processing Failed Permanently',
                    message=f'Video "{video.get("original_filename", video["id"])}" failed after {max_retries} attempts.',
                    data={'video_id': video['id']}
                )
                
            except Exception as e:
                stats['errors'].append(f"Error cleaning video {video['id']}: {str(e)}")
        
        # Find videos that can be retried
        retryable_videos = db.query(
            'videos',
            filters={
                'status': 'failed',
                'retry_count': {'$lt': max_retries}
            }
        )
        
        for video_data in retryable_videos:
            video = dict(video_data)
            
            try:
                # Retry the video
                from .video_tasks import retry_failed_video
                retry_failed_video.delay(video['id'], video['user_id'])
                stats['videos_retried'] += 1
                
            except Exception as e:
                stats['errors'].append(f"Error retrying video {video['id']}: {str(e)}")
        
        logger.info(f"Failed videos cleanup completed: {stats}")
        return {'status': 'completed', 'stats': stats}
        
    except Exception as e:
        logger.error(f"Error during failed videos cleanup: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'stats': stats}

@celery.task
def cleanup_orphaned_files() -> Dict[str, Any]:
    """
    Cleanup orphaned files that don't have corresponding database records.
    """
    db = FirebaseProvider()
    storage_service = StorageService()
    
    stats = {
        'orphaned_files_found': 0,
        'orphaned_files_deleted': 0,
        'space_freed_mb': 0,
        'errors': []
    }
    
    try:
        # Get all video URLs from database
        all_videos = db.query('videos', filters={})
        valid_urls = {video['output_video_url'] for video in all_videos if video.get('output_video_url')}
        
        # List all files in storage
        storage_files = storage_service.list_files()
        
        for file_url in storage_files:
            if file_url not in valid_urls:
                try:
                    # Delete orphaned file
                    file_size = storage_service.delete_file(file_url)
                    stats['orphaned_files_deleted'] += 1
                    stats['space_freed_mb'] += file_size / (1024 * 1024)
                except Exception as e:
                    stats['errors'].append(f"Error deleting orphaned file {file_url}: {str(e)}")
            
            stats['orphaned_files_found'] += 1
        
        logger.info(f"Orphaned files cleanup completed: {stats}")
        return {'status': 'completed', 'stats': stats}
        
    except Exception as e:
        logger.error(f"Error during orphaned files cleanup: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'stats': stats}

@celery.task
def reset_monthly_usage() -> Dict[str, Any]:

    """
    Reset monthly usage counters for all users.
    Runs on the first day of each month.
    """
    db = FirebaseProvider()
    
    stats = {
        'users_reset': 0,
        'errors': []
    }
    
    try:
        # Get all active users
        users = db.query('users', filters={'is_active': True})
        
        for user_data in users:
            user = dict(user_data)
            
            try:
                # Reset monthly counters
                updates = {
                    'videos_processed_this_month': 0,
                    'updated_at': datetime.utcnow().isoformat()
                }
                
                # For free tier users, also reset credits
                if user.get('tier') == 'free':
                    updates['credits_remaining'] = 0
                
                db.update('users', user['id'], updates)
                stats['users_reset'] += 1
                
                # Send monthly reset notification
                from .email_tasks import send_monthly_summary_email
                send_monthly_summary_email.delay(user['id'])
                
            except Exception as e:
                stats['errors'].append(f"Error resetting user {user['id']}: {str(e)}")
        
        logger.info(f"Monthly usage reset completed: {stats}")
        return {'status': 'completed', 'stats': stats}
        
    except Exception as e:
        logger.error(f"Error during monthly usage reset: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'stats': stats}
    
@celery.task
def cleanup_old_thumbnails(max_age_hours: int = 24):
    """Clean up thumbnail files older than max_age_hours."""
    from pathlib import Path
    import tempfile
    from datetime import datetime, timedelta
    
    thumbnails_dir = Path(tempfile.gettempdir()) / 'video_ai_thumbnails'
    if not thumbnails_dir.exists():
        return
    
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    deleted_count = 0
    
    for file in thumbnails_dir.glob("*.png"):
        # Check if file has expiry file
        expiry_file = thumbnails_dir / f"{file.name}.expiry"
        if expiry_file.exists():
            try:
                with open(expiry_file, "r") as f:
                    expiry_time = datetime.fromisoformat(f.read().strip())
                if expiry_time < datetime.now():
                    file.unlink()
                    expiry_file.unlink()
                    deleted_count += 1
            except:
                # If expiry file is corrupt, check modification time
                mod_time = datetime.fromtimestamp(file.stat().st_mtime)
                if mod_time < cutoff_time:
                    file.unlink()
                    deleted_count += 1
        else:
            # No expiry file, use file modification time
            mod_time = datetime.fromtimestamp(file.stat().st_mtime)
            if mod_time < cutoff_time:
                file.unlink()
                deleted_count += 1
    
    logger.info(f"Cleaned up {deleted_count} expired thumbnails")