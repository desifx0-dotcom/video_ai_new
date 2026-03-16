"""
Storage service abstraction for temporary file management.
"""
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from core.exceptions import ProcessingError, ConfigurationError
from core.constants import StorageProvider

logger = logging.getLogger(__name__)

class StorageService:
    """Storage service for temporary file management."""
    
    def __init__(self, provider: Optional[str] = None):
        self.provider_name = provider or os.getenv('STORAGE_PROVIDER', 'local').lower()
        self._setup_provider()
        
        # Base directories
        self.base_dir = Path(tempfile.gettempdir()) / 'video_ai_studio'
        self.upload_dir = self.base_dir / 'uploads'
        self.processing_dir = self.base_dir / 'processing'
        self.output_dir = self.base_dir / 'outputs'
        
        # Create directories
        for directory in [self.base_dir, self.upload_dir, self.processing_dir, self.output_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _setup_provider(self):
        """Setup storage provider based on configuration."""
        if self.provider_name == 'local':
            self.provider = LocalStorageProvider()
        elif self.provider_name == 's3':
            self.provider = S3StorageProvider()
        elif self.provider_name == 'gcs':
            self.provider = GCSStorageProvider()
        elif self.provider_name == 'r2':
            self.provider = R2StorageProvider()
        else:
            raise ConfigurationError(f"Unsupported storage provider: {self.provider_name}")
    
    def upload_video(
        self,
        video_path: str,
        video_id: str,
        user_id: str,
        expires_hours: Optional[int] = None
    ) -> str:
        """
        Upload video to storage.
        
        Args:
            video_path: Local path to video file
            video_id: Video ID
            user_id: User ID
            expires_hours: Optional expiry in hours
        
        Returns:
            URL or path to uploaded video
        """
        if not os.path.exists(video_path):
            raise ProcessingError(f"Video file not found: {video_path}")
        
        # Determine expiry
        if expires_hours is None:
            # Default based on tier (would be fetched from user service)
            expires_hours = 24  # Default 24 hours
        
        # Generate filename
        filename = f"{video_id}_{Path(video_path).name}"
        
        # Upload using provider
        try:
            url = self.provider.upload_file(
                file_path=video_path,
                destination=filename,
                metadata={
                    'video_id': video_id,
                    'user_id': user_id,
                    'expires_hours': expires_hours,
                    'uploaded_at': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Uploaded video {video_id} to {url}")
            return url
            
        except Exception as e:
            raise ProcessingError(f"Failed to upload video: {str(e)}", step="storage_upload")
    
    def download_video(self, url_or_path: str, destination: Optional[str] = None) -> str:
        """
        Download video from storage.
        
        Args:
            url_or_path: URL or path to video
            destination: Optional destination path
        
        Returns:
            Local path to downloaded video
        """
        if destination is None:
            destination = tempfile.mktemp(suffix='.mp4', prefix='video_ai_')
        
        try:
            local_path = self.provider.download_file(url_or_path, destination)
            return local_path
            
        except Exception as e:
            raise ProcessingError(f"Failed to download video: {str(e)}", step="storage_download")
    
    def delete_video(self, url_or_path: str) -> bool:
        """Delete video from storage."""
        try:
            return self.provider.delete_file(url_or_path)
        except Exception as e:
            logger.error(f"Failed to delete video {url_or_path}: {str(e)}")
            return False
    
    def schedule_deletion(self, url_or_path: str, delay_hours: int):
        """Schedule video for deletion after delay."""
        # In a production system, this would use a job queue
        # For now, we'll just log it
        deletion_time = datetime.utcnow() + timedelta(hours=delay_hours)
        
        logger.info(f"Scheduled deletion of {url_or_path} at {deletion_time}")
        
        # Store deletion schedule (in production, use a proper queue)
        from providers.firebase_provider import FirebaseProvider
        db = FirebaseProvider()
        
        schedule_id = f"del_{hash(url_or_path)}_{deletion_time.timestamp()}"
        
        db.save('deletion_schedule', schedule_id, {
            'url_or_path': url_or_path,
            'scheduled_time': deletion_time.isoformat(),
            'created_at': datetime.utcnow().isoformat()
        })
    
    def cleanup_expired_files(self):
        """Cleanup expired files from storage."""
        try:
            # Get files scheduled for deletion
            from providers.firebase_provider import FirebaseProvider
            db = FirebaseProvider()
            
            now = datetime.utcnow().isoformat()
            expired = db.query('deletion_schedule', filters={'scheduled_time': {'$lt': now}})
            
            count = 0
            for schedule in expired:
                try:
                    if self.delete_video(schedule['url_or_path']):
                        count += 1
                        db.delete('deletion_schedule', schedule['id'])
                except Exception as e:
                    logger.error(f"Failed to delete scheduled file {schedule['url_or_path']}: {str(e)}")
            
            logger.info(f"Cleaned up {count} expired files")
            return count
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
            return 0
    
    def get_file_info(self, url_or_path: str) -> Dict[str, Any]:
        """Get information about stored file."""
        try:
            return self.provider.get_file_info(url_or_path)
        except Exception as e:
            logger.error(f"Failed to get file info: {str(e)}")
            return {}
    
    def generate_presigned_url(
        self,
        url_or_path: str,
        expires_minutes: int = 60
    ) -> str:
        """Generate presigned URL for temporary access."""
        try:
            return self.provider.generate_presigned_url(url_or_path, expires_minutes)
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return url_or_path  # Return original if presigned URLs not supported
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage statistics."""
        try:
            return self.provider.get_storage_usage()
        except Exception as e:
            logger.error(f"Failed to get storage usage: {str(e)}")
            return {'error': str(e)}
    
    def create_temp_file(self, prefix: str = '', suffix: str = '') -> str:
        """Create a temporary file path."""
        return tempfile.mktemp(prefix=f"video_ai_{prefix}_", suffix=suffix)
    
    def create_temp_dir(self, prefix: str = '') -> str:
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix=f"video_ai_{prefix}_")
        return temp_dir
    
    def cleanup_temp_dir(self, directory: str):
        """Cleanup temporary directory."""
        if os.path.exists(directory):
            shutil.rmtree(directory, ignore_errors=True)
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0
    
    def validate_file(self, file_path: str, max_size: Optional[int] = None) -> bool:
        """Validate file exists and meets size constraints."""
        if not os.path.exists(file_path):
            return False
        
        if max_size is not None:
            file_size = self.get_file_size(file_path)
            return file_size <= max_size
        
        return True

# Storage Provider Implementations

class LocalStorageProvider:
    """Local filesystem storage provider."""
    
    def __init__(self):
        self.storage_dir = Path(tempfile.gettempdir()) / 'video_ai_storage'
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def upload_file(
        self,
        file_path: str,
        destination: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Upload file to local storage."""
        dest_path = self.storage_dir / destination
        
        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        shutil.copy2(file_path, dest_path)
        
        # Store metadata
        if metadata:
            meta_path = dest_path.with_suffix('.meta.json')
            import json
            with open(meta_path, 'w') as f:
                json.dump(metadata, f)
        
        return str(dest_path)
    
    def download_file(self, source: str, destination: str) -> str:
        """Download file from local storage."""
        source_path = Path(source)
        
        if not source_path.exists():
            # Try to find in storage directory
            source_path = self.storage_dir / source
            if not source_path.exists():
                raise FileNotFoundError(f"File not found: {source}")
        
        shutil.copy2(source_path, destination)
        return destination
    
    def delete_file(self, file_path: str) -> bool:
        """Delete file from local storage."""
        path = Path(file_path)
        
        if not path.exists():
            # Try to find in storage directory
            path = self.storage_dir / file_path
        
        if path.exists():
            path.unlink()
            
            # Also delete metadata file if exists
            meta_path = path.with_suffix('.meta.json')
            if meta_path.exists():
                meta_path.unlink()
            
            return True
        
        return False
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get file information."""
        path = Path(file_path)
        
        if not path.exists():
            path = self.storage_dir / file_path
        
        if not path.exists():
            return {}
        
        info = {
            'path': str(path),
            'size': path.stat().st_size,
            'modified': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            'exists': True
        }
        
        # Try to load metadata
        meta_path = path.with_suffix('.meta.json')
        if meta_path.exists():
            import json
            try:
                with open(meta_path, 'r') as f:
                    info['metadata'] = json.load(f)
            except:
                pass
        
        return info
    
    def generate_presigned_url(self, file_path: str, expires_minutes: int) -> str:
        """Generate presigned URL (not needed for local storage)."""
        return file_path
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage statistics."""
        total_size = 0
        file_count = 0
        
        for file_path in self.storage_dir.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1
        
        return {
            'total_size': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'file_count': file_count,
            'storage_dir': str(self.storage_dir)
        }

class S3StorageProvider:
    """AWS S3 storage provider."""
    
    def __init__(self):
        import boto3
        
        self.bucket_name = os.getenv('AWS_S3_BUCKET', 'video-ai-studio')
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=self.region
        )
    
    def upload_file(
        self,
        file_path: str,
        destination: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Upload file to S3."""
        extra_args = {}
        
        if metadata:
            # Convert metadata to S3 metadata format
            s3_metadata = {f'x-amz-meta-{k}': str(v) for k, v in metadata.items()}
            extra_args['Metadata'] = s3_metadata
        
        self.s3_client.upload_file(
            file_path,
            self.bucket_name,
            destination,
            ExtraArgs=extra_args
        )
        
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{destination}"
    
    def download_file(self, source: str, destination: str) -> str:
        """Download file from S3."""
        # Extract key from URL if full URL is provided
        if source.startswith('http'):
            # Parse URL to get key
            from urllib.parse import urlparse
            parsed = urlparse(source)
            key = parsed.path.lstrip('/')
        else:
            key = source
        
        self.s3_client.download_file(self.bucket_name, key, destination)
        return destination
    
    def delete_file(self, file_url: str) -> bool:
        """Delete file from S3."""
        try:
            # Extract key from URL
            from urllib.parse import urlparse
            parsed = urlparse(file_url)
            key = parsed.path.lstrip('/')
            
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception as e:
            logger.error(f"S3 delete failed: {str(e)}")
            return False
    
    def get_file_info(self, file_url: str) -> Dict[str, Any]:
        """Get file information from S3."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(file_url)
            key = parsed.path.lstrip('/')
            
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            
            info = {
                'key': key,
                'size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'content_type': response.get('ContentType', ''),
                'metadata': {
                    k.replace('x-amz-meta-', ''): v 
                    for k, v in response.get('Metadata', {}).items()
                }
            }
            
            return info
        except Exception as e:
            logger.error(f"S3 get info failed: {str(e)}")
            return {}
    
    def generate_presigned_url(self, file_url: str, expires_minutes: int) -> str:
        """Generate presigned URL for S3 object."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(file_url)
            key = parsed.path.lstrip('/')
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': key
                },
                ExpiresIn=expires_minutes * 60
            )
            
            return url
        except Exception as e:
            logger.error(f"S3 presigned URL failed: {str(e)}")
            return file_url
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get S3 storage usage statistics."""
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            
            total_size = 0
            file_count = 0
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    total_size += obj['Size']
                    file_count += 1
            
            return {
                'total_size': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'file_count': file_count,
                'bucket': self.bucket_name
            }
        except Exception as e:
            logger.error(f"S3 storage usage failed: {str(e)}")
            return {'error': str(e)}

class GCSStorageProvider:
    """Google Cloud Storage provider."""
    
    def __init__(self):
        from google.cloud import storage
        
        self.bucket_name = os.getenv('GCS_BUCKET', 'video-ai-studio')
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)
    
    def upload_file(
        self,
        file_path: str,
        destination: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Upload file to GCS."""
        blob = self.bucket.blob(destination)
        
        if metadata:
            blob.metadata = metadata
        
        blob.upload_from_filename(file_path)
        
        return blob.public_url
    
    # Other methods similar to S3 provider...

class R2StorageProvider:
    """Cloudflare R2 storage provider."""
    
    def __init__(self):
        import boto3
        
        self.bucket_name = os.getenv('R2_BUCKET', 'video-ai-studio')
        self.account_id = os.getenv('R2_ACCOUNT_ID')
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{self.account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY')
        )
    
    # Methods similar to S3 provider but with R2 endpoint...
