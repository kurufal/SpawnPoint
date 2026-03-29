"""
SpawnPoint - Application Launcher
Handles application startup, shutdown, and signal handling.
"""

import asyncio
import logging
import socket
import sys
from pathlib import Path

from nicegui import ui

# Add templates folder to path for spawnpoint module
sys.path.insert(0, str(Path(__file__).parent / "static" / "templates"))

from spawnpoint import initialize, logger


# ---------------------------------------------------------------------------
# Port Check
# ---------------------------------------------------------------------------

def stop_existing_instance(port: int = 40400):
    """Stop an already-running instance listening on the given port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        if result == 0:
            logger.info("Port %d is in use — stopping existing instance...", port)
            sock.close()
            # Find and kill the process occupying the port
            import subprocess
            if sys.platform == 'win32':
                out = subprocess.check_output(
                    ['netstat', '-ano', '-p', 'TCP'], text=True
                )
                for line in out.splitlines():
                    if f':{port}' in line and 'LISTENING' in line:
                        pid = int(line.strip().split()[-1])
                        logger.info("Killing PID %d on port %d", pid, port)
                        subprocess.call(['taskkill', '/F', '/PID', str(pid)])
                        break
            else:
                out = subprocess.check_output(
                    ['lsof', '-ti', f'tcp:{port}'], text=True
                )
                for pid in out.strip().splitlines():
                    logger.info("Killing PID %s on port %d", pid, port)
                    subprocess.call(['kill', '-9', pid])
            # Brief pause to let the OS release the port
            import time
            time.sleep(1)
        else:
            sock.close()
    except Exception as exc:
        logger.debug("Port check encountered an error: %s", exc)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    """Main entry point for SpawnPoint."""
    
    # Stop any already-running instance
    stop_existing_instance(40400)
    
    # Initialize SpawnPoint
    logger.info("=" * 60)
    logger.info("SpawnPoint Game Server Manager")
    logger.info("=" * 60)
    
    initialize()
    
    logger.info("Starting web interface on port 40400...")
    
    # Run NiceGUI
    try:
        ui.run(
            title='SpawnPoint',
            host='0.0.0.0',
            port=40400,
            favicon='🎮',
            dark=True,
            reload=False,
            show=False
        )
    except KeyboardInterrupt:
        logger.info("SpawnPoint shut down.")


if __name__ in {"__main__", "__mp_main__"}:
    main()
