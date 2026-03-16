/**
 * Custom video player with enhanced controls and features.
 */
class VideoPlayer {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container with id "${containerId}" not found`);
        }
        
        this.options = {
            autoplay: false,
            controls: true,
            loop: false,
            muted: false,
            preload: 'metadata',
            playbackRate: 1.0,
            volume: 0.8,
            responsive: true,
            qualitySelector: false,
            downloadButton: true,
            fullscreen: true,
            pictureInPicture: true,
            ...options
        };
        
        this.video = null;
        this.controls = null;
        this.isPlaying = false;
        this.isFullscreen = false;
        this.isPictureInPicture = false;
        this.currentTime = 0;
        this.duration = 0;
        this.buffered = 0;
        this.playbackRates = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
        this.qualities = options.qualities || ['720p', '1080p', '4K'];
        this.currentQuality = options.currentQuality || '1080p';
        
        this.init();
    }
    
    init() {
        this.createVideoElement();
        this.createControls();
        this.setupEventListeners();
        this.setupKeyboardControls();
        
        if (this.options.responsive) {
            this.makeResponsive();
        }
    }
    
    createVideoElement() {
        this.video = document.createElement('video');
        this.video.id = `${this.container.id}-video`;
        this.video.className = 'video-js';
        
        // Set video attributes
        this.video.autoplay = this.options.autoplay;
        this.video.controls = false; // We'll use custom controls
        this.video.loop = this.options.loop;
        this.video.muted = this.options.muted;
        this.video.preload = this.options.preload;
        this.video.playsInline = true;
        
        // Set initial playback rate and volume
        this.video.playbackRate = this.options.playbackRate;
        this.video.volume = this.options.volume;
        
        // Add source if provided
        if (this.options.src) {
            this.setSource(this.options.src);
        }
        
        this.container.appendChild(this.video);
    }
    
    createControls() {
        this.controls = document.createElement('div');
        this.controls.className = 'video-controls';
        this.controls.innerHTML = `
            <div class="controls-top">
                <div class="progress-container">
                    <div class="progress-bar">
                        <div class="progress-played"></div>
                        <div class="progress-buffered"></div>
                        <input type="range" class="progress-slider" min="0" max="100" value="0" step="0.1">
                    </div>
                    <div class="time-display">
                        <span class="current-time">00:00</span> / <span class="duration">00:00</span>
                    </div>
                </div>
            </div>
            
            <div class="controls-bottom">
                <div class="controls-left">
                    <button class="control-btn play-pause" title="Play/Pause">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="control-btn volume-btn" title="Volume">
                        <i class="fas fa-volume-up"></i>
                    </button>
                    <div class="volume-slider-container">
                        <input type="range" class="volume-slider" min="0" max="100" value="${this.options.volume * 100}" step="1">
                    </div>
                    <div class="time-display-mobile">
                        <span class="current-time">00:00</span> / <span class="duration">00:00</span>
                    </div>
                </div>
                
                <div class="controls-center">
                    <button class="control-btn skip-backward" title="Skip 10s backward">
                        <i class="fas fa-backward"></i>
                    </button>
                    <button class="control-btn skip-forward" title="Skip 10s forward">
                        <i class="fas fa-forward"></i>
                    </button>
                    <button class="control-btn playback-rate" title="Playback speed">
                        <span>${this.options.playbackRate}x</span>
                    </button>
                    
                    ${this.options.qualitySelector ? `
                    <div class="quality-selector">
                        <button class="control-btn quality-btn" title="Quality">
                            <span>${this.currentQuality}</span>
                        </button>
                        <div class="quality-menu">
                            ${this.qualities.map(quality => `
                                <button class="quality-option ${quality === this.currentQuality ? 'active' : ''}" data-quality="${quality}">
                                    ${quality}
                                </button>
                            `).join('')}
                        </div>
                    </div>
                    ` : ''}
                </div>
                
