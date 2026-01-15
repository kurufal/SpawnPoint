/**
 * SpawnPoint - Terminal functionality
 * Handles terminal panel toggle, resize, and log display
 */

(function() {
    'use strict';

    const MIN_TERMINAL_WIDTH = 240;
    const MAX_TERMINAL_WIDTH = 800;
    const RESIZE_HANDLE_WIDTH = 18;
    let lastExpandedWidth = 400;

    /**
     * Initialize terminal resize functionality
     */
    function initTerminalResize() {
        const resizer = document.getElementById('terminal-resizer');
        const terminalColumn = document.getElementById('terminal-column');
        
        if (!resizer || !terminalColumn) {
            // Retry after a short delay (NiceGUI may still be rendering)
            setTimeout(initTerminalResize, 100);
            return;
        }
        
        let isResizing = false;
        let startX = 0;
        let startWidth = 0;
        
        const onPointerMove = (event) => {
            if (!isResizing) return;
            
            const clientX = event.touches ? event.touches[0].clientX : event.clientX;
            const delta = startX - clientX;
            let nextWidth = startWidth + delta;
            nextWidth = Math.max(MIN_TERMINAL_WIDTH, Math.min(MAX_TERMINAL_WIDTH, nextWidth));
            
            terminalColumn.style.width = `${nextWidth}px`;
            lastExpandedWidth = nextWidth;
        };
        
        const stopResize = () => {
            if (!isResizing) return;
            
            isResizing = false;
            document.removeEventListener('mousemove', onPointerMove);
            document.removeEventListener('mouseup', stopResize);
            document.removeEventListener('touchmove', onPointerMove);
            document.removeEventListener('touchend', stopResize);
            
            resizer.classList.remove('is-active');
            document.body.style.userSelect = '';
            document.body.style.cursor = '';
            resizer.style.cursor = 'col-resize';
        };
        
        const startResize = (event) => {
            if (terminalColumn.classList.contains('collapsed')) return;
            if (resizer.getAttribute('data-collapsed') === 'true') return;
            
            const clientX = event.touches ? event.touches[0].clientX : event.clientX;
            const rect = terminalColumn.getBoundingClientRect();
            const withinHandle = clientX >= rect.left - RESIZE_HANDLE_WIDTH && 
                                 clientX <= rect.left + RESIZE_HANDLE_WIDTH;
            
            if (!withinHandle) return;
            
            isResizing = true;
            startX = clientX;
            startWidth = terminalColumn.getBoundingClientRect().width;
            resizer.classList.add('is-active');
            
            document.addEventListener('mousemove', onPointerMove);
            document.addEventListener('mouseup', stopResize);
            document.addEventListener('touchmove', onPointerMove);
            document.addEventListener('touchend', stopResize);
            
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
            event.preventDefault();
        };
        
        resizer.addEventListener('mousedown', startResize);
        resizer.addEventListener('touchstart', startResize, { passive: false });
        
        console.log('[SpawnPoint] Terminal resize initialized');
    }

    /**
     * Toggle terminal collapsed state
     */
    window.toggleTerminal = function() {
        const terminalColumn = document.getElementById('terminal-column');
        const toggleIcon = document.getElementById('toggle-icon');
        const resizer = document.getElementById('terminal-resizer');
        
        if (!terminalColumn) return;
        
        const currentlyCollapsed = terminalColumn.classList.contains('collapsed');
        
        if (!currentlyCollapsed) {
            lastExpandedWidth = terminalColumn.getBoundingClientRect().width;
        }
        
        terminalColumn.classList.toggle('collapsed');
        const isCollapsed = terminalColumn.classList.contains('collapsed');
        
        if (isCollapsed) {
            if (toggleIcon) toggleIcon.textContent = '<';
            terminalColumn.style.width = '';
            if (resizer) {
                resizer.setAttribute('data-collapsed', 'true');
                resizer.style.cursor = 'default';
            }
        } else {
            const widthToRestore = Math.max(MIN_TERMINAL_WIDTH, Math.min(MAX_TERMINAL_WIDTH, lastExpandedWidth));
            terminalColumn.style.width = `${widthToRestore}px`;
            if (toggleIcon) toggleIcon.textContent = '>';
            if (resizer) {
                resizer.removeAttribute('data-collapsed');
                resizer.style.cursor = 'col-resize';
            }
        }
    };

    /**
     * Auto-scroll terminal to bottom
     */
    window.scrollTerminalToBottom = function() {
        const terminalOutput = document.getElementById('terminal-output');
        if (terminalOutput) {
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTerminalResize);
    } else {
        initTerminalResize();
    }

    // Set up mutation observer to auto-scroll terminal
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === 'childList' && mutation.target.id === 'terminal-output') {
                window.scrollTerminalToBottom();
            }
        }
    });

    // Start observing once terminal exists
    function observeTerminal() {
        const terminal = document.getElementById('terminal-output');
        if (terminal) {
            observer.observe(terminal, { childList: true, subtree: true });
            console.log('[SpawnPoint] Terminal observer started');
        } else {
            setTimeout(observeTerminal, 100);
        }
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', observeTerminal);
    } else {
        observeTerminal();
    }

})();
