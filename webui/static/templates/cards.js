/**
 * SpawnPoint - Game cards functionality
 * Handles card grid, animations, and interactions
 */

(function() {
    'use strict';

    /**
     * Apply dynamic background images for cards
     */
    function applyCardBackgrounds() {
        // Apply noise background to body
        const noiseStyle = document.createElement('style');
        noiseStyle.textContent = `
            body::before {
                background-image: url("/static/noise.gif");
            }
        `;
        document.head.appendChild(noiseStyle);
        
        // Apply line borders to cards
        const borderStyle = document.createElement('style');
        borderStyle.textContent = `
            .card-border-top,
            .card-border-bottom {
                background-image: url("/static/line-BG.png");
            }
        `;
        document.head.appendChild(borderStyle);
        
        console.log('[SpawnPoint] Card backgrounds applied');
    }

    /**
     * Add hover effects to cards
     */
    function initCardHoverEffects() {
        document.addEventListener('mouseenter', (e) => {
            const card = e.target.closest('.game-card');
            if (card && !card.classList.contains('add-card')) {
                card.style.transform = 'translateY(-2px)';
                card.style.boxShadow = '0 8px 25px rgba(168, 85, 247, 0.3)';
            }
        }, true);
        
        document.addEventListener('mouseleave', (e) => {
            const card = e.target.closest('.game-card');
            if (card && !card.classList.contains('add-card')) {
                card.style.transform = '';
                card.style.boxShadow = '';
            }
        }, true);
        
        console.log('[SpawnPoint] Card hover effects initialized');
    }

    /**
     * Handle card status indicator animations
     */
    function initStatusAnimations() {
        // Add pulsing animation for running servers
        const pulseStyle = document.createElement('style');
        pulseStyle.textContent = `
            @keyframes statusPulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }
            
            .game-card[data-status="running"] .card-status-info {
                animation: statusPulse 2s ease-in-out infinite;
                color: #10b981;
            }
            
            .game-card[data-status="stopped"] .card-status-info {
                color: #ef4444;
            }
            
            .game-card[data-status="installing"] .card-status-info {
                animation: statusPulse 1s ease-in-out infinite;
                color: #f59e0b;
            }
        `;
        document.head.appendChild(pulseStyle);
        
        console.log('[SpawnPoint] Status animations initialized');
    }

    /**
     * Refresh card images (cache-bust)
     */
    window.refreshCardImage = function(appId) {
        const img = document.querySelector(`img[data-server="${appId}"]`);
        if (img) {
            const baseUrl = img.src.split('?')[0];
            img.src = `${baseUrl}?t=${Date.now()}`;
        }
    };

    /**
     * Update card status display
     */
    window.updateCardStatus = function(appId, status) {
        const card = document.querySelector(`.game-card[data-app-id="${appId}"]`);
        if (card) {
            card.setAttribute('data-status', status);
            const statusInfo = card.querySelector('.card-status-info');
            if (statusInfo) {
                statusInfo.textContent = `Status: ${status}`;
            }
        }
    };

    /**
     * API helper for server control
     */
    window.controlServer = async function(appId, action) {
        try {
            const response = await fetch(`/api/servers/${appId}/${action}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const result = await response.json();
            
            if (!response.ok) {
                console.error(`Failed to ${action}:`, result.error);
                return false;
            }
            
            // Update card UI
            window.updateCardStatus(appId, result.status);
            return true;
        } catch (error) {
            console.error(`Failed to ${action} server:`, error);
            return false;
        }
    };

    /**
     * Fetch and refresh server list
     */
    window.refreshServers = async function() {
        try {
            const response = await fetch('/api/servers');
            const servers = await response.json();
            
            // Update each card's status
            for (const server of servers) {
                window.updateCardStatus(server.appId, server.status);
            }
            
            return servers;
        } catch (error) {
            console.error('Failed to refresh servers:', error);
            return [];
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            applyCardBackgrounds();
            initCardHoverEffects();
            initStatusAnimations();
        });
    } else {
        applyCardBackgrounds();
        initCardHoverEffects();
        initStatusAnimations();
    }

    // Periodic server status refresh (every 10 seconds)
    setInterval(() => {
        window.refreshServers();
    }, 10000);

})();