                <div class="controls-right">
                    ${this.options.downloadButton ? `
                    <button class="control-btn download-btn" title="Download">
                        <i class="fas fa-download"></i>
                    </button>
                    ` : ''}
                    
                    ${this.options.pictureInPicture ? `
                    <button class="control-btn pip-btn" title="Picture in Picture">
                        <i class="fas fa-picture-in-picture"></i>
                    </button>
                    ` : ''}
                    
                    ${this.options.fullscreen ? `
                    <button class="control-btn fullscreen-btn" title="Fullscreen">
                        <i class="fas fa-expand"></i>
                    </button>
                    ` : ''}
                </div>
            </div>
        `;
        
        this.container.appendChild(this.controls);
        
        // Initialize control elements
        this.playPauseBtn = this.controls.querySelector('.play-pause');
        this.progressSlider = this.controls.querySelector('.progress-slider');
        this.progressPlayed = this.controls.querySelector('.progress-played');
        this.progressBuffered = this.controls.querySelector('.progress-buffered');
        this.currentTimeEl = this.controls.querySelector('.current-time');
        this.durationEl = this.controls.querySelector('.duration');
        this.volumeBtn = this.controls.querySelector('.volume-btn');
        this.volumeSlider = this.controls.querySelector('.volume-slider');
        this.playbackRateBtn = this.controls.querySelector('.playback-rate');
        this.fullscreenBtn = this.controls.querySelector('.fullscreen-btn');
        this.pipBtn = this.controls.querySelector('.pip-btn');
        this.downloadBtn = this.controls.querySelector('.download-btn');
        this.skipBackwardBtn = this.controls.querySelector('.skip-backward');
        this.skipForwardBtn = this.controls.querySelector('.skip-forward');
        
        if (this.options.qualitySelector) {
            this.qualityBtn = this.controls.querySelector('.quality-btn');
            this.qualityMenu = this.controls.querySelector('.quality-menu');
            this.qualityOptions = this.controls.querySelectorAll('.quality-option');
        }
    }
    
    setupEventListeners() {
        // Play/Pause
        this.playPauseBtn.addEventListener('click', () => this.togglePlay());
        this.video.addEventListener('click', () => this.togglePlay());
        
        // Progress
        this.progressSlider.addEventListener('input', (e) => {
            const time = (e.target.value / 100) * this.duration;
            this.video.currentTime = time;
        });
        
        this.video.addEventListener('timeupdate', () => this.updateProgress());
        this.video.addEventListener('loadedmetadata', () => {
            this.duration = this.video.duration;
            this.updateDurationDisplay();
        });
        
        // Volume
        this.volumeBtn.addEventListener('click', () => this.toggleMute());
        this.volumeSlider.addEventListener('input', (e) => {
            const volume = e.target.value / 100;
            this.video.volume = volume;
            this.updateVolumeIcon();
        });
        
        this.video.addEventListener('volumechange', () => {
            this.volumeSlider.value = this.video.volume * 100;
            this.updateVolumeIcon();
        });
        
        // Playback rate
        if (this.playbackRateBtn) {
            this.playbackRateBtn.addEventListener('click', () => this.cyclePlaybackRate());
        }
        
        // Skip buttons
        if (this.skipBackwardBtn) {
            this.skipBackwardBtn.addEventListener('click', () => this.skip(-10));
        }
        
        if (this.skipForwardBtn) {
            this.skipForwardBtn.addEventListener('click', () => this.skip(10));
        }
        
        // Quality selector
        if (this.options.qualitySelector && this.qualityBtn) {
            this.qualityBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.qualityMenu.classList.toggle('show');
            });
            
            this.qualityOptions.forEach(option => {
                option.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const quality = e.target.dataset.quality;
                    this.setQuality(quality);
                    this.qualityMenu.classList.remove('show');
                });
            });
            
            // Close quality menu when clicking elsewhere
            document.addEventListener('click', () => {
                this.qualityMenu.classList.remove('show');
            });
        }
        
        // Fullscreen
        if (this.fullscreenBtn) {
            this.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        }
        
        // Picture in Picture
        if (this.pipBtn && document.pictureInPictureEnabled) {
            this.pipBtn.addEventListener('click', () => this.togglePictureInPicture());
        } else if (this.pipBtn) {
            this.pipBtn.style.display = 'none';
        }
        
        // Download
        if (this.downloadBtn && this.options.src) {
            this.downloadBtn.addEventListener('click', () => this.downloadVideo());
        } else if (this.downloadBtn) {
            this.downloadBtn.style.display = 'none';
        }
        
        // Video events
        this.video.addEventListener('play', () => {
            this.isPlaying = true;
            this.updatePlayPauseIcon();
        });
        
        this.video.addEventListener('pause', () => {
            this.isPlaying = false;
            this.updatePlayPauseIcon();
        });
        
        this.video.addEventListener('ended', () => {
            this.isPlaying = false;
            this.updatePlayPauseIcon();
        });
        
        this.video.addEventListener('waiting', () => {
            this.showLoading();
        });
        
        this.video.addEventListener('playing', () => {
            this.hideLoading();
        });
        
        this.video.addEventListener('error', (e) => {
            console.error('Video error:', e);
            this.showError('Error loading video');
        });
        
        // Fullscreen change
        document.addEventListener('fullscreenchange', () => {
            this.isFullscreen = !!document.fullscreenElement;
            this.updateFullscreenIcon();
        });
        
        // Picture in Picture change
        if (document.pictureInPictureEnabled) {
            document.addEventListener('enterpictureinpicture', () => {
                this.isPictureInPicture = true;
                this.updatePipIcon();
            });
            
            document.addEventListener('leavepictureinpicture', () => {
                this.isPictureInPicture = false;
                this.updatePipIcon();
            });
        }
    }
    
    setupKeyboardControls() {
        document.addEventListener('keydown', (e) => {
            // Only handle if video is focused or in player container
            if (!this.container.contains(document.activeElement) && document.activeElement !== this.video) {
                return;
            }
            
            switch (e.key.toLowerCase()) {
                case ' ':
                case 'k':
                    e.preventDefault();
                    this.togglePlay();
                    break;
                    
                case 'f':
                    e.preventDefault();
                    this.toggleFullscreen();
                    break;
                    
                case 'm':
                    e.preventDefault();
                    this.toggleMute();
                    break;
                    
                case 'arrowleft':
                    e.preventDefault();
                    this.skip(-5);
                    break;
                    
                case 'arrowright':
                    e.preventDefault();
                    this.skip(5);
                    break;
                    
                case 'arrowup':
                    e.preventDefault();
                    this.adjustVolume(0.1);
                    break;
                    
                case 'arrowdown':
                    e.preventDefault();
                    this.adjustVolume(-0.1);
                    break;
                    
                case 'c':
                    if (document.pictureInPictureEnabled) {
                        e.preventDefault();
                        this.togglePictureInPicture();
                    }
                    break;
            }
        });
    }
    
    makeResponsive() {
        // Make video responsive
        this.video.style.width = '100%';
        this.video.style.height = 'auto';
        this.video.style.maxWidth = '100%';
        
        // Handle aspect ratio
        const observer = new ResizeObserver(() => {
            const width = this.container.clientWidth;
            const height = (width * 9) / 16; // 16:9 aspect ratio
            this.video.style.height = `${height}px`;
        });
        
        observer.observe(this.container);
    }
    
    // Public methods
    setSource(src, type = 'video/mp4') {
        this.video.innerHTML = '';
        const source = document.createElement('source');
        source.src = src;
        source.type = type;
        this.video.appendChild(source);
        
        // Enable download button if available
        if (this.downloadBtn) {
            this.downloadBtn.style.display = 'block';
            this.downloadBtn.dataset.src = src;
        }
        
        // Load the new source
        this.video.load();
    }
    
    play() {
        this.video.play().catch(e => {
            console.error('Error playing video:', e);
        });
    }
    
    pause() {
        this.video.pause();
    }
    
    togglePlay() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }
    
    skip(seconds) {
        this.video.currentTime += seconds;
    }
    
    setTime(time) {
        if (time >= 0 && time <= this.duration) {
            this.video.currentTime = time;
        }
    }
    
    setVolume(volume) {
        if (volume >= 0 && volume <= 1) {
            this.video.volume = volume;
        }
    }
    
    adjustVolume(delta) {
        const newVolume = Math.max(0, Math.min(1, this.video.volume + delta));
        this.setVolume(newVolume);
    }
    
    toggleMute() {
        this.video.muted = !this.video.muted;
    }
    
    setPlaybackRate(rate) {
        if (this.playbackRates.includes(rate)) {
            this.video.playbackRate = rate;
            this.updatePlaybackRateDisplay();
        }
    }
    
    cyclePlaybackRate() {
        const currentIndex = this.playbackRates.indexOf(this.video.playbackRate);
        const nextIndex = (currentIndex + 1) % this.playbackRates.length;
        this.setPlaybackRate(this.playbackRates[nextIndex]);
    }
    
    setQuality(quality) {
        if (this.qualities.includes(quality)) {
            this.currentQuality = quality;
            
            // Update UI
            if (this.qualityBtn) {
                this.qualityBtn.querySelector('span').textContent = quality;
            }
            
            // Update active class
            this.qualityOptions.forEach(option => {
                option.classList.toggle('active', option.dataset.quality === quality);
            });
            
            // Trigger quality change event
            this.container.dispatchEvent(new CustomEvent('qualitychange', {
                detail: { quality }
            }));
            
            // In a real implementation, you would switch video source here
            console.log('Switching to quality:', quality);
        }
    }
    
    toggleFullscreen() {
        if (!this.isFullscreen) {
            if (this.container.requestFullscreen) {
                this.container.requestFullscreen();
            } else if (this.container.webkitRequestFullscreen) {
                this.container.webkitRequestFullscreen();
            } else if (this.container.msRequestFullscreen) {
                this.container.msRequestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        }
    }
    
    async togglePictureInPicture() {
        try {
            if (this.isPictureInPicture) {
                await document.exitPictureInPicture();
            } else {
                await this.video.requestPictureInPicture();
            }
        } catch (error) {
            console.error('Picture in Picture error:', error);
        }
    }
    
    downloadVideo() {
        const src = this.downloadBtn ? this.downloadBtn.dataset.src : this.options.src;
        if (!src) return;
        
        const link = document.createElement('a');
        link.href = src;
        link.download = this.options.downloadName || 'video.mp4';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    // UI update methods
    updateProgress() {
        if (!this.duration) return;
        
        this.currentTime = this.video.currentTime;
        const progressPercent = (this.currentTime / this.duration) * 100;
        
        // Update progress bar
        this.progressPlayed.style.width = `${progressPercent}%`;
        this.progressSlider.value = progressPercent;
        
        // Update time display
        this.currentTimeEl.textContent = this.formatTime(this.currentTime);
        
        // Update buffered progress
        if (this.video.buffered.length > 0) {
            const bufferedEnd = this.video.buffered.end(this.video.buffered.length - 1);
            const bufferedPercent = (bufferedEnd / this.duration) * 100;
            this.progressBuffered.style.width = `${bufferedPercent}%`;
        }
    }
    
    updateDurationDisplay() {
        this.durationEl.textContent = this.formatTime(this.duration);
        
        // Update mobile time display
        const mobileTime = this.controls.querySelector('.time-display-mobile .duration');
        if (mobileTime) {
            mobileTime.textContent = this.formatTime(this.duration);
        }
    }
    
    updatePlayPauseIcon() {
        if (!this.playPauseBtn) return;
        
        const icon = this.playPauseBtn.querySelector('i');
        if (this.isPlaying) {
            icon.className = 'fas fa-pause';
            icon.title = 'Pause';
        } else {
            icon.className = 'fas fa-play';
            icon.title = 'Play';
        }
    }
    
    updateVolumeIcon() {
        if (!this.volumeBtn) return;
        
        const icon = this.volumeBtn.querySelector('i');
        if (this.video.muted || this.video.volume === 0) {
            icon.className = 'fas fa-volume-mute';
            icon.title = 'Unmute';
        } else if (this.video.volume < 0.5) {
            icon.className = 'fas fa-volume-down';
            icon.title = 'Volume';
        } else {
            icon.className = 'fas fa-volume-up';
            icon.title = 'Volume';
        }
    }
    
    updatePlaybackRateDisplay() {
        if (!this.playbackRateBtn) return;
        
        this.playbackRateBtn.querySelector('span').textContent = `${this.video.playbackRate}x`;
    }
    
    updateFullscreenIcon() {
        if (!this.fullscreenBtn) return;
        
        const icon = this.fullscreenBtn.querySelector('i');
        if (this.isFullscreen) {
            icon.className = 'fas fa-compress';
            icon.title = 'Exit fullscreen';
        } else {
            icon.className = 'fas fa-expand';
            icon.title = 'Fullscreen';
        }
    }
    
    updatePipIcon() {
        if (!this.pipBtn) return;
        
        const icon = this.pipBtn.querySelector('i');
        if (this.isPictureInPicture) {
            icon.className = 'fas fa-times-circle';
            icon.title = 'Exit Picture in Picture';
        } else {
            icon.className = 'fas fa-picture-in-picture';
            icon.title = 'Picture in Picture';
        }
    }
    
    formatTime(seconds) {
        if (isNaN(seconds)) return '00:00';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
    }
    
    showLoading() {
        // Add loading spinner
        let spinner = this.container.querySelector('.loading-spinner');
        if (!spinner) {
            spinner = document.createElement('div');
            spinner.className = 'loading-spinner';
            spinner.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            this.container.appendChild(spinner);
        }
        spinner.style.display = 'block';
    }
    
    hideLoading() {
        const spinner = this.container.querySelector('.loading-spinner');
        if (spinner) {
            spinner.style.display = 'none';
        }
    }
    
    showError(message) {
        // Remove existing error
        this.hideError();
        
        // Create error overlay
        const errorOverlay = document.createElement('div');
        errorOverlay.className = 'video-error-overlay';
        errorOverlay.innerHTML = `
            <div class="error-content">
                <i class="fas fa-exclamation-triangle"></i>
                <p>${message}</p>
                <button class="btn btn-primary retry-btn">Retry</button>
            </div>
        `;
        
        this.container.appendChild(errorOverlay);
        
        // Add retry button event
        const retryBtn = errorOverlay.querySelector('.retry-btn');
        retryBtn.addEventListener('click', () => {
            this.video.load();
            this.hideError();
        });
    }
    
    hideError() {
        const errorOverlay = this.container.querySelector('.video-error-overlay');
        if (errorOverlay) {
            errorOverlay.remove();
        }
    }
    
    // Public API
    getVideoElement() {
        return this.video;
    }
    
    getCurrentTime() {
        return this.currentTime;
    }
    
    getDuration() {
        return this.duration;
    }
    
    getVolume() {
        return this.video.volume;
    }
    
    getPlaybackRate() {
        return this.video.playbackRate;
    }
    
    getCurrentQuality() {
        return this.currentQuality;
    }
    
    destroy() {
        // Remove event listeners
        this.video.replaceWith(this.video.cloneNode(true));
        this.controls.remove();
        
        // Clean up references
        this.video = null;
        this.controls = null;
    }
}

// Initialize video players automatically
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-video-player]').forEach(container => {
        const options = JSON.parse(container.dataset.videoPlayerOptions || '{}');
        new VideoPlayer(container.id, options);
    });
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = VideoPlayer;
}