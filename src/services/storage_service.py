"""
Storage service for local-only file management (no cloud storage).
"""

import os
import shutil
import tempfile
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)


class StorageService:
    """Storage service for local file management only."""
    
    def __init__(self):
        # Base directories for temporary storage
        self.base_dir = Path(tempfile.gettempdir()) / 'video_ai_studio'
        self.upload_dir = self.base_dir / 'uploads'
        self.processing_dir = self.base_dir / 'processing'
        self.output_dir = self.base_dir / 'outputs'
        self.metadata_dir = self.base_dir / 'metadata'
        
        # Create directories
        for directory in [self.base_dir, self.upload_dir, self.processing_dir, 
                          self.output_dir, self.metadata_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Track local file references
        self._file_references = {}  # video_id -> local_path
        
        logger.info(f"StorageService initialized with base dir: {self.base_dir}")
    
    def store_video_metadata(
        self,
        video_id: str,
        user_id: str,
        local_path: str,
        original_filename: str,
        file_size: int,
        duration: float,
        expires_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Store video metadata (not the actual video file).
        
        Args:
            video_id: Video ID
            user_id: User ID
            local_path: Local path where video is stored
            original_filename: Original filename
            file_size: File size in bytes
            duration: Video duration in seconds
            expires_hours: Hours until expiration
        
        Returns:
            Metadata record
        """
        metadata = {
            "video_id": video_id,
            "user_id": user_id,
            "local_path": local_path,
            "original_filename": original_filename,
            "file_size": file_size,
            "duration": duration,
            "expires_at": (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "accessed_at": datetime.utcnow().isoformat(),
            "deleted": False,
        }
        
        # Store metadata in local file
        metadata_path = self.metadata_dir / f"{video_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Store reference
        self._file_references[video_id] = local_path
        
        logger.info(f"Stored metadata for video {video_id} at {local_path}")
        
        return metadata
    
    def get_video_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video metadata by ID."""
        metadata_path = self.metadata_dir / f"{video_id}.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                
            # Update access time
            metadata["accessed_at"] = datetime.utcnow().isoformat()
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            return metadata
        except Exception as e:
            logger.error(f"Failed to read metadata for {video_id}: {e}")
            return None
    
    def get_video_path(self, video_id: str) -> Optional[str]:
        """Get local path for a video."""
        metadata = self.get_video_metadata(video_id)
        if metadata and not metadata.get("deleted", False):
            local_path = metadata.get("local_path")
            if local_path and os.path.exists(local_path):
                return local_path
        return None
    
    def create_temp_upload_path(self, filename: str) -> str:
        """Create a temporary path for uploaded video."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{Path(filename).name}"
        return str(self.upload_dir / safe_filename)
    
    def create_temp_processing_path(self, video_id: str, suffix: str = "") -> str:
        """Create a temporary path for processing."""
        return str(self.processing_dir / f"{video_id}{suffix}")
    
    def create_temp_output_path(self, video_id: str, quality: str = "") -> str:
        """Create a temporary path for output."""
        quality_suffix = f"_{quality}" if quality else ""
        return str(self.output_dir / f"{video_id}{quality_suffix}.mp4")
    
    def save_uploaded_file(self, file_obj, destination: str) -> str:
        """Save uploaded file to local storage."""
        try:
            # Ensure directory exists
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            
            # Save file
            file_obj.save(destination)
            
            logger.info(f"Saved uploaded file to {destination}")
            return destination
            
        except Exception as e:
            raise ProcessingError(f"Failed to save uploaded file: {str(e)}")
    
    def copy_file(self, source: str, destination: str) -> str:
        """Copy file locally."""
        try:
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return destination
        except Exception as e:
            raise ProcessingError(f"Failed to copy file: {str(e)}")
    
    def delete_video(self, video_id: str) -> bool:
        """
        Delete video and its metadata (soft delete).
        
        This only marks as deleted, actual file deletion happens on cleanup.
        """
        metadata = self.get_video_metadata(video_id)
        if not metadata:
            return False
        
        # Mark as deleted
        metadata["deleted"] = True
        metadata["deleted_at"] = datetime.utcnow().isoformat()
        
        metadata_path = self.metadata_dir / f"{video_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Marked video {video_id} as deleted")
        return True
    
    def cleanup_expired_files(self) -> int:
        """Clean up expired files (actual deletion)."""
        count = 0
        
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                # Check if expired
                expires_at = metadata.get("expires_at")
                if expires_at:
                    expires_time = datetime.fromisoformat(expires_at)
                    if datetime.utcnow() > expires_time or metadata.get("deleted", False):
                        # Delete actual file
                        local_path = metadata.get("local_path")
                        if local_path and os.path.exists(local_path):
                            os.remove(local_path)
                            count += 1
                        
                        # Delete metadata
                        metadata_file.unlink()
                        count += 1
                        
                        logger.info(f"Cleaned up video {metadata.get('video_id')}")
                        
            except Exception as e:
                logger.error(f"Cleanup failed for {metadata_file}: {e}")
        
        return count
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage statistics."""
        total_size = 0
        file_count = 0
        
        # Count files in all directories
        for directory in [self.upload_dir, self.processing_dir, self.output_dir]:
            if directory.exists():
                for file_path in directory.rglob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                        file_count += 1
        
        return {
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "file_count": file_count,
            "base_dir": str(self.base_dir),
            "metadata_count": len(list(self.metadata_dir.glob("*.json"))),
        }
    
    def cleanup_temp_dirs(self) -> int:
        """Clean up all temporary directories."""
        count = 0
        
        for directory in [self.upload_dir, self.processing_dir, self.output_dir]:
            try:
                for item in directory.iterdir():
                    if item.is_file():
                        item.unlink()
                        count += 1
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                        count += 1
            except Exception as e:
                logger.error(f"Cleanup failed for {directory}: {e}")
        
        return count
    
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(file_path)
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0