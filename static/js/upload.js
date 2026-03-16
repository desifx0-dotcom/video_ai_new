/**
 * Drag & drop file upload functionality
 */

class VideoUploader {
    constructor() {
        this.dropZone = document.getElementById('upload-dropzone');
        this.fileInput = document.getElementById('file-input');
        this.progressBar = document.getElementById('upload-progress');
        this.progressText = document.getElementById('progress-text');
        this.progressPercentage = document.getElementById('progress-percentage');
        this.fileInfo = document.getElementById('file-info');
        this.fileName = document.getElementById('file-name');
        this.fileSize = document.getElementById('file-size');
        this.fileDuration = document.getElementById('file-duration');
        this.uploadForm = document.getElementById('upload-form');
        this.cancelBtn = document.getElementById('cancel-upload');
        this.uploadBtn = document.getElementById('start-upload');
        this.optionsForm = document.getElementById('upload-options');
        
        this.currentFile = null;
        this.uploadController = null;
        this.isUploading = false;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupDragAndDrop();
        this.validateTierLimits();
    }
    
    setupEventListeners() {
        // File input change
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        
        // Drop zone click
        this.dropZone.addEventListener('click', () => this.fileInput.click());
        
        // Upload button
        this.uploadBtn.addEventListener('click', (e) => this.startUpload(e));
        
        // Cancel button
        this.cancelBtn.addEventListener('click', () => this.cancelUpload());
        
        // Form submission
        this.uploadForm.addEventListener('submit', (e) => e.preventDefault());
        
        // Window beforeunload (warn if uploading)
        window.addEventListener('beforeunload', (e) => {
            if (this.isUploading) {
                e.preventDefault();
                e.returnValue = 'You have an upload in progress. Are you sure you want to leave?';
            }
        });
    }
    
