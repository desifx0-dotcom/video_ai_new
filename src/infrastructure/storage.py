"""
Storage abstraction layer.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, BinaryIO, Union
import os
import tempfile
import shutil
from pathlib import Path
import mimetypes
from datetime import datetime, timedelta
import hashlib

class Storage(ABC):
    """Abstract storage interface."""
    
    @abstractmethod
    def upload(self, 
               file_path: Union[str, Path, BinaryIO],
               destination: str,
               metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload a file to storage."""
        pass
    
    @abstractmethod
    def download(self, 
                 source: str,
                 destination: Union[str, Path]) -> bool:
        """Download a file from storage."""
        pass
    
    @abstractmethod
    def delete(self, source: str) -> bool:
        """Delete a file from storage."""
        pass
    
    @abstractmethod
    def exists(self, source: str) -> bool:
        """Check if file exists in storage."""
        pass
    
    @abstractmethod
    def get_url(self, 
                source: str,
                expires_in: Optional[int] = None) -> str:
        """Get URL for file, optionally signed/expiring."""
        pass
    
    @abstractmethod
    def list_files(self, 
                   prefix: str = "",
                   max_results: int = 1000) -> List[Dict[str, Any]]:
        """List files in storage."""
        pass
    
    @abstractmethod
    def get_metadata(self, source: str) -> Dict[str, Any]:
        """Get file metadata."""
        pass
    
    @abstractmethod
    def copy(self, 
             source: str,
             destination: str) -> bool:
        """Copy file within storage."""
        pass
    
    @abstractmethod
    def move(self, 
             source: str,
             destination: str) -> bool:
        """Move file within storage."""
        pass
    
    def upload_bytes(self, 
                    data: bytes,
                    destination: str,
                    metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload bytes data to storage."""
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(data)
            temp_file.flush()
            
            try:
                return self.upload(temp_file.name, destination, metadata)
            finally:
                os.unlink(temp_file.name)
    
    def download_bytes(self, source: str) -> Optional[bytes]:
        """Download file as bytes."""
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            try:
                if self.download(source, temp_file.name):
                    with open(temp_file.name, 'rb') as f:
                        return f.read()
            finally:
                os.unlink(temp_file.name)
        return None
    
    def upload_string(self, 
                     data: str,
                     destination: str,
                     metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload string data to storage."""
        return self.upload_bytes(data.encode('utf-8'), destination, metadata)
    
    def download_string(self, source: str) -> Optional[str]:
        """Download file as string."""
        data = self.download_bytes(source)
        if data is not None:
            return data.decode('utf-8')
        return None
    
    def calculate_hash(self, 
                      source: str,
                      algorithm: str = 'sha256') -> Optional[str]:
        """Calculate file hash."""
        data = self.download_bytes(source)
        if data is None:
            return None
        
        hash_func = hashlib.new(algorithm)
        hash_func.update(data)
        return hash_func.hexdigest()

class LocalStorage(Storage):
    """Local filesystem storage implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        self.base_path = Path(config.get('base_path', 'data/storage')).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # URL configuration
        self.base_url = config.get('base_url', '/storage')
        self.serve_static = config.get('serve_static', True)
        
        # Cleanup configuration
        self.cleanup_days = config.get('cleanup_days', 30)
    
    def upload(self, 
               file_path: Union[str, Path, BinaryIO],
               destination: str,
               metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload a file to local storage."""
        # Clean destination path
        destination = self._clean_path(destination)
        dest_path = self.base_path / destination
        
        # Create parent directories
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle different input types
        if hasattr(file_path, 'read'):
            # File-like object
            with open(dest_path, 'wb') as dest_file:
                shutil.copyfileobj(file_path, dest_file)
        else:
            # File path
            shutil.copy2(str(file_path), str(dest_path))
        
        # Store metadata
        if metadata:
            metadata_path = dest_path.with_suffix('.meta.json')
            import json
            with open(metadata_path, 'w') as f:
                json.dump({
                    'metadata': metadata,
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'original_filename': os.path.basename(str(file_path))
                }, f)
        
        return destination
    
    def download(self, 
                 source: str,
                 destination: Union[str, Path]) -> bool:
        """Download a file from local storage."""
        source = self._clean_path(source)
        source_path = self.base_path / source
        
        if not source_path.exists():
            return False
        
        # Create parent directories
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(str(source_path), str(destination))
        return True
    
    def delete(self, source: str) -> bool:
        """Delete a file from local storage."""
        source = self._clean_path(source)
        source_path = self.base_path / source
        
        if not source_path.exists():
            return False
        
        try:
            # Delete main file
            source_path.unlink()
            
            # Delete metadata file if exists
            metadata_path = source_path.with_suffix('.meta.json')
            if metadata_path.exists():
                metadata_path.unlink()
            
            # Try to remove empty parent directories
            self._cleanup_empty_dirs(source_path.parent)
            
            return True
            
        except Exception:
            return False
    
    def exists(self, source: str) -> bool:
        """Check if file exists in local storage."""
        source = self._clean_path(source)
        source_path = self.base_path / source
        return source_path.exists()
    
    def get_url(self, 
                source: str,
                expires_in: Optional[int] = None) -> str:
        """Get URL for file."""
        source = self._clean_path(source)
        
        if self.serve_static:
            # For development, serve via Flask static route
            return f"{self.base_url}/{source}"
        else:
            # In production, you might use a CDN or signed URLs
            # For now, return a file:// URL
            source_path = self.base_path / source
            return f"file://{source_path.resolve()}"
    
    def list_files(self, 
                   prefix: str = "",
                   max_results: int = 1000) -> List[Dict[str, Any]]:
        """List files in local storage."""
        prefix = self._clean_path(prefix)
        search_path = self.base_path / prefix
        
        if not search_path.exists():
            return []
        
        files = []
        
        for item in search_path.rglob('*'):
            if item.is_file() and not item.name.endswith('.meta.json'):
                rel_path = str(item.relative_to(self.base_path))
                
                # Skip if doesn't match prefix
                if prefix and not rel_path.startswith(prefix):
                    continue
                
                stats = item.stat()
                
                file_info = {
                    'name': rel_path,
                    'size': stats.st_size,
                    'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    'url': self.get_url(rel_path)
                }
                
                # Add metadata if available
                metadata_path = item.with_suffix('.meta.json')
                if metadata_path.exists():
                    import json
                    try:
                        with open(metadata_path, 'r') as f:
                            file_info['metadata'] = json.load(f)
                    except:
                        pass
                
                files.append(file_info)
                
                if len(files) >= max_results:
                    break
        
        return files
    
    def get_metadata(self, source: str) -> Dict[str, Any]:
        """Get file metadata."""
        source = self._clean_path(source)
        source_path = self.base_path / source
        
        if not source_path.exists():
            return {}
        
        metadata = {
            'size': source_path.stat().st_size,
            'modified': datetime.fromtimestamp(source_path.stat().st_mtime).isoformat(),
            'created': datetime.fromtimestamp(source_path.stat().st_ctime).isoformat(),
            'mime_type': mimetypes.guess_type(str(source_path))[0] or 'application/octet-stream'
        }
        
        # Load additional metadata from file
        metadata_path = source_path.with_suffix('.meta.json')
        if metadata_path.exists():
            import json
            try:
                with open(metadata_path, 'r') as f:
                    stored_metadata = json.load(f)
                    metadata.update(stored_metadata)
            except:
                pass
        
        return metadata
    
    def copy(self, 
             source: str,
             destination: str) -> bool:
        """Copy file within local storage."""
        source = self._clean_path(source)
        destination = self._clean_path(destination)
        
        source_path = self.base_path / source
        dest_path = self.base_path / destination
        
        if not source_path.exists():
            return False
        
        try:
            # Create parent directories
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(str(source_path), str(dest_path))
            
            # Copy metadata if exists
            metadata_source = source_path.with_suffix('.meta.json')
            metadata_dest = dest_path.with_suffix('.meta.json')
            
            if metadata_source.exists():
                shutil.copy2(str(metadata_source), str(metadata_dest))
            
            return True
            
        except Exception:
            return False
    
    def move(self, 
             source: str,
             destination: str) -> bool:
        """Move file within local storage."""
        if self.copy(source, destination):
            return self.delete(source)
        return False
    
    def cleanup_old_files(self) -> int:
        """Cleanup files older than cleanup_days."""
        cutoff = datetime.utcnow() - timedelta(days=self.cleanup_days)
        deleted_count = 0
        
        for item in self.base_path.rglob('*'):
            if item.is_file() and not item.name.endswith('.meta.json'):
                stats = item.stat()
                modified = datetime.fromtimestamp(stats.st_mtime)
                
                if modified < cutoff:
                    try:
                        item.unlink()
                        
                        # Delete metadata file
                        metadata_path = item.with_suffix('.meta.json')
                        if metadata_path.exists():
                            metadata_path.unlink()
                        
                        deleted_count += 1
                        
                    except Exception:
                        pass
        
        # Cleanup empty directories
        self._cleanup_empty_dirs(self.base_path)
        
        return deleted_count
    
    def _clean_path(self, path: str) -> str:
        """Clean path to prevent directory traversal."""
        # Normalize path
        path = str(path).strip().lstrip('/')
        
        # Prevent directory traversal
        if '..' in path or path.startswith('/'):
            raise ValueError("Invalid path")
        
        return path
    
    def _cleanup_empty_dirs(self, directory: Path):
        """Recursively remove empty directories."""
        try:
            # Check if directory is empty
            if directory.exists() and directory.is_dir():
                # Check if empty (excluding .gitkeep)
                items = list(directory.iterdir())
                if all(item.name == '.gitkeep' for item in items) or len(items) == 0:
                    # Remove .gitkeep if present
                    gitkeep = directory / '.gitkeep'
                    if gitkeep.exists():
                        gitkeep.unlink()
                    
                    # Remove directory
                    directory.rmdir()
                    
                    # Try parent directory
                    self._cleanup_empty_dirs(directory.parent)
        except Exception:
            # Directory might not be empty or we don't have permission
            pass

class S3Storage(Storage):
    """Amazon S3 storage implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise ImportError("boto3 is required for S3Storage")
        
        config = config or {}
        
        # S3 configuration
        self.bucket_name = config.get('bucket_name')
        if not self.bucket_name:
            raise ValueError("bucket_name is required for S3Storage")
        
        # S3 client configuration
        s3_config = Config(
            retries={
                'max_attempts': config.get('max_retries', 3),
                'mode': 'standard'
            },
            connect_timeout=config.get('connect_timeout', 10),
            read_timeout=config.get('read_timeout', 30)
        )
        
        # Create S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=config.get('access_key_id'),
            aws_secret_access_key=config.get('secret_access_key'),
            region_name=config.get('region', 'us-east-1'),
            endpoint_url=config.get('endpoint_url'),
            config=s3_config
        )
        
        # URL configuration
        self.cdn_url = config.get('cdn_url')
        self.presigned_url_expiry = config.get('presigned_url_expiry', 3600)
        
        # Check bucket existence
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except Exception as e:
            # Try to create bucket if it doesn't exist
            try:
                self.s3_client.create_bucket(
                    Bucket=self.bucket_name,
                    CreateBucketConfiguration={
                        'LocationConstraint': config.get('region', 'us-east-1')
                    }
                )
            except Exception:
                raise ConnectionError(f"Failed to access or create bucket: {e}")
    
    def upload(self, 
               file_path: Union[str, Path, BinaryIO],
               destination: str,
               metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload a file to S3."""
        # Clean destination path
        destination = self._clean_path(destination)
        
        # Prepare extra arguments
        extra_args = {
            'Metadata': {
                'uploaded_at': datetime.utcnow().isoformat()
            }
        }
        
        # Add custom metadata
        if metadata:
            # Store metadata in S3 metadata (limited to 2KB total)
            for key, value in metadata.items():
                if len(str(value)) < 500:  # Keep metadata small
                    extra_args['Metadata'][f'x-amz-meta-{key}'] = str(value)
        
        # Set content type based on file extension
        content_type = mimetypes.guess_type(destination)[0]
        if content_type:
            extra_args['ContentType'] = content_type
        
        # Upload file
        if hasattr(file_path, 'read'):
            # File-like object
            self.s3_client.upload_fileobj(
                file_path,
                self.bucket_name,
                destination,
                ExtraArgs=extra_args
            )
        else:
            # File path
            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                destination,
                ExtraArgs=extra_args
            )
        
        return destination
    
    def download(self, 
                 source: str,
                 destination: Union[str, Path]) -> bool:
        """Download a file from S3."""
        source = self._clean_path(source)
        
        try:
            # Create parent directories
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            
            # Download file
            self.s3_client.download_file(
                self.bucket_name,
                source,
                str(destination)
            )
            
            return True
            
        except Exception:
            return False
    
    def delete(self, source: str) -> bool:
        """Delete a file from S3."""
        source = self._clean_path(source)
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=source
            )
            return True
            
        except Exception:
            return False
    
    def exists(self, source: str) -> bool:
        """Check if file exists in S3."""
        source = self._clean_path(source)
        
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=source
            )
            return True
            
        except Exception:
            return False
    
    def get_url(self, 
                source: str,
                expires_in: Optional[int] = None) -> str:
        """Get URL for file."""
        source = self._clean_path(source)
        
        if self.cdn_url:
            # Use CDN URL
            return f"{self.cdn_url}/{source}"
        
        elif expires_in is not None:
            # Generate presigned URL
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': source
                },
                ExpiresIn=expires_in or self.presigned_url_expiry
            )
        
        else:
            # Public URL (if bucket is public)
            return f"https://{self.bucket_name}.s3.amazonaws.com/{source}"
    
    def list_files(self, 
                   prefix: str = "",
                   max_results: int = 1000) -> List[Dict[str, Any]]:
        """List files in S3."""
        prefix = self._clean_path(prefix)
        
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix,
                PaginationConfig={'MaxItems': max_results}
            )
            
            files = []
            for page in pages:
                for obj in page.get('Contents', []):
                    file_info = {
                        'name': obj['Key'],
                        'size': obj['Size'],
                        'modified': obj['LastModified'].isoformat(),
                        'etag': obj['ETag'].strip('"'),
                        'url': self.get_url(obj['Key'])
                    }
                    
                    # Get metadata
                    try:
                        metadata = self.get_metadata(obj['Key'])
                        file_info.update(metadata)
                    except:
                        pass
                    
                    files.append(file_info)
            
            return files
            
        except Exception:
            return []
    
    def get_metadata(self, source: str) -> Dict[str, Any]:
        """Get file metadata from S3."""
        source = self._clean_path(source)
        
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=source
            )
            
            metadata = {
                'size': response['ContentLength'],
                'modified': response['LastModified'].isoformat(),
                'content_type': response.get('ContentType', 'application/octet-stream'),
                'etag': response['ETag'].strip('"'),
                'metadata': {}
            }
            
            # Extract custom metadata
            for key, value in response.get('Metadata', {}).items():
                if key.startswith('x-amz-meta-'):
                    metadata['metadata'][key[11:]] = value
                else:
                    metadata['metadata'][key] = value
            
            return metadata
            
        except Exception:
            return {}
    
    def copy(self, 
             source: str,
             destination: str) -> bool:
        """Copy file within S3."""
        source = self._clean_path(source)
        destination = self._clean_path(destination)
        
        try:
            # Copy object
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': source
            }
            
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=destination
            )
            
            return True
            
        except Exception:
            return False
    
    def move(self, 
             source: str,
             destination: str) -> bool:
        """Move file within S3."""
        if self.copy(source, destination):
            return self.delete(source)
        return False
    
    def _clean_path(self, path: str) -> str:
        """Clean path for S3."""
        # Normalize path
        path = str(path).strip().lstrip('/')
        
        # S3 doesn't allow consecutive slashes or certain characters
        while '//' in path:
            path = path.replace('//', '/')
        
        # Remove problematic characters
        for char in ['\0', '\r', '\n']:
            path = path.replace(char, '')
        
        return path

