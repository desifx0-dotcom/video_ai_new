/**
 * Video preview and playback functionality.
 */

class VideoPreview {
  constructor() {
    this.videoElement = null;
    this.previewContainer = null;
    this.thumbnails = [];
    this.currentVideo = null;
    this.init();
  }

  init() {
    this.videoElement = document.getElementById('video-preview');
    this.previewContainer = document.getElementById('video-preview-container');

    if (this.videoElement) {
      this.setupVideoPlayer();
    }

    this.setupEventListeners();
    this.loadThumbnails();
  }

  setupVideoPlayer() {
    // Initialize video.js if available
    if (typeof videojs !== 'undefined') {
      this.player = videojs(this.videoElement, {
        controls: true,
        autoplay: false,
        preload: 'auto',
        responsive: true,
        fluid: true,
        playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
        plugins: {
          hotkeys: {
            enableModifiersForNumbers: false,
            volumeStep: 0.1,
            seekStep: 5
          }
        }
      });
    } else {
      // Fallback to native video player
      this.setupNativePlayer();
    }
  }

  setupNativePlayer() {
    const video = this.videoElement;

    // Add custom controls
    this.addCustomControls();

    // Handle keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (!this.isVideoInViewport()) return;

      switch (e.key) {
        case ' ':
          e.preventDefault();
          this.togglePlayPause();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          this.seek(-5);
          break;
        case 'ArrowRight':
          e.preventDefault();
          this.seek(5);
          break;
        case 'ArrowUp':
          e.preventDefault();
          this.adjustVolume(0.1);
          break;
        case 'ArrowDown':
          e.preventDefault();
          this.adjustVolume(-0.1);
          break;
        case 'f':
        case 'F':
          e.preventDefault();
          this.toggleFullscreen();
          break;
        case 'm':
        case 'M':
          e.preventDefault();
          this.toggleMute();
          break;
      }
    });
  }

  addCustomControls() {
    const video = this.videoElement;
    const controlsContainer = document.createElement('div');
    controlsContainer.className = 'custom-video-controls';

    controlsContainer.innerHTML = `
            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill"></div>
                    <div class="progress-thumb"></div>
                </div>
                <div class="time-display">
                    <span class="current-time">0:00</span> / <span class="duration">0:00</span>
                </div>
            </div>
            <div class="controls-row">
                <div class="left-controls">
                    <button class="control-btn play-pause">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="control-btn mute">
                        <i class="fas fa-volume-up"></i>
                    </button>
                    <div class="volume-slider">
                        <input type="range" min="0" max="100" value="100" class="volume-control">
                    </div>
                </div>
                <div class="right-controls">
                    <button class="control-btn fullscreen">
                        <i class="fas fa-expand"></i>
                    </button>
                    <button class="control-btn settings">
                        <i class="fas fa-cog"></i>
                    </button>
                </div>
            </div>
        `;

    video.parentNode.insertBefore(controlsContainer, video.nextSibling);
    this.setupCustomControls(controlsContainer);
  }

  setupCustomControls(container) {
    const video = this.videoElement;
    const playPauseBtn = container.querySelector('.play-pause');
    const muteBtn = container.querySelector('.mute');
    const volumeSlider = container.querySelector('.volume-control');
    const fullscreenBtn = container.querySelector('.fullscreen');
    const progressBar = container.querySelector('.progress-bar');
    const progressFill = container.querySelector('.progress-fill');
    const currentTimeEl = container.querySelector('.current-time');
    const durationEl = container.querySelector('.duration');

    // Play/Pause
    playPauseBtn.addEventListener('click', () => this.togglePlayPause());
    video.addEventListener('play', () => {
      playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
    });
    video.addEventListener('pause', () => {
      playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
    });

    // Mute/Volume
    muteBtn.addEventListener('click', () => this.toggleMute());
    volumeSlider.addEventListener('input', (e) => {
      video.volume = e.target.value / 100;
      muteBtn.innerHTML = video.volume === 0 ?
        '<i class="fas fa-volume-mute"></i>' :
        '<i class="fas fa-volume-up"></i>';
    });

    // Fullscreen
    fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());

    // Progress bar
    progressBar.addEventListener('click', (e) => {
      const rect = progressBar.getBoundingClientRect();
      const pos = (e.clientX - rect.left) / rect.width;
      video.currentTime = pos * video.duration;
    });

    // Update progress and time
    video.addEventListener('timeupdate', () => {
      if (video.duration) {
        const progress = (video.currentTime / video.duration) * 100;
        progressFill.style.width = `${progress}%`;
        currentTimeEl.textContent = this.formatTime(video.currentTime);
      }
    });

    video.addEventListener('loadedmetadata', () => {
      durationEl.textContent = this.formatTime(video.duration);
    });
  }

  setupEventListeners() {
    // Handle video file selection
    const fileInput = document.getElementById('video-file');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        this.handleFileSelect(e.target.files[0]);
      });
    }

    // Handle drag and drop
    const dropZone = document.getElementById('video-drop-zone');
    if (dropZone) {
      dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
      });

      dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
      });

      dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');

        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('video/')) {
          this.handleFileSelect(file);
        }
      });
    }

    // Handle thumbnail selection
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('thumbnail-select')) {
        this.selectThumbnail(e.target.dataset.index);
      }
    });
  }

  async handleFileSelect(file) {
    if (!file || !file.type.startsWith('video/')) {
      alert('Please select a valid video file.');
      return;
    }

    // Check file size (max 2GB)
    if (file.size > 2 * 1024 * 1024 * 1024) {
      alert('File size exceeds 2GB limit.');
      return;
    }

    this.showLoading(true);

    try {
      // Create preview URL
      const url = URL.createObjectURL(file);

      // Set video source
      if (this.player) {
        this.player.src({ type: file.type, src: url });
      } else {
        this.videoElement.src = url;
      }

      // Extract metadata
      const metadata = await this.extractVideoMetadata(file);
      this.updateVideoInfo(metadata);

      // Generate thumbnails
      await this.generateThumbnails(file);

    } catch (error) {
      console.error('Error handling video file:', error);
      alert('Error loading video file.');
    } finally {
      this.showLoading(false);
    }
  }

  async extractVideoMetadata(file) {
    return new Promise((resolve) => {
      const video = document.createElement('video');
      video.preload = 'metadata';

      video.onloadedmetadata = () => {
        resolve({
          duration: video.duration,
          width: video.videoWidth,
          height: video.videoHeight,
          size: file.size,
          type: file.type,
          name: file.name
        });
      };

      video.src = URL.createObjectURL(file);
    });
  }

  updateVideoInfo(metadata) {
    const infoContainer = document.getElementById('video-info');
    if (!infoContainer) return;

    infoContainer.innerHTML = `
            <div class="video-metadata">
                <div class="metadata-item">
                    <span class="label">Name:</span>
                    <span class="value">${metadata.name}</span>
                </div>
                <div class="metadata-item">
                    <span class="label">Duration:</span>
                    <span class="value">${this.formatTime(metadata.duration)}</span>
                </div>
                <div class="metadata-item">
                    <span class="label">Resolution:</span>
                    <span class="value">${metadata.width} × ${metadata.height}</span>
                </div>
                <div class="metadata-item">
                    <span class="label">Size:</span>
                    <span class="value">${this.formatFileSize(metadata.size)}</span>
                </div>
                <div class="metadata-item">
                    <span class="label">Format:</span>
                    <span class="value">${metadata.type.split('/')[1].toUpperCase()}</span>
                </div>
            </div>
        `;
  }

  async generateThumbnails(file) {
    const thumbnailsContainer = document.getElementById('video-thumbnails');
    if (!thumbnailsContainer) return;

    thumbnailsContainer.innerHTML = '<div class="loading">Generating thumbnails...</div>';

    try {
      const thumbnails = await this.extractThumbnails(file, 5);
      this.thumbnails = thumbnails;

      thumbnailsContainer.innerHTML = thumbnails.map((thumb, index) => `
                <div class="thumbnail-item" data-index="${index}">
                    <img src="${thumb}" alt="Thumbnail ${index + 1}" class="thumbnail-img">
                    <button class="btn btn-sm btn-primary thumbnail-select" data-index="${index}">
                        Select
                    </button>
                </div>
            `).join('');

    } catch (error) {
      console.error('Error generating thumbnails:', error);
      thumbnailsContainer.innerHTML = '<div class="error">Failed to generate thumbnails</div>';
    }
  }

  async extractThumbnails(file, count = 5) {
    return new Promise((resolve, reject) => {
      const video = document.createElement('video');
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const thumbnails = [];

      video.preload = 'metadata';
      video.src = URL.createObjectURL(file);

      video.onloadedmetadata = () => {
        const duration = video.duration;
        const interval = duration / (count + 1);

        let loaded = 0;

        for (let i = 1; i <= count; i++) {
          const time = interval * i;

          video.currentTime = time;

          video.onseeked = () => {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

            thumbnails.push({
              time: time,
              dataUrl: canvas.toDataURL('image/jpeg', 0.8)
            });

            loaded++;

            if (loaded === count) {
              resolve(thumbnails.map(t => t.dataUrl));
            }
          };
        }
      };

      video.onerror = reject;
    });
  }

  selectThumbnail(index) {
    // Remove previous selection
    document.querySelectorAll('.thumbnail-item.selected').forEach(item => {
      item.classList.remove('selected');
    });

    // Add selection to clicked thumbnail
    const thumbnailItem = document.querySelector(`.thumbnail-item[data-index="${index}"]`);
    if (thumbnailItem) {
      thumbnailItem.classList.add('selected');

      // Update hidden input for form submission
      const thumbnailInput = document.getElementById('selected-thumbnail');
      if (thumbnailInput) {
        thumbnailInput.value = this.thumbnails[index];
      }

      // Show confirmation
      alert(`Thumbnail ${parseInt(index) + 1} selected`);
    }
  }

  loadThumbnails() {
    // Load existing thumbnails from server if editing
    const videoId = this.getVideoId();
    if (videoId) {
      this.fetchVideoThumbnails(videoId);
    }
  }

  async fetchVideoThumbnails(videoId) {
    try {
      const response = await fetch(`/api/v1/videos/${videoId}/thumbnails`);
      if (!response.ok) throw new Error('Failed to fetch thumbnails');

      const data = await response.json();
      this.displayThumbnails(data.thumbnails);
    } catch (error) {
      console.error('Error fetching thumbnails:', error);
    }
  }

  displayThumbnails(thumbnails) {
    const container = document.getElementById('video-thumbnails');
    if (!container) return;

    container.innerHTML = thumbnails.map((thumb, index) => `
            <div class="thumbnail-item" data-index="${index}">
                <img src="${thumb.url}" alt="Thumbnail ${index + 1}" class="thumbnail-img">
                <button class="btn btn-sm btn-primary thumbnail-select" data-index="${index}">
                    Select
                </button>
            </div>
        `).join('');
  }

  togglePlayPause() {
    if (this.player) {
      if (this.player.paused()) {
        this.player.play();
      } else {
        this.player.pause();
      }
    } else {
      const video = this.videoElement;
      if (video.paused) {
        video.play();
      } else {
        video.pause();
      }
    }
  }

  seek(seconds) {
    if (this.player) {
      this.player.currentTime(this.player.currentTime() + seconds);
    } else {
      this.videoElement.currentTime += seconds;
    }
  }

  adjustVolume(delta) {
    if (this.player) {
      const newVolume = Math.max(0, Math.min(1, this.player.volume() + delta));
      this.player.volume(newVolume);
    } else {
      const newVolume = Math.max(0, Math.min(1, this.videoElement.volume + delta));
      this.videoElement.volume = newVolume;
    }
  }

  toggleMute() {
    if (this.player) {
      this.player.muted(!this.player.muted());
    } else {
      this.videoElement.muted = !this.videoElement.muted;
    }
  }

  toggleFullscreen() {
    const container = this.previewContainer || this.videoElement.parentElement;

    if (!document.fullscreenElement) {
      if (container.requestFullscreen) {
        container.requestFullscreen();
      } else if (container.webkitRequestFullscreen) {
        container.webkitRequestFullscreen();
      } else if (container.msRequestFullscreen) {
        container.msRequestFullscreen();
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

  isVideoInViewport() {
    const rect = this.videoElement.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
  }

  formatTime(seconds) {
    if (isNaN(seconds)) return '0:00';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
      return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
  }

  formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  showLoading(show) {
    const loadingElement = document.getElementById('video-loading');
    if (loadingElement) {
      loadingElement.style.display = show ? 'block' : 'none';
    }
  }

  getVideoId() {
    // Extract video ID from URL or data attribute
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('id') ||
      document.querySelector('[data-video-id]')?.dataset.videoId;
  }
}

// Initialize video preview
document.addEventListener('DOMContentLoaded', () => {
  window.videoPreview = new VideoPreview();
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = VideoPreview;
}