/**
 * Tier comparison and upgrade functionality.
 */

class TierComparison {
    constructor() {
        this.tiers = null;
        this.userTier = 'free';
        this.init();
    }

    async init() {
        await this.loadTiers();
        this.renderComparisonTable();
        this.setupEventListeners();
        this.updateUserTier();
    }

    async loadTiers() {
        try {
            const response = await fetch('/api/v1/billing/tiers');
            if (!response.ok) throw new Error('Failed to load tiers');
            
            this.tiers = await response.json();
        } catch (error) {
            console.error('Error loading tiers:', error);
            this.tiers = this.getDefaultTiers();
        }
    }

    getDefaultTiers() {
        return {
            free: {
                name: 'Free',
                price_monthly: 0,
                price_yearly: 0,
                yearly_savings: 0,
                videos_per_month: 3,
                max_video_length: 180,
                max_quality: '720p',
                ai_thumbnails_count: 1,
                extracted_thumbnails_count: 5,
                retention_days: 1,
                priority: 1,
                email_support: false,
                priority_support: false,
                dedicated_support: false
            },
            starter: {
                name: 'Starter',
                price_monthly: 24,
                price_yearly: 230,
                yearly_savings: 20,
                videos_per_month: 50,
                max_video_length: 1800,
                max_quality: '1080p',
                ai_thumbnails_count: 3,
                extracted_thumbnails_count: 8,
                retention_days: 7,
                priority: 2,
                email_support: true,
                priority_support: false,
                dedicated_support: false
            },
            pro: {
                name: 'Pro',
                price_monthly: 79,
                price_yearly: 758,
                yearly_savings: 20,
                videos_per_month: 100,
                max_video_length: 3600,
                max_quality: '4K',
                ai_thumbnails_count: 5,
                extracted_thumbnails_count: 15,
                retention_days: 30,
                priority: 3,
                email_support: true,
                priority_support: true,
                dedicated_support: false
            },
            plus: {
                name: 'Plus',
                price_monthly: 250,
                price_yearly: 2400,
                yearly_savings: 20,
                videos_per_month: 500,
                max_video_length: 7200,
                max_quality: '4K+HDR',
                ai_thumbnails_count: 10,
                extracted_thumbnails_count: 25,
                retention_days: 90,
                priority: 4,
                email_support: true,
                priority_support: true,
                dedicated_support: true
            }
        };
    }

