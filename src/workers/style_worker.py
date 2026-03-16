"""
GPU-intensive video style processing worker.
"""
import os
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from . import BaseWorker
from services.style_service import StyleService
from providers.ffmpeg_provider import FFmpegProvider
from core.domain.entities.video import Video
from core.domain.value_objects.video_style import VideoStyle, StyleCategory
from core.exceptions import ProcessingError

logger = logging.getLogger(__name__)

class StyleWorker(BaseWorker):
    """Worker for GPU-intensive video style processing."""
    
    def __init__(self, worker_id: str, config: Dict[str, Any] = None):
        super().__init__(worker_id, config)
        self.style_service = StyleService()
        self.ffmpeg = FFmpegProvider()
        
        # GPU capabilities
        self.gpu_info = self._detect_gpu()
        
        # Worker capabilities
        self.capabilities = {
            'video_formats': ['mp4', 'mov', 'mkv'],
            'max_resolution': '4k',
            'supports_hdr': True,
            'gpu_accelerated': True,
            'gpu_type': self.gpu_info.get('type', 'unknown'),
            'gpu_memory_gb': self.gpu_info.get('memory_gb', 0),
            'max_concurrent_tasks': 1,
            'supported_styles': self._get_supported_styles()
        }
        
        # Update capabilities from config
        if 'capabilities' in config:
            self.capabilities.update(config['capabilities'])
        
        # Style processing queue
        self.style_queue = []
        self.max_queue_size = config.get('max_queue_size', 10)
        
        logger.info(f"Style Worker {worker_id} initialized with GPU: {self.gpu_info}")
    
    def _detect_gpu(self) -> Dict[str, Any]:
        """Detect GPU information."""
        gpu_info = {
            'type': 'unknown',
            'memory_gb': 0,
            'available': False
        }
        
        try:
            # Try to detect NVIDIA GPU
            import subprocess
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    parts = lines[0].split(',')
                    if len(parts) >= 2:
                        gpu_info['type'] = parts[0].strip()
                        gpu_info['memory_gb'] = int(parts[1].strip()) / 1024
                        gpu_info['available'] = True
                        return gpu_info
            
            # Try to detect AMD GPU
            result = subprocess.run(
                ['rocm-smi', '--showproductname', '--showmeminfo', 'vram'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                gpu_info['type'] = 'amd'
                gpu_info['available'] = True
                # Parse memory info from output
                for line in result.stdout.split('\n'):
                    if 'Total' in line and 'VRAM' in line:
                        try:
                            mem_mb = int(''.join(filter(str.isdigit, line)))
                            gpu_info['memory_gb'] = mem_mb / 1024
                        except:
                            pass
            
        except Exception as e:
            logger.warning(f"Failed to detect GPU: {e}")
        
        return gpu_info
    
    def _get_supported_styles(self) -> List[str]:
        """Get list of supported video styles based on GPU capabilities."""
        # All available styles
        all_styles = [
            'cinematic', 'gaming', 'educational', 'vlog',
            'documentary', 'corporate', 'wedding', 'real_estate',
            'travel', 'cinematic_pro', 'artistic', 'retro',
            'futuristic', 'hdr_enhanced', 'slow_motion', 'time_lapse'
        ]
        
        # Filter based on GPU capabilities
        supported = all_styles.copy()
        
        if not self.gpu_info['available']:
            # CPU-only styles
            supported = [s for s in supported if s not in [
                'cinematic_pro', 'hdr_enhanced', 'slow_motion'
            ]]
        
        if self.gpu_info['memory_gb'] < 4:
            # Limited GPU memory
            supported = [s for s in supported if s not in [
                'artistic', 'futuristic', 'hdr_enhanced'
            ]]
        
        return supported
    
    def can_process(self, task_data: Dict[str, Any]) -> bool:
        """Check if worker can process the given style task."""
        try:
            video_format = task_data.get('video_format', 'mp4').lower()
            resolution = task_data.get('resolution', '1080p').lower()
            styles = task_data.get('styles', [])
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
            
            # Check style support
            for style in styles:
                if style not in self.capabilities['supported_styles']:
                    return False
            
            # Check GPU memory requirements
            estimated_memory = self._estimate_memory_requirements(task_data)
            if estimated_memory > self.capabilities['gpu_memory_gb']:
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error checking style task compatibility: {e}")
            return False
    
    def _estimate_memory_requirements(self, task_data: Dict[str, Any]) -> float:
        """Estimate GPU memory requirements for a task."""
        resolution = task_data.get('resolution', '1080p')
        styles = task_data.get('styles', [])
        
        # Base memory per resolution (GB)
        resolution_memory = {
            '480p': 1.0,
            '720p': 2.0,
            '1080p': 4.0,
            '4k': 8.0,
            '8k': 16.0
        }
        
        base_memory = resolution_memory.get(resolution, 4.0)
        
        # Additional memory per style
        style_multipliers = {
            'cinematic': 1.2,
            'cinematic_pro': 1.5,
            'hdr_enhanced': 2.0,
            'artistic': 1.8,
            'futuristic': 1.7,
            'slow_motion': 1.3,
            'time_lapse': 1.1
        }
        
        multiplier = 1.0
        for style in styles:
            multiplier *= style_multipliers.get(style, 1.0)
        
        return base_memory * multiplier
    
    def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a video style task."""
        start_time = time.time()
        task_id = task_data.get('task_id', 'unknown')
        video_id = task_data.get('video_id')
        user_id = task_data.get('user_id')
        
        logger.info(f"Style Worker {self.worker_id} starting task {task_id} for video {video_id}")
        
        try:
            # Validate task data
            if not video_id or not user_id:
                raise ProcessingError("Missing video_id or user_id in task data")
            
            # Check if queue is full
            if len(self.style_queue) >= self.max_queue_size:
                raise ProcessingError("Style worker queue is full")
            
            # Add to queue
            self.style_queue.append(task_id)
            
            # Update task status
            self.current_task = {
                'task_id': task_id,
                'video_id': video_id,
                'user_id': user_id,
                'started_at': start_time,
                'styles': task_data.get('styles', [])
            }
            
            # Process styles
            result = self._apply_styles(task_data)
            
            # Remove from queue
            if task_id in self.style_queue:
                self.style_queue.remove(task_id)
            
            # Update stats
            processing_time = time.time() - start_time
            self.update_stats(success=True, processing_time=processing_time)
            
            logger.info(f"Style Worker {self.worker_id} completed task {task_id} in {processing_time:.2f}s")
            
            return {
                'status': 'success',
                'task_id': task_id,
                'video_id': video_id,
                'result': result,
                'processing_time': processing_time,
                'worker_id': self.worker_id,
                'gpu_used': True
            }
            
        except Exception as e:
            # Remove from queue if present
            if task_id in self.style_queue:
                self.style_queue.remove(task_id)
            
            # Update stats
            processing_time = time.time() - start_time
            self.update_stats(success=False, processing_time=processing_time)
            
            logger.error(f"Style Worker {self.worker_id} failed task {task_id}: {e}")
            
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
    
    def _apply_styles(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply video styles."""
        video_id = task_data['video_id']
        user_id = task_data['user_id']
        styles = task_data.get('styles', [])
        tier = task_data.get('tier', 'free')
        
        # Get video service to access video
        from services.video_service import VideoService
        video_service = VideoService()
        video = video_service.get_video(video_id, user_id)
        
        if not video:
            raise ProcessingError(f"Video {video_id} not found")
        
        # Create temp directory
        temp_dir = Path(tempfile.gettempdir()) / "video_ai" / "styles" / video.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each style sequentially
        current_input = video.original_path or video.processing_path
        processing_details = []
        
        for style_name in styles:
            style_start = time.time()
            
            # Apply style
            style_result = self.style_service.apply_style(
                input_path=current_input,
                style_name=style_name,
                tier=tier,
                gpu_accelerated=self.capabilities['gpu_accelerated']
            )
            
            # Update input for next style
            current_input = style_result['output_path']
            processing_time = time.time() - style_start
            
            processing_details.append({
                'style': style_name,
                'processing_time': processing_time,
                'output_path': style_result['output_path'],
                'gpu_used': style_result.get('gpu_used', False)
            })
            
            logger.debug(f"Applied style {style_name} in {processing_time:.2f}s")
        
        # Final output is the last processed file
        final_output = current_input
        
        # Get file size
        output_size = os.path.getsize(final_output)
        
        return {
            'output_path': final_output,
            'file_size': output_size,
            'styles_applied': styles,
            'processing_details': processing_details,
            'total_styles': len(styles),
            'gpu_accelerated': self.capabilities['gpu_accelerated'],
            'gpu_type': self.capabilities['gpu_type']
        }
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed worker status."""
        base_status = super().get_status()
        base_status.update({
            'capabilities': self.capabilities,
            'gpu_info': self.gpu_info,
            'queue_size': len(self.style_queue),
            'max_queue_size': self.max_queue_size,
            'queue_items': self.style_queue.copy(),
            'average_processing_time': (
                self.stats['total_processing_time'] / 
                max(1, self.stats['tasks_completed'] + self.stats['tasks_failed'])
            ),
            'success_rate': (
                self.stats['tasks_completed'] / 
                max(1, self.stats['tasks_completed'] + self.stats['tasks_failed']) * 100
            ),
            'gpu_utilization': self._calculate_gpu_utilization()
        })
        return base_status
    
    def _calculate_gpu_utilization(self) -> float:
        """Calculate GPU utilization percentage."""
        if not self.gpu_info['available']:
            return 0.0
        
        try:
            import subprocess
            
            if self.gpu_info['type'].lower() == 'nvidia':
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    utilization = result.stdout.strip()
                    if utilization:
                        return float(utilization)
            
            # Default estimation based on current tasks
            if self.current_task:
                return 85.0  # Assume high utilization when processing
            elif self.style_queue:
                return 30.0  # Some utilization when queued
            else:
                return 5.0   # Idle
        
        except Exception:
            return 0.0
    
    def preload_style_models(self, style_names: List[str]):
        """Preload style models into GPU memory."""
        if not self.gpu_info['available']:
            logger.warning("Cannot preload models without GPU")
            return
        
        logger.info(f"Preloading style models: {style_names}")
        
        # This would typically involve loading neural network models
        # For now, we'll just log the action
        for style in style_names:
            if style in self.capabilities['supported_styles']:
                logger.debug(f"Preloaded model for style: {style}")
    
    def clear_gpu_cache(self):
        """Clear GPU memory cache."""
        if not self.gpu_info['available']:
            return
        
        logger.info("Clearing GPU cache")
        
        try:
            # For NVIDIA GPUs
            if 'nvidia' in self.gpu_info['type'].lower():
                import subprocess
                subprocess.run(['nvidia-smi', '--gpu-reset'], capture_output=True)
                logger.debug("Cleared NVIDIA GPU cache")
        except Exception as e:
            logger.warning(f"Failed to clear GPU cache: {e}")