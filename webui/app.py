"""
SpawnPoint - Application Launcher
Handles application startup, shutdown, and signal handling.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from nicegui import ui

# Add templates folder to path for spawnpoint module
sys.path.insert(0, str(Path(__file__).parent / "static" / "templates"))

from spawnpoint import initialize, logger

# ---------------------------------------------------------------------------
# Shutdown Handling
# ---------------------------------------------------------------------------

_shutdown_event = asyncio.Event()
_is_shutting_down = False


def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals gracefully."""
    global _is_shutting_down
    
    if _is_shutting_down:
        logger.warning("Forced shutdown requested")
        sys.exit(1)
    
    _is_shutting_down = True
    sig_name = signal.Signals(signum).name
    logger.info("Received %s, initiating graceful shutdown...", sig_name)
    
    # Set shutdown event
    try:
        _shutdown_event.set()
    except Exception:
        pass
    
    # Allow NiceGUI to handle shutdown
    logger.info("SpawnPoint shutting down gracefully")


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    # Handle common shutdown signals
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    
    # Windows-specific
    if sys.platform == 'win32':
        try:
            signal.signal(signal.SIGBREAK, handle_shutdown_signal)
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    """Main entry point for SpawnPoint."""
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Initialize SpawnPoint
    logger.info("=" * 60)
    logger.info("SpawnPoint Game Server Manager")
    logger.info("=" * 60)
    
    initialize()
    
    logger.info("Starting web interface on port 40400...")
    
    # Run NiceGUI
    ui.run(
        title='SpawnPoint',
        host='0.0.0.0',
        port=40400,
        favicon='🎮',
        dark=True,
        reload=False,
        show=False
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