    renderComparisonTable() {
        const container = document.getElementById('tier-comparison');
        if (!container) return;

        const tiers = ['free', 'starter', 'pro', 'plus'];
        
        let html = `
            <div class="table-responsive">
                <table class="table table-hover tier-comparison-table">
                    <thead>
                        <tr>
                            <th scope="col">Feature</th>
                            ${tiers.map(tier => `
                                <th scope="col" class="text-center tier-header ${tier}">
                                    <div class="tier-name">${this.tiers[tier].name}</div>
                                    <div class="tier-price">
                                        $${this.tiers[tier].price_monthly}<small>/month</small>
                                    </div>
                                    ${this.tiers[tier].price_yearly > 0 ? `
                                        <div class="tier-yearly">
                                            $${this.tiers[tier].price_yearly}/year
                                            <span class="badge bg-success">Save ${this.tiers[tier].yearly_savings}%</span>
                                        </div>
                                    ` : ''}
                                    <button class="btn btn-sm ${this.getUpgradeButtonClass(tier)} mt-2"
                                            onclick="tierComparison.upgradeTo('${tier}')"
                                            ${this.isCurrentTier(tier) ? 'disabled' : ''}>
                                        ${this.getUpgradeButtonText(tier)}
                                    </button>
                                </th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${this.renderFeaturesTable()}
                    </tbody>
                </table>
            </div>
        `;

        container.innerHTML = html;
        this.highlightCurrentTier();
    }

    renderFeaturesTable() {
        const tiers = ['free', 'starter', 'pro', 'plus'];
        
        const features = [
            {
                name: 'Videos per month',
                key: 'videos_per_month',
                format: (value) => value === 500 ? '500+' : value === 10000 ? 'Unlimited' : value
            },
            {
                name: 'Max video length',
                key: 'max_video_length',
                format: (value) => {
                    const minutes = Math.floor(value / 60);
                    if (minutes < 60) return `${minutes} min`;
                    const hours = (minutes / 60).toFixed(1);
                    return `${hours} hour${hours > 1 ? 's' : ''}`;
                }
            },
            {
                name: 'Max quality',
                key: 'max_quality',
                format: (value) => value
            },
            {
                name: 'AI thumbnails',
                key: 'ai_thumbnails_count',
                format: (value) => value
            },
            {
                name: 'Extracted thumbnails',
                key: 'extracted_thumbnails_count',
                format: (value) => value
            },
            {
                name: 'Video retention',
                key: 'retention_days',
                format: (value) => {
                    if (value === 1) return '24 hours';
                    if (value === 7) return '7 days';
                    if (value === 30) return '30 days';
                    if (value === 90) return '90 days';
                    return `${value} days`;
                }
            },
            {
                name: 'Processing priority',
                key: 'priority',
                format: (value) => {
                    const priorities = {
                        1: 'Normal',
                        2: 'Priority',
                        3: 'Express',
                        4: 'VIP'
                    };
                    return priorities[value] || 'Normal';
                }
            },
            {
                name: 'Email support',
                key: 'email_support',
                format: (value) => value ? '✓' : '✗'
            },
            {
                name: 'Priority support',
                key: 'priority_support',
                format: (value) => value ? '✓' : '✗'
            },
            {
                name: 'Dedicated support',
                key: 'dedicated_support',
                format: (value) => value ? '✓' : '✗'
            }
        ];

        return features.map(feature => `
            <tr>
                <td class="feature-name">${feature.name}</td>
                ${tiers.map(tier => `
                    <td class="text-center ${this.isCurrentTier(tier) ? 'current-tier' : ''}">
                        ${feature.format(this.tiers[tier][feature.key])}
                    </td>
                `).join('')}
            </tr>
        `).join('');
    }

    getUpgradeButtonClass(tier) {
        if (this.isCurrentTier(tier)) {
            return 'btn-outline-secondary';
        }
        
        const tierOrder = { free: 0, starter: 1, pro: 2, plus: 3, enterprise: 4 };
        const currentOrder = tierOrder[this.userTier];
        const targetOrder = tierOrder[tier];
        
        if (targetOrder > currentOrder) {
            return 'btn-success';
        } else if (targetOrder < currentOrder) {
            return 'btn-outline-secondary';
        } else {
            return 'btn-primary';
        }
    }

    getUpgradeButtonText(tier) {
        if (this.isCurrentTier(tier)) {
            return 'Current Plan';
        }
        
        const tierOrder = { free: 0, starter: 1, pro: 2, plus: 3, enterprise: 4 };
        const currentOrder = tierOrder[this.userTier];
        const targetOrder = tierOrder[tier];
        
        if (targetOrder > currentOrder) {
            return 'Upgrade';
        } else if (targetOrder < currentOrder) {
            return 'Downgrade';
        } else {
            return 'Select';
        }
    }

    isCurrentTier(tier) {
        return tier === this.userTier;
    }

    highlightCurrentTier() {
        const cells = document.querySelectorAll(`.tier-header.${this.userTier}`);
        cells.forEach(cell => {
            cell.classList.add('current-tier-highlight');
        });
    }

    async updateUserTier() {
        try {
            const response = await fetch('/api/v1/users/me');
            if (!response.ok) throw new Error('Failed to load user info');
            
            const user = await response.json();
            this.userTier = user.tier;
            
            this.renderComparisonTable();
        } catch (error) {
            console.error('Error loading user tier:', error);
        }
    }

    async upgradeTo(tier) {
        if (this.isCurrentTier(tier)) {
            return;
        }

        if (!confirm(`Are you sure you want to upgrade to ${this.tiers[tier].name} tier?`)) {
            return;
        }

        try {
            const response = await fetch('/api/v1/billing/upgrade', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({ tier: tier })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Upgrade failed');
            }

            const result = await response.json();
            
            if (result.checkout_url) {
                // Redirect to Stripe checkout
                window.location.href = result.checkout_url;
            } else {
                // Direct upgrade (free tier or admin)
                alert('Tier upgraded successfully!');
                this.userTier = tier;
                this.renderComparisonTable();
            }
        } catch (error) {
            console.error('Upgrade error:', error);
            alert(`Upgrade failed: ${error.message}`);
        }
    }

    getAuthToken() {
        // Get token from localStorage or cookie
        return localStorage.getItem('auth_token') || 
               document.cookie.split('; ').find(row => row.startsWith('auth_token='))?.split('=')[1];
    }

    setupEventListeners() {
        // Handle yearly/monthly toggle
        const billingToggle = document.getElementById('billing-toggle');
        if (billingToggle) {
            billingToggle.addEventListener('change', (e) => {
                this.renderComparisonTable();
            });
        }

        // Handle upgrade buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('upgrade-btn')) {
                const tier = e.target.dataset.tier;
                this.upgradeTo(tier);
            }
        });

        // Handle plan selection in checkout
        document.addEventListener('change', (e) => {
            if (e.target.name === 'plan') {
                this.updateCheckoutSummary(e.target.value);
            }
        });
    }

    updateCheckoutSummary(selectedTier) {
        const summaryElement = document.getElementById('checkout-summary');
        if (!summaryElement || !this.tiers[selectedTier]) return;

        const tier = this.tiers[selectedTier];
        const isYearly = document.getElementById('billing-yearly')?.checked || false;
        const price = isYearly ? tier.price_yearly : tier.price_monthly * (isYearly ? 12 : 1);
        const interval = isYearly ? 'year' : 'month';

        const summary = `
            <div class="checkout-summary">
                <h5>Order Summary</h5>
                <div class="summary-item">
                    <span>${tier.name} Plan</span>
                    <span>$${price}/${interval}</span>
                </div>
                <div class="summary-item">
                    <span>Videos per month</span>
                    <span>${tier.videos_per_month === 500 ? '500+' : tier.videos_per_month}</span>
                </div>
                <div class="summary-item">
                    <span>Max video length</span>
                    <span>${Math.floor(tier.max_video_length / 60)} minutes</span>
                </div>
                <div class="summary-item">
                    <span>Max quality</span>
                    <span>${tier.max_quality}</span>
                </div>
                <hr>
                <div class="summary-item total">
                    <strong>Total</strong>
                    <strong>$${price}/${interval}</strong>
                </div>
                ${isYearly ? `
                    <div class="text-success small">
                        <i class="fas fa-check-circle"></i> Save ${tier.yearly_savings}% with yearly billing
                    </div>
                ` : ''}
            </div>
        `;

        summaryElement.innerHTML = summary;
    }
}

// Initialize tier comparison
const tierComparison = new TierComparison();

// Export for global access
window.tierComparison = tierComparison;