/**
 * SpawnPoint - Modal dialogs functionality
 * Handles add server and edit server modals
 */

(function() {
    'use strict';

    /**
     * Close modal when clicking outside
     */
    function initModalBackdropClose() {
        document.addEventListener('click', (e) => {
            // NiceGUI dialogs have specific structure, handle backdrop clicks
            if (e.target.classList.contains('q-dialog__backdrop')) {
                // Find the dialog and close it
                const dialog = e.target.closest('.q-dialog');
                if (dialog) {
                    // Trigger ESC key to close
                    const escEvent = new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape' });
                    document.dispatchEvent(escEvent);
                }
            }
        });
        
        console.log('[SpawnPoint] Modal backdrop close initialized');
    }

    /**
     * Handle keyboard shortcuts for modals
     */
    function initModalKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // ESC to close modals is handled by NiceGUI
            
            // Enter to submit active form
            if (e.key === 'Enter' && !e.shiftKey) {
                const activeElement = document.activeElement;
                if (activeElement && activeElement.tagName === 'INPUT') {
                    // Find submit button in same form/dialog
                    const dialog = activeElement.closest('.q-card');
                    if (dialog) {
                        const submitBtn = dialog.querySelector('.btn-primary');
                        if (submitBtn) {
                            e.preventDefault();
                            submitBtn.click();
                        }
                    }
                }
            }
        });
        
        console.log('[SpawnPoint] Modal keyboard shortcuts initialized');
    }

    /**
     * Focus first input when modal opens
     */
    function initModalAutoFocus() {
        // Use MutationObserver to detect when dialogs appear
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        // Check if it's a dialog
                        const dialog = node.classList?.contains('q-dialog') ? node : node.querySelector?.('.q-dialog');
                        if (dialog) {
                            // Focus first input after a short delay
                            setTimeout(() => {
                                const firstInput = dialog.querySelector('input:not([readonly])');
                                if (firstInput) {
                                    firstInput.focus();
                                }
                            }, 100);
                        }
                    }
                }
            }
        });
        
        observer.observe(document.body, { childList: true, subtree: true });
        console.log('[SpawnPoint] Modal auto-focus initialized');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initModalBackdropClose();
            initModalKeyboardShortcuts();
            initModalAutoFocus();
        });
    } else {
        initModalBackdropClose();
        initModalKeyboardShortcuts();
        initModalAutoFocus();
    }

})();