class GCSStorage(Storage):
    """Google Cloud Storage implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        try:
            from google.cloud import storage
            from google.auth.exceptions import DefaultCredentialsError
        except ImportError:
            raise ImportError("google-cloud-storage is required for GCSStorage")
        
        config = config or {}
        
        # GCS configuration
        self.bucket_name = config.get('bucket_name')
        if not self.bucket_name:
            raise ValueError("bucket_name is required for GCSStorage")
        
        # Initialize GCS client
        try:
            # Try to use credentials from config
            credentials_path = config.get('credentials_path')
            if credentials_path:
                self.storage_client = storage.Client.from_service_account_json(credentials_path)
            else:
                # Use default credentials
                self.storage_client = storage.Client()
        except DefaultCredentialsError:
            raise ConnectionError("Failed to authenticate with Google Cloud")
        
        # Get or create bucket
        try:
            self.bucket = self.storage_client.get_bucket(self.bucket_name)
        except Exception:
            # Try to create bucket
            try:
                self.bucket = self.storage_client.create_bucket(self.bucket_name)
            except Exception as e:
                raise ConnectionError(f"Failed to access or create bucket: {e}")
        
        # URL configuration
        self.cdn_url = config.get('cdn_url')
        self.signed_url_expiry = config.get('signed_url_expiry', 3600)
    
    def upload(self, 
               file_path: Union[str, Path, BinaryIO],
               destination: str,
               metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload a file to GCS."""
        # Clean destination path
        destination = self._clean_path(destination)
        
        # Get blob
        blob = self.bucket.blob(destination)
        
        # Set metadata
        blob.metadata = {
            'uploaded_at': datetime.utcnow().isoformat()
        }
        
        if metadata:
            blob.metadata.update(metadata)
        
        # Set content type
        content_type = mimetypes.guess_type(destination)[0]
        if content_type:
            blob.content_type = content_type
        
        # Upload file
        if hasattr(file_path, 'read'):
            # File-like object
            blob.upload_from_file(file_path)
        else:
            # File path
            blob.upload_from_filename(str(file_path))
        
        return destination
    
    def download(self, 
                 source: str,
                 destination: Union[str, Path]) -> bool:
        """Download a file from GCS."""
        source = self._clean_path(source)
        
        try:
            blob = self.bucket.blob(source)
            
            # Create parent directories
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            
            # Download file
            blob.download_to_filename(str(destination))
            
            return True
            
        except Exception:
            return False
    
    def delete(self, source: str) -> bool:
        """Delete a file from GCS."""
        source = self._clean_path(source)
        
        try:
            blob = self.bucket.blob(source)
            blob.delete()
            return True
            
        except Exception:
            return False
    
    def exists(self, source: str) -> bool:
        """Check if file exists in GCS."""
        source = self._clean_path(source)
        
        try:
            blob = self.bucket.blob(source)
            return blob.exists()
            
        except Exception:
            return False
    
    def get_url(self, 
                source: str,
                expires_in: Optional[int] = None) -> str:
        """Get URL for file."""
        source = self._clean_path(source)
        
        if self.cdn_url:
            # Use CDN URL
            return f"{self.cdn_url}/{source}"
        
        elif expires_in is not None:
            # Generate signed URL
            blob = self.bucket.blob(source)
            
            # Check if blob exists
            if not blob.exists():
                raise FileNotFoundError(f"File {source} not found")
            
            url = blob.generate_signed_url(
                expiration=expires_in or self.signed_url_expiry,
                method='GET'
            )
            return url
        
        else:
            # Public URL (if blob is public)
            blob = self.bucket.blob(source)
            return blob.public_url
    
    def list_files(self, 
                   prefix: str = "",
                   max_results: int = 1000) -> List[Dict[str, Any]]:
        """List files in GCS."""
        prefix = self._clean_path(prefix)
        
        try:
            blobs = self.bucket.list_blobs(
                prefix=prefix,
                max_results=max_results
            )
            
            files = []
            for blob in blobs:
                # Skip directories (they appear as empty blobs)
                if blob.name.endswith('/'):
                    continue
                
                file_info = {
                    'name': blob.name,
                    'size': blob.size,
                    'modified': blob.updated.isoformat(),
                    'url': self.get_url(blob.name)
                }
                
                # Add metadata
                if blob.metadata:
                    file_info['metadata'] = blob.metadata
                
                files.append(file_info)
            
            return files
            
        except Exception:
            return []
    
    def get_metadata(self, source: str) -> Dict[str, Any]:
        """Get file metadata from GCS."""
        source = self._clean_path(source)
        
        try:
            blob = self.bucket.blob(source)
            
            # Reload to get metadata
            blob.reload()
            
            metadata = {
                'size': blob.size,
                'modified': blob.updated.isoformat(),
                'content_type': blob.content_type or 'application/octet-stream',
                'metadata': blob.metadata or {}
            }
            
            return metadata
            
        except Exception:
            return {}
    
    def copy(self, 
             source: str,
             destination: str) -> bool:
        """Copy file within GCS."""
        source = self._clean_path(source)
        destination = self._clean_path(destination)
        
        try:
            source_blob = self.bucket.blob(source)
            
            # Copy blob
            self.bucket.copy_blob(
                source_blob,
                self.bucket,
                destination
            )
            
            return True
            
        except Exception:
            return False
    
    def move(self, 
             source: str,
             destination: str) -> bool:
        """Move file within GCS."""
        if self.copy(source, destination):
            return self.delete(source)
        return False
    
    def _clean_path(self, path: str) -> str:
        """Clean path for GCS."""
        # Normalize path
        path = str(path).strip().lstrip('/')
        
        # Remove problematic characters
        for char in ['\0', '\r', '\n']:
            path = path.replace(char, '')
        
        return path