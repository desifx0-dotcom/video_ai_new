/**
 * Theme toggle functionality for dark/light mode.
 */
class ThemeToggle {
    constructor() {
        this.theme = localStorage.getItem('theme') || 'light';
        this.init();
    }
    
    init() {
        // Apply saved theme
        this.applyTheme(this.theme);
        
        // Set up toggle button
        this.setupToggleButton();
        
        // Watch for system theme changes
        this.watchSystemTheme();
    }
    
    setupToggleButton() {
        const toggleBtn = document.getElementById('theme-toggle');
        const toggleIcon = document.getElementById('theme-toggle-icon');
        
        if (!toggleBtn) return;
        
        // Update button icon based on current theme
        this.updateToggleIcon(toggleIcon);
        
        // Add click event
        toggleBtn.addEventListener('click', () => {
            this.toggleTheme();
            this.updateToggleIcon(toggleIcon);
        });
        
        // Add keyboard support
        toggleBtn.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.toggleTheme();
                this.updateToggleIcon(toggleIcon);
            }
        });
    }
    
    toggleTheme() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        this.applyTheme(this.theme);
        localStorage.setItem('theme', this.theme);
        
        // Dispatch custom event for other components
        document.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { theme: this.theme }
        }));
        
        // Send to server if user is logged in
        this.syncWithServer();
    }
    
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        document.body.className = theme + '-mode';
        
        // Update meta theme-color
        this.updateMetaThemeColor(theme);
        
        // Update CSS variables
        this.updateCSSVariables(theme);
    }
    
    updateToggleIcon(iconElement) {
        if (!iconElement) return;
        
        if (this.theme === 'dark') {
            // Show sun icon for dark mode (click to switch to light)
            iconElement.className = 'fas fa-sun';
            iconElement.title = 'Switch to light mode';
        } else {
            // Show moon icon for light mode (click to switch to dark)
            iconElement.className = 'fas fa-moon';
            iconElement.title = 'Switch to dark mode';
        }
    }
    
    updateMetaThemeColor(theme) {
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');
        
        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }
        
        // Set theme color based on theme
        if (theme === 'dark') {
            metaThemeColor.content = '#1a1a1a';
        } else {
            metaThemeColor.content = '#ffffff';
        }
    }
    
    updateCSSVariables(theme) {
        const root = document.documentElement;
        
        if (theme === 'dark') {
            // Dark mode variables
            root.style.setProperty('--bg-primary', '#1a1a1a');
            root.style.setProperty('--bg-secondary', '#2d2d2d');
            root.style.setProperty('--bg-tertiary', '#3d3d3d');
            root.style.setProperty('--text-primary', '#ffffff');
            root.style.setProperty('--text-secondary', '#b0b0b0');
            root.style.setProperty('--text-tertiary', '#808080');
            root.style.setProperty('--border-color', '#404040');
            root.style.setProperty('--shadow-color', 'rgba(0, 0, 0, 0.3)');
            root.style.setProperty('--card-bg', '#2d2d2d');
            root.style.setProperty('--input-bg', '#3d3d3d');
            root.style.setProperty('--hover-bg', '#404040');
        } else {
            // Light mode variables
            root.style.setProperty('--bg-primary', '#ffffff');
            root.style.setProperty('--bg-secondary', '#f8f9fa');
            root.style.setProperty('--bg-tertiary', '#e9ecef');
            root.style.setProperty('--text-primary', '#212529');
            root.style.setProperty('--text-secondary', '#6c757d');
            root.style.setProperty('--text-tertiary', '#adb5bd');
            root.style.setProperty('--border-color', '#dee2e6');
            root.style.setProperty('--shadow-color', 'rgba(0, 0, 0, 0.1)');
            root.style.setProperty('--card-bg', '#ffffff');
            root.style.setProperty('--input-bg', '#ffffff');
            root.style.setProperty('--hover-bg', '#f8f9fa');
        }
    }
    
    watchSystemTheme() {
        // Check if user prefers dark mode
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
        
        // Update theme if system preference changes and no user preference is set
        const userTheme = localStorage.getItem('theme');
        if (!userTheme) {
            this.systemThemeChange(prefersDark);
        }
        
        // Listen for system theme changes
        prefersDark.addEventListener('change', (e) => {
            if (!localStorage.getItem('theme')) {
                this.systemThemeChange(e);
            }
        });
    }
    
    systemThemeChange(mediaQuery) {
        const newTheme = mediaQuery.matches ? 'dark' : 'light';
        if (this.theme !== newTheme) {
            this.theme = newTheme;
            this.applyTheme(newTheme);
        }
    }
    
    async syncWithServer() {
        // Only sync if user is authenticated
        const token = localStorage.getItem('access_token');
        if (!token) return;
        
        try {
            const response = await fetch('/api/v1/users/me/settings', {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    theme: this.theme
                })
            });
            
            if (!response.ok) {
                console.warn('Failed to sync theme with server');
            }
        } catch (error) {
            console.warn('Error syncing theme:', error);
        }
    }
    
    // Public method to get current theme
    getCurrentTheme() {
        return this.theme;
    }
    
    // Public method to set theme programmatically
    setTheme(theme) {
        if (theme !== 'light' && theme !== 'dark') {
            console.error('Invalid theme. Use "light" or "dark"');
            return;
        }
        
        this.theme = theme;
        this.applyTheme(theme);
        localStorage.setItem('theme', theme);
        this.updateToggleIcon(document.getElementById('theme-toggle-icon'));
    }
}

// Initialize theme toggle when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.themeToggle = new ThemeToggle();
    
    // Make it available globally
    if (typeof window.VideoAI === 'undefined') {
        window.VideoAI = {};
    }
    window.VideoAI.ThemeToggle = ThemeToggle;
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeToggle;
}