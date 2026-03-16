"""
Dedicated video processing worker.
"""
import os
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from . import BaseWorker
from services.video_service import VideoService
from services.quality_service import QualityService
from providers.ffmpeg_provider import FFmpegProvider
from core.domain.entities.video import Video, VideoStatus
from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)

class VideoWorker(BaseWorker):
    """Worker for general video processing tasks."""
    
    def __init__(self, worker_id: str, config: Dict[str, Any] = None):
        super().__init__(worker_id, config)
        self.video_service = VideoService()
        self.quality_service = QualityService()
        self.ffmpeg = FFmpegProvider()
        
        # Worker capabilities
        self.capabilities = {
            'video_formats': ['mp4', 'avi', 'mov', 'mkv', 'webm'],
            'max_resolution': '4k',
            'supports_hdr': False,
            'gpu_accelerated': False,
            'max_concurrent_tasks': 1
        }
        
        # Update capabilities from config
        if 'capabilities' in config:
            self.capabilities.update(config['capabilities'])
    
    def can_process(self, task_data: Dict[str, Any]) -> bool:
        """Check if worker can process the given task."""
        try:
            video_format = task_data.get('video_format', 'mp4').lower()
            resolution = task_data.get('resolution', '1080p').lower()
            requires_hdr = task_data.get('requires_hdr', False)
            
            # Check format support
            if video_format not in self.capabilities['video_formats']:
                return False
            
            # Check resolution support
            resolution_order = ['480p', '720p', '1080p', '4k', '8k']
            if resolution in resolution_order:
                worker_max_idx = resolution_order.index(self.capabilities['max_resolution'])
                task_idx = resolution_order.index(resolution)
                if task_idx > worker_max_idx:
                    return False
            
            # Check HDR support
            if requires_hdr and not self.capabilities['supports_hdr']:
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error checking task compatibility: {e}")
            return False
    
    def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a video task."""
        start_time = time.time()
        task_id = task_data.get('task_id', 'unknown')
        video_id = task_data.get('video_id')
        user_id = task_data.get('user_id')
        
        logger.info(f"Worker {self.worker_id} starting task {task_id} for video {video_id}")
        
        try:
            # Validate task data
            if not video_id or not user_id:
                raise ProcessingError("Missing video_id or user_id in task data")
            
            # Get video from service
            video = self.video_service.get_video(video_id, user_id)
            if not video:
                raise ProcessingError(f"Video {video_id} not found or access denied")
            
            # Update task status
            self.current_task = {
                'task_id': task_id,
                'video_id': video_id,
                'user_id': user_id,
                'started_at': start_time
            }
            
            # Process based on task type
            task_type = task_data.get('task_type', 'quality_processing')
            
            if task_type == 'quality_processing':
                result = self._process_quality(video, task_data)
            elif task_type == 'format_conversion':
                result = self._process_conversion(video, task_data)
            elif task_type == 'compression':
                result = self._process_compression(video, task_data)
            elif task_type == 'extract_frames':
                result = self._process_frame_extraction(video, task_data)
            else:
                raise ProcessingError(f"Unknown task type: {task_type}")
            
            # Update stats
            processing_time = time.time() - start_time
            self.update_stats(success=True, processing_time=processing_time)
            
            logger.info(f"Worker {self.worker_id} completed task {task_id} in {processing_time:.2f}s")
            
            return {
                'status': 'success',
                'task_id': task_id,
                'video_id': video_id,
                'result': result,
                'processing_time': processing_time,
                'worker_id': self.worker_id
            }
            
        except Exception as e:
            # Update stats
            processing_time = time.time() - start_time
            self.update_stats(success=False, processing_time=processing_time)
            
            logger.error(f"Worker {self.worker_id} failed task {task_id}: {e}")
            
            return {
                'status': 'failed',
                'task_id': task_id,
                'video_id': video_id,
                'error': str(e),
                'processing_time': processing_time,
                'worker_id': self.worker_id
            }
            
        finally:
            self.current_task = None
    
    def _process_quality(self, video: Video, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process video quality adjustment."""
        # Get processing parameters
        target_quality = task_data.get('quality', video.output_quality)
        tier = task_data.get('tier', 'free')
        
        # Create temp directory
        temp_dir = Path(tempfile.gettempdir()) / "video_ai" / "processing" / video.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Define output path
        output_path = temp_dir / f"processed_{target_quality}.mp4"
        
        # Process video quality
        result = self.quality_service.process_video(
            input_path=video.original_path or video.processing_path,
            output_path=str(output_path),
            target_quality=target_quality,
            tier=tier
        )
        
        # Update video object
        video.output_path = str(output_path)
        video.output_quality = target_quality
        video.output_video_size = os.path.getsize(output_path)
        
        return {
            'output_path': str(output_path),
            'output_quality': target_quality,
            'file_size': video.output_video_size,
            'processing_details': result
        }
    
    def _process_conversion(self, video: Video, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process video format conversion."""
        target_format = task_data.get('format', 'mp4')
        preset = task_data.get('preset', 'medium')
        
        # Create temp directory
        temp_dir = Path(tempfile.gettempdir()) / "video_ai" / "processing" / video.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Define output path
        output_filename = f"converted.{target_format}"
        output_path = temp_dir / output_filename
        
        # Convert video format
        input_path = video.original_path or video.processing_path
        self.ffmpeg.convert_format(
            input_path=str(input_path),
            output_path=str(output_path),
            output_format=target_format,
            preset=preset
        )
        
        # Get output file size
        output_size = os.path.getsize(output_path)
        
        return {
            'output_path': str(output_path),
            'output_format': target_format,
            'file_size': output_size,
            'original_format': video.mime_type.split('/')[-1]
        }
    
    def _process_compression(self, video: Video, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process video compression."""
        target_bitrate = task_data.get('bitrate', '2M')
        crf = task_data.get('crf', 23)
        
        # Create temp directory
        temp_dir = Path(tempfile.gettempdir()) / "video_ai" / "processing" / video.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Define output path
        output_path = temp_dir / "compressed.mp4"
        
        # Compress video
        input_path = video.original_path or video.processing_path
        self.ffmpeg.compress_video(
            input_path=str(input_path),
            output_path=str(output_path),
            target_bitrate=target_bitrate,
            crf=crf
        )
        
        # Calculate compression ratio
        original_size = video.file_size
        compressed_size = os.path.getsize(output_path)
        compression_ratio = (original_size - compressed_size) / original_size * 100
        
        return {
            'output_path': str(output_path),
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': f"{compression_ratio:.1f}%",
            'target_bitrate': target_bitrate,
            'crf': crf
        }
    
    def _process_frame_extraction(self, video: Video, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract frames from video."""
        frame_count = task_data.get('frame_count', 10)
        frame_interval = task_data.get('frame_interval', 'equal')
        
        # Create temp directory for frames
        frames_dir = Path(tempfile.gettempdir()) / "video_ai" / "frames" / video.id
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract frames
        input_path = video.original_path or video.processing_path
        frames = self.ffmpeg.extract_frames(
            input_path=str(input_path),
            output_dir=str(frames_dir),
            frame_count=frame_count,
            interval=frame_interval
        )
        
        return {
            'frames_dir': str(frames_dir),
            'frame_paths': frames,
            'frame_count': len(frames),
            'frame_interval': frame_interval
        }
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed worker status."""
        base_status = super().get_status()
        base_status.update({
            'capabilities': self.capabilities,
            'average_processing_time': (
                self.stats['total_processing_time'] / 
                max(1, self.stats['tasks_completed'] + self.stats['tasks_failed'])
            ),
            'success_rate': (
                self.stats['tasks_completed'] / 
                max(1, self.stats['tasks_completed'] + self.stats['tasks_failed']) * 100
            )
        })
        return base_status