    setupDragAndDrop() {
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });
        
        // Highlight drop zone on drag
        ['dragenter', 'dragover'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, () => {
                this.dropZone.classList.add('dragover');
            });
        });
        
        // Remove highlight
        ['dragleave', 'drop'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, () => {
                this.dropZone.classList.remove('dragover');
            });
        });
        
        // Handle dropped files
        this.dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFiles(files);
            }
        });
    }
    
    handleFileSelect(e) {
        const files = e.target.files;
        if (files.length > 0) {
            this.handleFiles(files);
        }
    }
    
    handleFiles(files) {
        const file = files[0];
        
        // Validate file type
        if (!this.validateFileType(file)) {
            this.showError('Invalid file type. Please upload a video file (MP4, AVI, MOV, etc.)');
            return;
        }
        
        // Validate file size
        if (!this.validateFileSize(file)) {
            const maxSize = this.getMaxFileSize();
            this.showError(`File too large. Maximum size is ${this.formatFileSize(maxSize)}`);
            return;
        }
        
        this.currentFile = file;
        this.displayFileInfo(file);
        this.getVideoDuration(file);
        this.showUploadOptions();
    }
    
    validateFileType(file) {
        const allowedTypes = [
            'video/mp4',
            'video/x-msvideo',
            'video/quicktime',
            'video/x-matroska',
            'video/webm',
            'video/x-flv',
            'video/x-ms-wmv',
            'video/mpeg'
        ];
        
        return allowedTypes.includes(file.type) || 
               file.name.match(/\.(mp4|avi|mov|mkv|webm|flv|wmv|mpeg|mpg|m4v|3gp|ogv)$/i);
    }
    
    validateFileSize(file) {
        const maxSize = this.getMaxFileSize();
        return file.size <= maxSize;
    }
    
    getMaxFileSize() {
        // Get tier from user data
        const userTier = document.body.dataset.userTier || 'free';
        const sizeLimits = {
            'free': 100 * 1024 * 1024,      // 100MB
            'starter': 500 * 1024 * 1024,   // 500MB
            'pro': 2 * 1024 * 1024 * 1024,  // 2GB
            'plus': 5 * 1024 * 1024 * 1024, // 5GB
            'enterprise': 10 * 1024 * 1024 * 1024 // 10GB
        };
        
        return sizeLimits[userTier] || sizeLimits.free;
    }
    
    validateTierLimits() {
        const userTier = document.body.dataset.userTier || 'free';
        const videosThisMonth = parseInt(document.body.dataset.videosThisMonth) || 0;
        const monthlyLimit = parseInt(document.body.dataset.monthlyLimit) || 3;
        
        // Show tier limitations if applicable
        const limitationContainer = document.getElementById('tier-limitations');
        if (limitationContainer) {
            if (videosThisMonth >= monthlyLimit) {
                limitationContainer.style.display = 'block';
                this.updateLimitationText(monthlyLimit, videosThisMonth);
            } else {
                limitationContainer.style.display = 'none';
            }
        }
    }
    
    updateLimitationText(limit, used) {
        const limitationText = document.getElementById('limitation-text');
        if (limitationText) {
            limitationText.textContent = `You've used ${used} of ${limit} videos this month. Upgrade your plan to process more videos.`;
        }
    }
    
    displayFileInfo(file) {
        this.fileName.textContent = file.name;
        this.fileSize.textContent = this.formatFileSize(file.size);
        this.fileDuration.textContent = 'Calculating...';
        
        this.fileInfo.style.display = 'block';
        this.dropZone.style.display = 'none';
    }
    
    async getVideoDuration(file) {
        return new Promise((resolve) => {
            const video = document.createElement('video');
            video.preload = 'metadata';
            
            video.onloadedmetadata = () => {
                window.URL.revokeObjectURL(video.src);
                const duration = Math.round(video.duration);
                this.fileDuration.textContent = this.formatDuration(duration);
                resolve(duration);
                
                // Validate duration against tier limits
                this.validateVideoDuration(duration);
            };
            
            video.onerror = () => {
                this.fileDuration.textContent = 'Unknown';
                resolve(null);
            };
            
            video.src = URL.createObjectURL(file);
        });
    }
    
    validateVideoDuration(duration) {
        const userTier = document.body.dataset.userTier || 'free';
        const durationLimits = {
            'free': 180,      // 3 minutes
            'starter': 1800,  // 30 minutes
            'pro': 3600,      // 60 minutes
            'plus': 7200,     // 120 minutes
            'enterprise': 18000 // 300 minutes
        };
        
        const maxDuration = durationLimits[userTier] || durationLimits.free;
        
        if (duration > maxDuration) {
            this.showError(`Video duration (${this.formatDuration(duration)}) exceeds maximum for your tier (${this.formatDuration(maxDuration)})`);
            this.uploadBtn.disabled = true;
        } else {
            this.uploadBtn.disabled = false;
        }
    }
    
    showUploadOptions() {
        this.optionsForm.style.display = 'block';
        this.scrollToElement(this.optionsForm);
    }
    
    async startUpload(e) {
        e.preventDefault();
        
        if (!this.currentFile || this.isUploading) {
            return;
        }
        
        // Get processing options
        const formData = new FormData(this.uploadForm);
        formData.append('file', this.currentFile);
        
        // Add processing options
        const quality = document.querySelector('input[name="quality"]:checked');
        const styles = Array.from(document.querySelectorAll('input[name="styles"]:checked'))
            .map(input => input.value);
        const translation = document.getElementById('translation-language');
        
        if (quality) {
            formData.append('quality', quality.value);
        }
        
        if (styles.length > 0) {
            formData.append('styles', JSON.stringify(styles));
        }
        
        if (translation && translation.value) {
            formData.append('translation_language', translation.value);
        }
        
        this.isUploading = true;
        this.showProgress(0);
        this.uploadBtn.disabled = true;
        this.cancelBtn.style.display = 'inline-flex';
        
        try {
            // Create AbortController for cancellation
            this.uploadController = new AbortController();
            
            const response = await fetch('/api/v1/videos/upload', {
                method: 'POST',
                body: formData,
                signal: this.uploadController.signal,
                headers: {
                    'X-CSRF-Token': this.getCSRFToken()
                }
            });
            
            if (!response.ok) {
                throw new Error(`Upload failed: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess('Upload completed! Processing started.');
                this.redirectToProcessing(data.video_id);
            } else {
                throw new Error(data.message || 'Upload failed');
            }
            
        } catch (error) {
            if (error.name === 'AbortError') {
                this.showInfo('Upload cancelled');
            } else {
                this.showError(`Upload failed: ${error.message}`);
                console.error('Upload error:', error);
            }
        } finally {
            this.isUploading = false;
            this.uploadBtn.disabled = false;
            this.cancelBtn.style.display = 'none';
            this.uploadController = null;
        }
    }
    
    showProgress(percentage) {
        this.progressBar.style.width = `${percentage}%`;
        this.progressPercentage.textContent = `${Math.round(percentage)}%`;
        
        if (percentage < 100) {
            this.progressText.textContent = 'Uploading...';
        } else {
            this.progressText.textContent = 'Processing...';
        }
    }
    
    cancelUpload() {
        if (this.uploadController && this.isUploading) {
            this.uploadController.abort();
        }
        
        this.resetUpload();
    }
    
    resetUpload() {
        this.currentFile = null;
        this.isUploading = false;
        this.uploadController = null;
        
        this.fileInfo.style.display = 'none';
        this.dropZone.style.display = 'block';
        this.optionsForm.style.display = 'none';
        
        this.progressBar.style.width = '0%';
        this.progressPercentage.textContent = '0%';
        this.progressText.textContent = '';
        
        this.uploadBtn.disabled = false;
        this.cancelBtn.style.display = 'none';
        
        // Reset file input
        this.fileInput.value = '';
    }
    
    redirectToProcessing(videoId) {
        // Show success message
        this.showSuccess('Video uploaded successfully! Redirecting to processing page...');
        
        // Redirect after delay
        setTimeout(() => {
            window.location.href = `/dashboard/processing/${videoId}`;
        }, 2000);
    }
    
    showError(message) {
        this.showNotification(message, 'error');
    }
    
    showSuccess(message) {
        this.showNotification(message, 'success');
    }
    
    showInfo(message) {
        this.showNotification(message, 'info');
    }
    
    showNotification(message, type = 'info') {
        // Remove existing notifications
        const existing = document.querySelector('.upload-notification');
        if (existing) {
            existing.remove();
        }
        
        // Create notification
        const notification = document.createElement('div');
        notification.className = `upload-notification alert alert-${type}`;
        notification.textContent = message;
        notification.style.position = 'fixed';
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '10000';
        notification.style.maxWidth = '400px';
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }
    
    scrollToElement(element) {
        element.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }
    
    getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, '0')}`;
        }
    }
}

// Initialize uploader when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const uploader = new VideoUploader();
    
    // Expose uploader to window for debugging
    window.videoUploader = uploader;
});