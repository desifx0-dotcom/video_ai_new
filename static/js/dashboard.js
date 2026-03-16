/**
 * Dashboard interactivity and functionality
 * Production version with dual auth support (Session + JWT)
 */

class Dashboard {
    constructor() {
        this.token = localStorage.getItem('access_token');
        this.refreshToken = localStorage.getItem('refresh_token');
        this.tokenExpiry = localStorage.getItem('token_expiry');
        this.sidebar = document.getElementById('sidebar');
        this.sidebarToggle = document.getElementById('sidebar-toggle');
        this.sidebarOverlay = document.getElementById('sidebar-overlay');
        this.themeToggle = document.getElementById('theme-toggle');
        this.videoGrid = document.getElementById('video-grid');
        this.statsCards = document.querySelectorAll('.stat-card');
        this.notificationBell = document.getElementById('notification-bell');
        this.notificationPanel = document.getElementById('notification-panel');
        
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.unreadNotifications = 0;
        this.authenticated = false;
        this.authMethod = null; // 'session' or 'token'
        
        // Start initialization
        this.init();
    }
    
    async init() {
        try {
            // First check if we're authenticated
            const authStatus = await this.checkAuthStatus();
            
            if (!authStatus.authenticated) {
                console.log('Not authenticated, redirecting to login');
                window.location.href = '/auth/login';
                return;
            }
            
            // Store auth method
            this.authenticated = true;
            this.authMethod = authStatus.method;
            
            console.log(`✅ Authenticated via ${this.authMethod}`);
            
            // Proceed with dashboard setup
            this.setupEventListeners();
            this.applyTheme();
            
            // Load all dashboard data
            await Promise.all([
                this.loadUserStats(),
                this.loadVideos(),
                this.setupNotifications(),
                this.setupRealTimeUpdates()
            ]);
            
            // Request notification permission if needed
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }
            
            // Expose for debugging (development only)
            if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                window.dashboard = this;
            }
            
        } catch (error) {
            console.error('Dashboard initialization failed:', error);
            this.showNotification('Failed to load dashboard', 'error');
        }
    }
    
    async checkAuthStatus() {
        try {
            // First check session (most reliable)
            const sessionResponse = await fetch('/api/v1/auth/session-check', {
                credentials: 'same-origin',
                headers: { 'Cache-Control': 'no-cache' }
            });
            
            if (sessionResponse.ok) {
                const sessionData = await sessionResponse.json();
                if (sessionData.authenticated) {
                    return { authenticated: true, method: 'session' };
                }
            }
            
            // If no session, check token
            if (this.token) {
                // Validate token with a lightweight call
                const tokenResponse = await fetch('/api/v1/users/stats', {
                    headers: { 'Authorization': `Bearer ${this.token}` }
                });
                
                if (tokenResponse.ok) {
                    return { authenticated: true, method: 'token' };
                }
                
                // Token expired, try refresh
                if (tokenResponse.status === 401 && this.refreshToken) {
                    const refreshed = await this.refreshAccessToken();
                    if (refreshed) {
                        return { authenticated: true, method: 'token' };
                    }
                }
            }
            
            return { authenticated: false };
            
        } catch (error) {
            console.error('Auth check failed:', error);
            return { authenticated: false };
        }
    }
    
    async refreshAccessToken() {
        try {
            const response = await fetch('/api/v1/auth/refresh', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.refreshToken}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.token = data.access_token;
                localStorage.setItem('access_token', this.token);
                
                const expiry = Date.now() + (24 * 60 * 60 * 1000);
                localStorage.setItem('token_expiry', expiry);
                
                return true;
            }
            
            this.clearTokens();
            return false;
            
        } catch (error) {
            console.error('Token refresh failed:', error);
            return false;
        }
    }
    
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('token_expiry');
        this.token = null;
        this.refreshToken = null;
        this.tokenExpiry = null;
    }
    
    async fetchWithAuth(url, options = {}) {
        // Set default headers
        const headers = {
            'Content-Type': 'application/json',
            'X-CSRF-Token': this.getCSRFToken()
        };
        
        // If you have a token, add it (optional)
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        
        // Merge with custom headers
        options.headers = { ...headers, ...options.headers };
        options.credentials = 'same-origin';  // Important: send session cookies
        
        try {
            const response = await fetch(url, options);
            
            // If unauthorized but session exists, it might be a token issue
            if (response.status === 401) {
                // Try without token (session only)
                console.log('Token auth failed, trying session auth');
                delete options.headers['Authorization'];
                return fetch(url, options);
            }
            
            return response;
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
    // ========== EVENT LISTENERS ==========
    
    setupEventListeners() {
        // Sidebar toggle
        if (this.sidebarToggle) {
            this.sidebarToggle.addEventListener('click', () => this.toggleSidebar());
        }
        
        // Sidebar overlay
        if (this.sidebarOverlay) {
            this.sidebarOverlay.addEventListener('click', () => this.closeSidebar());
        }
        
        // Theme toggle
        if (this.themeToggle) {
            this.themeToggle.addEventListener('click', () => this.toggleTheme());
        }
        
        // Notifications
        if (this.notificationBell) {
            this.notificationBell.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleNotifications();
            });
        }
        
        // Close notifications when clicking outside
        document.addEventListener('click', (e) => {
            if (this.notificationPanel && this.notificationPanel.style.display === 'block') {
                if (!this.notificationPanel.contains(e.target) && 
                    !this.notificationBell.contains(e.target)) {
                    this.closeNotifications();
                }
            }
        });
        
        // Escape key to close sidebar and notifications
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeSidebar();
                this.closeNotifications();
            }
        });
        
        // Resize handler
        window.addEventListener('resize', () => this.handleResize());
    }
    
    // ========== SIDEBAR ==========
    
    toggleSidebar() {
        this.sidebar.classList.toggle('open');
        this.sidebarOverlay.classList.toggle('open');
        
        if (this.sidebar.classList.contains('open')) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
    }
    
    closeSidebar() {
        this.sidebar.classList.remove('open');
        this.sidebarOverlay.classList.remove('open');
        document.body.style.overflow = '';
    }
    
    // ========== THEME ==========
    
    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', this.currentTheme);
        this.applyTheme();
    }
    
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.currentTheme);
        
        if (this.themeToggle) {
            const lightIcon = this.themeToggle.querySelector('.light-icon');
            const darkIcon = this.themeToggle.querySelector('.dark-icon');
            
            if (lightIcon && darkIcon) {
                if (this.currentTheme === 'light') {
                    lightIcon.style.display = 'block';
                    darkIcon.style.display = 'none';
                } else {
                    lightIcon.style.display = 'none';
                    darkIcon.style.display = 'block';
                }
            }
        }
    }
    
    // ========== USER STATS ==========
    
    async loadUserStats() {
        try {
            const response = await this.fetchWithAuth('/api/v1/users/stats');
            if (response && response.ok) {
                const stats = await response.json();
                this.updateStatsCards(stats);
            }
        } catch (error) {
            console.error('Failed to load user stats:', error);
        }
    }
    
    updateStatsCards(stats) {
        this.statsCards.forEach(card => {
            const statType = card.dataset.stat;
            if (stats[statType] !== undefined) {
                const valueElement = card.querySelector('.stat-value');
                if (valueElement) {
                    valueElement.textContent = this.formatStatValue(statType, stats[statType]);
                }
            }
        });
    }
    
    formatStatValue(statType, value) {
        switch (statType) {
            case 'credits_remaining':
                return value.toLocaleString();
            case 'total_processing_time':
                return this.formatDuration(value);
            case 'total_cost':
                return `$${value.toFixed(2)}`;
            case 'videos_processed':
                return value.toLocaleString();
            default:
                return value;
        }
    }
    
    // ========== VIDEOS ==========
    
    async loadVideos(limit = 12) {
        if (!this.videoGrid) return;
        
        try {
            const response = await this.fetchWithAuth(`/api/v1/videos?limit=${limit}`);
            if (response && response.ok) {
                const data = await response.json();
                const videos = data.videos || data;
                this.renderVideos(videos);
            }
        } catch (error) {
            console.error('Failed to load videos:', error);
            this.showEmptyState();
        }
    }
    
    renderVideos(videos) {
        if (!videos || videos.length === 0) {
            this.showEmptyState();
            return;
        }
        
        this.videoGrid.innerHTML = '';
        
        videos.forEach(video => {
            const videoCard = this.createVideoCard(video);
            this.videoGrid.appendChild(videoCard);
        });
    }
    
    createVideoCard(video) {
        const card = document.createElement('div');
        card.className = 'video-card';
        card.dataset.videoId = video.id;
        
        const thumbnailUrl = video.selected_thumbnail || '/static/images/placeholder.jpg';
        const duration = this.formatDuration(video.duration);
        const uploadDate = new Date(video.created_at).toLocaleDateString();
        const statusClass = `status-${video.status}`;
        
        card.innerHTML = `
            <div class="video-thumbnail">
                <img src="${thumbnailUrl}" alt="${video.title || video.original_filename}" loading="lazy">
                <div class="video-overlay">
                    <span class="video-duration">${duration}</span>
                </div>
            </div>
            <div class="video-info">
                <h3 class="video-title" title="${video.title || video.original_filename}">
                    ${video.title || video.original_filename}
                </h3>
                <div class="video-meta">
                    <span class="video-date">${uploadDate}</span>
                    <span class="video-status ${statusClass}">${video.status}</span>
                </div>
                <div class="video-actions">
                    <button class="btn btn-sm btn-outline view-video" data-video-id="${video.id}">
                        <i class="fas fa-eye"></i> View
                    </button>
                    <button class="btn btn-sm btn-outline download-video" data-video-id="${video.id}">
                        <i class="fas fa-download"></i> Download
                    </button>
                    <button class="btn btn-sm btn-outline delete-video" data-video-id="${video.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        
        const viewBtn = card.querySelector('.view-video');
        const downloadBtn = card.querySelector('.download-video');
        const deleteBtn = card.querySelector('.delete-video');
        
        viewBtn.addEventListener('click', () => this.viewVideo(video.id));
        downloadBtn.addEventListener('click', () => this.downloadVideo(video.id));
        deleteBtn.addEventListener('click', () => this.deleteVideo(video.id));
        
        return card;
    }
    
    showEmptyState() {
        if (!this.videoGrid) return;
        
        this.videoGrid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">
                    <i class="fas fa-video-slash"></i>
                </div>
                <h3>No videos yet</h3>
                <p>Upload your first video to get started with AI processing.</p>
                <a href="/dashboard/upload" class="btn btn-primary mt-3">
                    <i class="fas fa-upload"></i> Upload Video
                </a>
            </div>
        `;
    }
    
    viewVideo(videoId) {
        window.location.href = `/dashboard/results/${videoId}`;
    }
    
    async downloadVideo(videoId) {
        try {
            const response = await this.fetchWithAuth(`/api/v1/videos/${videoId}/download`);
            if (response && response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `video-${videoId}.mp4`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            } else {
                this.showNotification('Failed to download video', 'error');
            }
        } catch (error) {
            console.error('Download error:', error);
            this.showNotification('Failed to download video', 'error');
        }
    }
    
    async deleteVideo(videoId) {
        if (!confirm('Are you sure you want to delete this video? This action cannot be undone.')) {
            return;
        }
        
        try {
            const response = await this.fetchWithAuth(`/api/v1/videos/${videoId}`, {
                method: 'DELETE'
            });
            
            if (response && response.ok) {
                const videoCard = document.querySelector(`.video-card[data-video-id="${videoId}"]`);
                if (videoCard) {
                    videoCard.remove();
                }
                
                this.showNotification('Video deleted successfully', 'success');
                this.loadUserStats();
                
                if (this.videoGrid && this.videoGrid.children.length === 0) {
                    this.showEmptyState();
                }
            } else {
                const data = await response.json();
                this.showNotification(data.message || 'Failed to delete video', 'error');
            }
        } catch (error) {
            console.error('Delete error:', error);
            this.showNotification('Failed to delete video', 'error');
        }
    }
    
    // ========== NOTIFICATIONS ==========
    
    async setupNotifications() {
        await this.loadNotifications();
        setInterval(() => this.checkNewNotifications(), 30000);
    }
    
    async loadNotifications() {
        try {
            const response = await this.fetchWithAuth('/api/v1/notifications');
            if (response && response.ok) {
                const data = await response.json();
                const notifications = data.notifications || data;
                this.updateNotificationBadge(notifications);
            }
        } catch (error) {
            console.error('Failed to load notifications:', error);
        }
    }
    
    async checkNewNotifications() {
        try {
            const response = await this.fetchWithAuth('/api/v1/notifications/unread-count');
            if (response && response.ok) {
                const data = await response.json();
                if (data.count > this.unreadNotifications) {
                    this.showNewNotification();
                }
                this.unreadNotifications = data.count;
                this.updateNotificationBadgeCount(data.count);
            }
        } catch (error) {
            console.error('Failed to check notifications:', error);
        }
    }
    
    updateNotificationBadge(notifications) {
        const unreadCount = notifications.filter(n => !n.read).length;
        this.unreadNotifications = unreadCount;
        this.updateNotificationBadgeCount(unreadCount);
    }
    
    updateNotificationBadgeCount(count) {
        if (!this.notificationBell) return;
        
        const badge = this.notificationBell.querySelector('.notification-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.style.display = 'block';
            } else {
                badge.style.display = 'none';
            }
        }
    }
    
    showNewNotification() {
        if (Notification.permission === 'granted') {
            new Notification('Video AI Studio', {
                body: 'You have new notifications',
                icon: '/static/images/logo-light.svg'
            });
        }
        
        this.showNotification('New notifications available', 'info');
    }
    
    toggleNotifications() {
        if (!this.notificationPanel) return;
        
        if (this.notificationPanel.style.display === 'block') {
            this.closeNotifications();
        } else {
            this.openNotifications();
        }
    }
    
    openNotifications() {
        this.notificationPanel.style.display = 'block';
        this.loadNotificationPanel();
    }
    
    closeNotifications() {
        this.notificationPanel.style.display = 'none';
    }
    
    async loadNotificationPanel() {
        try {
            const response = await this.fetchWithAuth('/api/v1/notifications?limit=10');
            if (response && response.ok) {
                const data = await response.json();
                const notifications = data.notifications || data;
                this.renderNotificationPanel(notifications);
            }
        } catch (error) {
            console.error('Failed to load notification panel:', error);
        }
    }
    
    renderNotificationPanel(notifications) {
        if (!this.notificationPanel) return;
        
        const container = this.notificationPanel.querySelector('.notification-list');
        if (!container) return;
        
        if (!notifications || notifications.length === 0) {
            container.innerHTML = `
                <div class="notification-empty">
                    <i class="fas fa-bell-slash"></i>
                    <p>No notifications</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = notifications.map(notification => `
            <div class="notification-item ${notification.read ? 'read' : 'unread'}" data-notification-id="${notification.id}">
                <div class="notification-icon">
                    <i class="fas ${this.getNotificationIcon(notification.type)}"></i>
                </div>
                <div class="notification-content">
                    <p class="notification-text">${notification.message}</p>
                    <span class="notification-time">${this.formatTimeAgo(notification.created_at)}</span>
                </div>
                <button class="notification-mark-read" title="Mark as read">
                    <i class="fas fa-check"></i>
                </button>
            </div>
        `).join('');
        
        container.querySelectorAll('.notification-mark-read').forEach(button => {
            button.addEventListener('click', async (e) => {
                const notificationItem = e.target.closest('.notification-item');
                const notificationId = notificationItem.dataset.notificationId;
                await this.markNotificationAsRead(notificationId);
            });
        });
    }
    
    getNotificationIcon(type) {
        const icons = {
            'video_completed': 'fa-check-circle',
            'video_failed': 'fa-exclamation-circle',
            'tier_upgraded': 'fa-arrow-up',
            'payment_received': 'fa-credit-card',
            'credits_low': 'fa-exclamation-triangle',
            'system': 'fa-info-circle'
        };
        
        return icons[type] || 'fa-bell';
    }
    
    async markNotificationAsRead(notificationId) {
        try {
            const response = await this.fetchWithAuth(`/api/v1/notifications/${notificationId}/read`, {
                method: 'POST'
            });
            
            if (response && response.ok) {
                const notificationItem = document.querySelector(`.notification-item[data-notification-id="${notificationId}"]`);
                if (notificationItem) {
                    notificationItem.classList.remove('unread');
                    notificationItem.classList.add('read');
                }
                
                this.unreadNotifications = Math.max(0, this.unreadNotifications - 1);
                this.updateNotificationBadgeCount(this.unreadNotifications);
            }
        } catch (error) {
            console.error('Failed to mark notification as read:', error);
        }
    }
    
    // ========== REAL-TIME UPDATES ==========
    
    setupRealTimeUpdates() {
        this.setupWebSocket();
        this.pollVideoStatus();
    }
    
    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = this.authMethod === 'token' && this.token ? `?token=${this.token}` : '';
        const wsUrl = `${protocol}//${window.location.host}/ws${token}`;
        
        try {
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('WebSocket connected');
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };
            
            this.socket.onclose = () => {
                console.log('WebSocket disconnected');
                setTimeout(() => this.setupWebSocket(), 5000);
            };
            
            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        } catch (error) {
            console.error('Failed to setup WebSocket:', error);
        }
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'video_processing':
                this.updateVideoStatus(data.video_id, data.status, data.progress);
                break;
            case 'video_completed':
                this.showVideoCompleted(data.video_id);
                break;
            case 'video_failed':
                this.showVideoFailed(data.video_id, data.error);
                break;
            case 'notification':
                this.showNewNotification();
                break;
            case 'credits_updated':
                this.updateCredits(data.credits_remaining);
                break;
        }
    }
    
    updateVideoStatus(videoId, status, progress) {
        const videoCard = document.querySelector(`.video-card[data-video-id="${videoId}"]`);
        if (videoCard) {
            const statusElement = videoCard.querySelector('.video-status');
            if (statusElement) {
                statusElement.textContent = status;
                statusElement.className = `video-status status-${status}`;
            }
        }
        
        if (window.location.pathname.includes(`/processing/${videoId}`)) {
            this.updateProcessingProgress(progress);
        }
    }
    
    showVideoCompleted(videoId) {
        this.showNotification('Video processing completed!', 'success');
        this.updateVideoStatus(videoId, 'completed', 100);
        this.loadUserStats();
        this.loadVideos();
    }
    
    showVideoFailed(videoId, error) {
        this.showNotification(`Video processing failed: ${error}`, 'error');
        this.updateVideoStatus(videoId, 'failed', 0);
    }
    
    updateProcessingProgress(progress) {
        const progressBar = document.querySelector('.progress-bar-fill');
        const progressText = document.querySelector('.progress-percentage');
        
        if (progressBar) {
            progressBar.style.width = `${progress}%`;
        }
        
        if (progressText) {
            progressText.textContent = `${Math.round(progress)}%`;
        }
    }
    
    updateCredits(credits) {
        const creditsElement = document.getElementById('credits-display');
        if (creditsElement) {
            creditsElement.textContent = `${credits} credits remaining`;
        }
    }
    
    pollVideoStatus() {
        setInterval(() => {
            this.loadUserStats();
            this.loadVideos(6);
        }, 10000);
    }
    
    // ========== UTILITIES ==========
    
    handleResize() {
        if (window.innerWidth >= 1024) {
            this.closeSidebar();
        }
    }
    
    showNotification(message, type = 'info') {
        const existing = document.querySelector('.global-notification');
        if (existing) {
            existing.remove();
        }
        
        const notification = document.createElement('div');
        notification.className = `global-notification alert alert-${type}`;
        notification.innerHTML = `
            ${message}
            <button class="btn-close" onclick="this.parentElement.remove()"></button>
        `;
        notification.style.position = 'fixed';
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '10000';
        notification.style.maxWidth = '400px';
        notification.style.minWidth = '250px';
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }
    
    getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }
    
    formatDuration(seconds) {
        if (!seconds) return '0:00';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, '0')}`;
        }
    }
    
    formatTimeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffDays > 0) {
            return `${diffDays}d ago`;
        } else if (diffHours > 0) {
            return `${diffHours}h ago`;
        } else if (diffMins > 0) {
            return `${diffMins}m ago`;
        } else {
            return 'Just now';
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('video-grid') || document.querySelector('.stat-card')) {
        new Dashboard();
    }
});