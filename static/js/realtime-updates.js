"""
Real-time updates via WebSocket.
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class RealtimeUpdates:
    """Handle real-time updates via WebSocket."""
    
    def __init__(self):
        self.socket = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1000  # ms
        self.subscriptions = {}
        self.event_handlers = {}
        
    def connect(self, token: Optional[str] = None):
        """Connect to WebSocket server."""
        if self.connected:
            logger.warning("Already connected to WebSocket")
            return
            
        try:
            # Get WebSocket URL from current page
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            const ws_url = `${protocol}//${host}/socket.io`;
            
            # Connect to Socket.IO
            this.socket = io(ws_url, {
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionAttempts: this.max_reconnect_attempts,
                reconnectionDelay: this.reconnect_delay
            });
            
            # Setup event handlers
            this.setupSocketEvents();
            
            # Authenticate if token is provided
            if (token) {
                this.authenticate(token);
            }
            
        } catch (error) {
            logger.error("Failed to connect to WebSocket:", error);
            this.scheduleReconnect();
        }
    
    def setupSocketEvents(self):
        """Setup Socket.IO event handlers."""
        if (!this.socket) return;
        
        // Connection events
        this.socket.on('connect', () => {
            logger.info("Connected to WebSocket");
            this.connected = true;
            this.reconnect_attempts = 0;
            this.emit('connected');
            
            // Resubscribe to previous subscriptions
            this.resubscribe();
        });
        
        this.socket.on('disconnect', (reason) => {
            logger.warn("Disconnected from WebSocket:", reason);
            this.connected = false;
            this.emit('disconnected', { reason });
            
            if (reason === 'io server disconnect') {
                // Server disconnected, try to reconnect
                this.socket.connect();
            }
        });
        
        this.socket.on('connect_error', (error) => {
            logger.error("WebSocket connection error:", error);
            this.emit('connection_error', { error });
        });
        
        this.socket.on('reconnect', (attempt) => {
            logger.info("Reconnected to WebSocket, attempt:", attempt);
            this.connected = true;
            this.emit('reconnected', { attempt });
        });
        
        this.socket.on('reconnect_attempt', (attempt) => {
            logger.info("Reconnection attempt:", attempt);
            this.reconnect_attempts = attempt;
            this.emit('reconnect_attempt', { attempt });
        });
        
        this.socket.on('reconnect_error', (error) => {
            logger.error("Reconnection error:", error);
            this.emit('reconnect_error', { error });
        });
        
        this.socket.on('reconnect_failed', () => {
            logger.error("Failed to reconnect to WebSocket");
            this.emit('reconnect_failed');
        });
        
        // Authentication events
        this.socket.on('authenticated', (data) => {
            logger.info("WebSocket authenticated");
            this.emit('authenticated', data);
        });
        
        this.socket.on('unauthorized', (data) => {
            logger.error("WebSocket unauthorized:", data);
            this.emit('unauthorized', data);
        });
        
        // Video processing events
        this.socket.on('video_uploaded', this.handleVideoUploaded.bind(this));
        this.socket.on('video_processing', this.handleVideoProcessing.bind(this));
        this.socket.on('video_progress', this.handleVideoProgress.bind(this));
        this.socket.on('video_completed', this.handleVideoCompleted.bind(this));
        this.socket.on('video_failed', this.handleVideoFailed.bind(this));
        
        // Tier and credit events
        this.socket.on('tier_upgraded', this.handleTierUpgraded.bind(this));
        this.socket.on('credits_updated', this.handleCreditsUpdated.bind(this));
        
        // Subscription events
        this.socket.on('subscribed', this.handleSubscribed.bind(this));
        this.socket.on('unsubscribed', this.handleUnsubscribed.bind(this));
        
        // Error events
        this.socket.on('error', this.handleError.bind(this));
    }
    
    def authenticate(self, token: str):
        """Authenticate with WebSocket server."""
        if (!this.socket || !this.connected) {
            logger.warning("Cannot authenticate, not connected to WebSocket");
            return;
        }
        
        logger.info("Authenticating WebSocket connection");
        this.socket.emit('authenticate', { token: token });
    }
    
    def subscribeVideo(self, video_id: str):
        """Subscribe to video updates."""
        if (!this.socket || !this.connected) {
            logger.warning("Cannot subscribe, not connected to WebSocket");
            return;
        }
        
        logger.info("Subscribing to video:", video_id);
        this.socket.emit('subscribe_video', { video_id: video_id });
        
        // Track subscription
        this.subscriptions[video_id] = {
            type: 'video',
            timestamp: new Date().toISOString()
        };
    }
    
    def unsubscribeVideo(self, video_id: str):
        """Unsubscribe from video updates."""
        if (!this.socket || !this.connected) {
            logger.warning("Cannot unsubscribe, not connected to WebSocket");
            return;
        }
        
        logger.info("Unsubscribing from video:", video_id);
        this.socket.emit('unsubscribe_video', { video_id: video_id });
        
        // Remove subscription tracking
        delete this.subscriptions[video_id];
    }
    
    def resubscribe(self):
        """Resubscribe to previous subscriptions after reconnection."""
        Object.keys(this.subscriptions).forEach(video_id => {
            if (this.subscriptions[video_id].type === 'video') {
                this.subscribeVideo(video_id);
            }
        });
    }
    
    // Event handlers
    def handleVideoUploaded(self, data):
        """Handle video uploaded event."""
        logger.info("Video uploaded:", data.video_id);
        this.emit('video_uploaded', data);
        
        // Update UI if video element exists
        this.updateVideoStatus(data.video_id, 'uploaded', data);
    }
    
    def handleVideoProcessing(self, data):
        """Handle video processing event."""
        logger.info("Video processing:", data.video_id);
        this.emit('video_processing', data);
        
        // Update UI
        this.updateVideoStatus(data.video_id, 'processing', data);
    }
    
    def handleVideoProgress(self, data):
        """Handle video progress event."""
        logger.debug("Video progress:", data.video_id, data.progress);
        this.emit('video_progress', data);
        
        // Update progress bar
        this.updateVideoProgress(data.video_id, data.progress, data);
    }
    
    def handleVideoCompleted(self, data):
        """Handle video completed event."""
        logger.info("Video completed:", data.video_id);
        this.emit('video_completed', data);
        
        // Update UI
        this.updateVideoStatus(data.video_id, 'completed', data);
        
        // Show success notification
        this.showNotification('Video processed successfully!', 'success');
    }
    
    def handleVideoFailed(self, data):
        """Handle video failed event."""
        logger.error("Video failed:", data.video_id, data.error_message);
        this.emit('video_failed', data);
        
        // Update UI
        this.updateVideoStatus(data.video_id, 'failed', data);
        
        // Show error notification
        this.showNotification(`Video processing failed: ${data.error_message}`, 'error');
    }
    
    def handleTierUpgraded(self, data):
        """Handle tier upgraded event."""
        logger.info("Tier upgraded:", data.from_tier, '→', data.to_tier);
        this.emit('tier_upgraded', data);
        
        // Update UI
        this.updateTierDisplay(data.to_tier, data);
        
        // Show success notification
        this.showNotification(`Upgraded to ${data.to_tier} tier!`, 'success');
    }
    
    def handleCreditsUpdated(self, data):
        """Handle credits updated event."""
        logger.info("Credits updated:", data.credits_remaining);
        this.emit('credits_updated', data);
        
        // Update UI
        this.updateCreditsDisplay(data.credits_remaining, data);
    }
    
    def handleSubscribed(self, data):
        """Handle subscribed event."""
        logger.info("Subscribed to:", data.video_id);
        this.emit('subscribed', data);
    }
    
    def handleUnsubscribed(self, data):
        """Handle unsubscribed event."""
        logger.info("Unsubscribed from:", data.video_id);
        this.emit('unsubscribed', data);
    }
    
    def handleError(self, data):
        """Handle error event."""
        logger.error("WebSocket error:", data);
        this.emit('error', data);
        
        // Show error notification
        if (data.error) {
            this.showNotification(`WebSocket error: ${data.error}`, 'error');
        }
    }
    
    // UI update methods
    def updateVideoStatus(video_id, status, data):
        """Update video status in UI."""
        // Find video element by ID
        const videoElement = document.querySelector(`[data-video-id="${video_id}"]`);
        if (!videoElement) return;
        
        // Update status badge
        const statusBadge = videoElement.querySelector('.video-status');
        if (statusBadge) {
            statusBadge.textContent = status;
            statusBadge.className = `video-status badge status-${status}`;
        }
        
        // Update progress bar
        if (status === 'processing' && data.progress !== undefined) {
            this.updateVideoProgress(video_id, data.progress, data);
        }
        
        // Update last updated time
        const timeElement = videoElement.querySelector('.video-updated');
        if (timeElement) {
            timeElement.textContent = new Date().toLocaleTimeString();
        }
    }
    
    def updateVideoProgress(video_id, progress, data):
        """Update video progress in UI."""
        const videoElement = document.querySelector(`[data-video-id="${video_id}"]`);
        if (!videoElement) return;
        
        // Update progress bar
        const progressBar = videoElement.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);
        }
        
        // Update progress text
        const progressText = videoElement.querySelector('.progress-text');
        if (progressText) {
            progressText.textContent = `${progress}%`;
        }
        
        // Update current step if provided
        if (data.current_step) {
            const stepElement = videoElement.querySelector('.current-step');
            if (stepElement) {
                stepElement.textContent = data.current_step;
            }
        }
        
        // Update estimated time if provided
        if (data.estimated_time_remaining) {
            const timeElement = videoElement.querySelector('.estimated-time');
            if (timeElement) {
                const minutes = Math.floor(data.estimated_time_remaining / 60);
                const seconds = Math.floor(data.estimated_time_remaining % 60);
                timeElement.textContent = `ETA: ${minutes}m ${seconds}s`;
            }
        }
    }
    
    def updateTierDisplay(tier, data):
        """Update tier display in UI."""
        // Update tier badge
        const tierBadge = document.querySelector('.tier-badge');
        if (tierBadge) {
            tierBadge.textContent = tier;
            tierBadge.className = `tier-badge badge tier-${tier}`;
        }
        
        // Update tier name
        const tierName = document.querySelector('.tier-name');
        if (tierName) {
            tierName.textContent = tier.charAt(0).toUpperCase() + tier.slice(1);
        }
        
        // Update features display
        if (data.new_features) {
            const featuresList = document.querySelector('.tier-features');
            if (featuresList) {
                featuresList.innerHTML = data.new_features.map(feature => 
                    `<li><i class="fas fa-check"></i> ${feature}</li>`
                ).join('');
            }
        }
    }
    
    def updateCreditsDisplay(credits, data):
        """Update credits display in UI."""
        // Update credits count
        const creditsElement = document.querySelector('.credits-count');
        if (creditsElement) {
            creditsElement.textContent = credits;
        }
        
        // Update progress bar if available
        const creditsBar = document.querySelector('.credits-progress');
        if (creditsBar && data.credits_total) {
            const percent = (credits / data.credits_total) * 100;
            creditsBar.style.width = `${percent}%`;
        }
    }
    
    def showNotification(message, type = 'info'):
        """Show notification to user."""
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <i class="fas ${this.getNotificationIcon(type)}"></i>
                <span>${message}</span>
            </div>
            <button class="notification-close">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add to notification container
        const container = document.querySelector('.notification-container');
        if (!container) {
            // Create container if it doesn't exist
            const newContainer = document.createElement('div');
            newContainer.className = 'notification-container';
            document.body.appendChild(newContainer);
            container = newContainer;
        }
        
        container.appendChild(notification);
        
        // Add close button event
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => {
            notification.remove();
        });
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
    
    def getNotificationIcon(type):
        """Get icon for notification type."""
        switch (type) {
            case 'success':
                return 'fa-check-circle';
            case 'error':
                return 'fa-exclamation-circle';
            case 'warning':
                return 'fa-exclamation-triangle';
            default:
                return 'fa-info-circle';
        }
    }
    
    // Event emitter methods
    def on(event, handler):
        """Register event handler."""
        if (!this.event_handlers[event]) {
            this.event_handlers[event] = [];
        }
        this.event_handlers[event].push(handler);
    }
    
    def off(event, handler):
        """Remove event handler."""
        if (!this.event_handlers[event]) return;
        
        const index = this.event_handlers[event].indexOf(handler);
        if (index > -1) {
            this.event_handlers[event].splice(index, 1);
        }
    }
    
    def emit(event, data):
        """Emit event to registered handlers."""
        if (!this.event_handlers[event]) return;
        
        this.event_handlers[event].forEach(handler => {
            try {
                handler(data);
            } catch (error) {
                logger.error(`Error in event handler for ${event}:`, error);
            }
        });
    }
    
    // Utility methods
    def scheduleReconnect():
        """Schedule reconnection attempt."""
        if (this.reconnect_attempts >= this.max_reconnect_attempts) {
            logger.error("Max reconnection attempts reached");
            return;
        }
        
        this.reconnect_attempts++;
        const delay = this.reconnect_delay * Math.pow(2, this.reconnect_attempts - 1);
        
        logger.info(`Scheduling reconnection in ${delay}ms`);
        setTimeout(() => {
            this.connect();
        }, Math.min(delay, 30000)); // Max 30 seconds delay
    }
    
    def disconnect():
        """Disconnect from WebSocket server."""
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        this.connected = false;
        this.emit('disconnected', { reason: 'manual' });
    }
    
    def isConnected():
        """Check if connected to WebSocket."""
        return this.connected;
    }
    
    def getSubscriptions():
        """Get current subscriptions."""
        return { ...this.subscriptions };
    }
}

// Create global instance
if (typeof window.VideoAI === 'undefined') {
    window.VideoAI = {};
}

window.VideoAI.RealtimeUpdates = new RealtimeUpdates();

// Auto-connect on page load if user is authenticated
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('access_token');
    if (token) {
        window.VideoAI.RealtimeUpdates.connect(token);
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RealtimeUpdates;
}