"""
Storage service for decentralized video storage (user's local device).
Server only stores metadata references, actual videos stay on user's device.
Compatible with existing code - no breaking changes.
"""

import os
import shutil
import tempfile
import json
import platform
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import logging

from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)


class StorageService:
    """
    Storage service for decentralized file management.
    
    DESIGN:
    - Videos stored on USER'S LOCAL DEVICE (not server)
    - Server stores ONLY metadata and file references
    - User's Videos/VideoAIStudio/ folder contains all their videos
    - Server temp used ONLY for processing (files deleted after)
    
    This saves server storage costs and ensures user privacy.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StorageService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # === USER'S LOCAL DEVICE STORAGE (Primary) ===
        self._user_storage_base = self._get_user_storage_path()
        
        # === SERVER TEMP STORAGE (Processing only - auto cleaned) ===
        self._temp_base_dir = Path(tempfile.gettempdir()) / 'video_ai_processing'
        self._temp_upload_dir = self._temp_base_dir / 'uploads'
        self._temp_processing_dir = self._temp_base_dir / 'processing'
        self._temp_output_dir = self._temp_base_dir / 'outputs'
        self._metadata_dir = self._temp_base_dir / 'metadata'
        
        # Create all directories
        for directory in [self._temp_upload_dir, self._temp_processing_dir, 
                          self._temp_output_dir, self._metadata_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Track file references for cleanup
        self._file_references = {}
        
        # Create user storage if needed
        self._user_storage_base.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ StorageService initialized")
        logger.info(f"   📁 User storage (primary): {self._user_storage_base}")
        logger.info(f"   🗑️ Temp storage (processing): {self._temp_base_dir}")
    
    def _get_user_storage_path(self) -> Path:
        """
        Get user's local device storage path.
        Videos are stored HERE - NOT on server!
        """
        home = Path.home()
        
        system = platform.system()
        if system == "Windows":
            base = home / "Videos" / "VideoAIStudio"
        elif system == "Darwin":  # macOS
            base = home / "Movies" / "VideoAIStudio"
        else:  # Linux
            base = home / "Videos" / "VideoAIStudio"
        
        return base
    
    # ==================== USER STORAGE METHODS (NEW) ====================
    
    def get_user_dir(self, user_id: str) -> Path:
        """Get user's directory path on local device."""
        user_dir = self._user_storage_base / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def get_video_dir(self, user_id: str, video_id: str) -> Path:
        """Get video's directory path on local device."""
        video_dir = self.get_user_dir(user_id) / video_id
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir
    
    def save_video_to_user_device(
        self, 
        user_id: str, 
        video_id: str, 
        source_path: str, 
        filename: str,
        is_processed: bool = False
    ) -> str:
        """
        Save video to user's local device (primary storage).
        
        Args:
            user_id: User ID
            video_id: Video ID
            source_path: Source file path (temp processing location)
            filename: Original filename
            is_processed: Whether this is a processed video
        
        Returns:
            Path on user's device
        """
        video_dir = self.get_video_dir(user_id, video_id)
        
        if is_processed:
            dest_path = video_dir / "processed.mp4"
        else:
            ext = Path(filename).suffix or ".mp4"
            dest_path = video_dir / f"original{ext}"
        
        # Copy to user's device
        shutil.copy2(source_path, str(dest_path))
        logger.info(f"✅ Saved video to user device: {dest_path}")
        
        return str(dest_path)
    
    def get_video_from_user_device(
        self, 
        user_id: str, 
        video_id: str, 
        file_type: str = "processed"
    ) -> Optional[str]:
        """
        Get video path from user's local device.
        
        Args:
            user_id: User ID
            video_id: Video ID  
            file_type: 'original', 'processed', or specific filename
        
        Returns:
            Path if exists, None otherwise
        """
        video_dir = self.get_video_dir(user_id, video_id)
        
        if file_type == "original":
            # Look for any original video file
            for ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                path = video_dir / f"original{ext}"
                if path.exists():
                    return str(path)
            return None
        elif file_type == "processed":
            # Look for processed video
            for pattern in ['processed*.mp4', 'output*.mp4']:
                matches = list(video_dir.glob(pattern))
                if matches:
                    return str(matches[0])
            return None
        else:
            # Specific filename
            path = video_dir / file_type
            return str(path) if path.exists() else None
    
    def video_exists_on_user_device(self, user_id: str, video_id: str, file_type: str = "processed") -> bool:
        """Check if video exists on user's local device."""
        path = self.get_video_from_user_device(user_id, video_id, file_type)
        return path is not None and os.path.exists(path)
    
    def delete_from_user_device(self, user_id: str, video_id: str) -> bool:
        """Delete all video files for a video from user's device."""
        video_dir = self.get_video_dir(user_id, video_id)
        
        if not video_dir.exists():
            return False
        
        try:
            shutil.rmtree(video_dir)
            logger.info(f"🗑️ Deleted user video: {video_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {video_dir}: {e}")
            return False
    
    def cleanup_expired_user_videos(self, retention_days: int = 7) -> int:
        """
        Clean up expired videos from user's local devices.
        
        Args:
            retention_days: Days to keep videos before deletion
        
        Returns:
            Number of videos deleted
        """
        deleted_count = 0
        cutoff = datetime.now() - timedelta(days=retention_days)
        
        for user_dir in self._user_storage_base.iterdir():
            if not user_dir.is_dir():
                continue
            
            for video_dir in user_dir.iterdir():
                if not video_dir.is_dir():
                    continue
                
                # Check last modified time
                modified = datetime.fromtimestamp(video_dir.stat().st_mtime)
                if modified < cutoff:
                    try:
                        shutil.rmtree(video_dir)
                        deleted_count += 1
                        logger.info(f"🗑️ Cleaned up expired video: {video_dir}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup {video_dir}: {e}")
        
        if deleted_count > 0:
            logger.info(f"🧹 Cleaned up {deleted_count} expired videos from user devices")
        return deleted_count
    
    def get_user_storage_info(self, user_id: str) -> Dict[str, Any]:
        """Get storage usage for a user on their local device."""
        user_dir = self.get_user_dir(user_id)
        
        total_size = 0
        video_count = 0
        
        for video_dir in user_dir.iterdir():
            if video_dir.is_dir():
                video_count += 1
                for file_path in video_dir.rglob("*"):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
        
        return {
            "user_id": user_id,
            "base_path": str(user_dir),
            "video_count": video_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
        }
    
    # ==================== BACKWARD COMPATIBLE METHODS (Keep existing code working) ====================
    
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
        Store video metadata (backward compatible).
        Now also stores reference to user's local device.
        
        NOTE: This no longer stores files in temp - only metadata.
        """
        # Ensure video is on user's device
        if not self.video_exists_on_user_device(user_id, video_id, "original"):
            # Video not on user device, need to move it
            if os.path.exists(local_path):
                self.save_video_to_user_device(
                    user_id=user_id,
                    video_id=video_id,
                    source_path=local_path,
                    filename=original_filename,
                    is_processed=False
                )
        
        # Get user device path
        user_device_path = self.get_video_from_user_device(user_id, video_id, "original")
        
        metadata = {
            "video_id": video_id,
            "user_id": user_id,
            "local_path": user_device_path or local_path,
            "original_filename": original_filename,
            "file_size": file_size,
            "duration": duration,
            "expires_at": (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "accessed_at": datetime.utcnow().isoformat(),
            "deleted": False,
        }
        
        # Store metadata in local file (server-side)
        metadata_path = self._metadata_dir / f"{video_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self._file_references[video_id] = user_device_path or local_path
        
        logger.info(f"📝 Stored metadata for video {video_id} (video on user device)")
        return metadata
    
    def get_video_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video metadata by ID (backward compatible)."""
        metadata_path = self._metadata_dir / f"{video_id}.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Check if video still exists on user device
            if metadata.get("user_id") and metadata.get("video_id"):
                user_id = metadata["user_id"]
                video_id = metadata["video_id"]
                if self.video_exists_on_user_device(user_id, video_id, "original"):
                    metadata["user_device_path"] = self.get_video_from_user_device(
                        user_id, video_id, "original"
                    )
            
            # Update access time
            metadata["accessed_at"] = datetime.utcnow().isoformat()
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return metadata
        except Exception as e:
            logger.error(f"Failed to read metadata for {video_id}: {e}")
            return None
    
    def get_video_path(self, video_id: str) -> Optional[str]:
        """
        Get path for a video (backward compatible).
        Checks user device first, then falls back to stored path.
        """
        metadata = self.get_video_metadata(video_id)
        if not metadata or metadata.get("deleted", False):
            return None
        
        # Try user device first
        user_id = metadata.get("user_id")
        if user_id:
            user_device_path = self.get_video_from_user_device(user_id, video_id, "original")
            if user_device_path:
                return user_device_path
        
        # Fallback to stored path
        local_path = metadata.get("local_path")
        if local_path and os.path.exists(local_path):
            return local_path
        
        return None
    
    def get_processed_video_path(self, user_id: str, video_id: str) -> Optional[str]:
        """Get processed video path from user's device."""
        return self.get_video_from_user_device(user_id, video_id, "processed")
    
    def save_processed_video(self, user_id: str, video_id: str, source_path: str, quality: str = "720p") -> str:
        """Save processed video to user's device."""
        return self.save_video_to_user_device(
            user_id=user_id,
            video_id=video_id,
            source_path=source_path,
            filename=f"processed_{quality}.mp4",
            is_processed=True
        )
    
    # ==================== TEMP FILE MANAGEMENT (Processing only) ====================
    
    def create_temp_upload_path(self, filename: str) -> str:
        """Create a temporary path for uploaded video (processing only)."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{Path(filename).name}"
        temp_path = self._temp_upload_dir / safe_filename
        return str(temp_path)
    
    def create_temp_processing_path(self, video_id: str, suffix: str = "") -> str:
        """Create a temporary path for processing."""
        return str(self._temp_processing_dir / f"{video_id}{suffix}")
    
    def create_temp_output_path(self, video_id: str, quality: str = "") -> str:
        """Create a temporary path for output."""
        quality_suffix = f"_{quality}" if quality else ""
        return str(self._temp_output_dir / f"{video_id}{quality_suffix}.mp4")
    
    def save_uploaded_file(self, file_obj, destination: str) -> str:
        """Save uploaded file to temp location for processing."""
        try:
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            
            if hasattr(file_obj, "save"):
                file_obj.save(destination)
            elif hasattr(file_obj, "read"):
                with open(destination, "wb") as f:
                    while True:
                        chunk = file_obj.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                raise ValueError(f"Cannot save file object of type {type(file_obj)}")
            
            logger.info(f"📁 Saved temp file: {destination}")
            return destination
        except Exception as e:
            raise ProcessingError(f"Failed to save uploaded file: {str(e)}")
    
    def copy_file(self, source: str, destination: str) -> str:
        """Copy file (for processing)."""
        try:
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return destination
        except Exception as e:
            raise ProcessingError(f"Failed to copy file: {str(e)}")
    
    def delete_video(self, video_id: str) -> bool:
        """Delete video and its metadata (soft delete)."""
        metadata = self.get_video_metadata(video_id)
        if not metadata:
            return False
        
        # Mark as deleted
        metadata["deleted"] = True
        metadata["deleted_at"] = datetime.utcnow().isoformat()
        
        metadata_path = self._metadata_dir / f"{video_id}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"📝 Marked video {video_id} as deleted")
        return True
    
    def cleanup_expired_files(self) -> int:
        """Clean up expired temp files and metadata."""
        count = 0
        
        # Clean up metadata
        for metadata_file in self._metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                expires_at = metadata.get("expires_at")
                if expires_at and datetime.utcnow() > datetime.fromisoformat(expires_at):
                    metadata_file.unlink()
                    count += 1
                    logger.info(f"🗑️ Cleaned up expired metadata: {metadata_file.name}")
                    
            except Exception as e:
                logger.error(f"Cleanup failed for {metadata_file}: {e}")
        
        # Clean up temp directories (older than 24 hours)
        for temp_dir in [self._temp_upload_dir, self._temp_processing_dir, self._temp_output_dir]:
            if temp_dir.exists():
                for item in temp_dir.iterdir():
                    try:
                        modified = datetime.fromtimestamp(item.stat().st_mtime)
                        if datetime.utcnow() - modified > timedelta(hours=24):
                            if item.is_file():
                                item.unlink()
                            else:
                                shutil.rmtree(item)
                            count += 1
                    except Exception as e:
                        logger.error(f"Cleanup failed for {item}: {e}")
        
        # Also clean up expired user videos
        user_cleanup = self.cleanup_expired_user_videos(retention_days=30)
        
        logger.info(f"🧹 Cleaned up {count} temp files + {user_cleanup} user videos")
        return count
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage statistics."""
        total_size = 0
        file_count = 0
        
        for directory in [self._temp_upload_dir, self._temp_processing_dir, self._temp_output_dir]:
            if directory.exists():
                for file_path in directory.rglob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                        file_count += 1
        
        # Also check user storage
        user_total_size = 0
        user_video_count = 0
        for user_dir in self._user_storage_base.iterdir():
            if user_dir.is_dir():
                for video_dir in user_dir.iterdir():
                    if video_dir.is_dir():
                        user_video_count += 1
                        for file_path in video_dir.rglob('*'):
                            if file_path.is_file():
                                user_total_size += file_path.stat().st_size
        
        return {
            "temp_storage": {
                "total_size_bytes": total_size,
                "total_size_mb": total_size / (1024 * 1024),
                "file_count": file_count,
            },
            "user_storage": {
                "total_size_bytes": user_total_size,
                "total_size_mb": user_total_size / (1024 * 1024),
                "total_size_gb": user_total_size / (1024 * 1024 * 1024),
                "video_count": user_video_count,
            },
            "base_dir": str(self._temp_base_dir),
            "user_storage_dir": str(self._user_storage_base),
            "metadata_count": len(list(self._metadata_dir.glob("*.json"))),
        }
    
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(file_path)
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        return os.path.getsize(file_path) if os.path.exists(file_path) else 0
    
    def cleanup_temp_dirs(self) -> int:
        """Clean up all temporary directories (for testing)."""
        count = 0
        for directory in [self._temp_upload_dir, self._temp_processing_dir, self._temp_output_dir]:
            try:
                for item in directory.iterdir():
                    if item.is_file():
                        item.unlink()
                    else:
                        shutil.rmtree(item)
                    count += 1
            except Exception as e:
                logger.error(f"Cleanup failed for {directory}: {e}")
        
        logger.info(f"🗑️ Cleaned up {count} temp files")
        return count