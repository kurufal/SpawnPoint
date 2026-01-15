"""
SpawnPoint - Game Server Manager
Core logic and UI components for managing game servers via SteamCMD.
"""

import asyncio
import asyncio.subprocess as asp
import json
import logging
import re
import shutil
import signal
import time
from collections import deque
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from nicegui import app, ui, Client

# ---------------------------------------------------------------------------
# Logging / In-Memory Log Buffer
# ---------------------------------------------------------------------------

class InMemoryLogHandler(logging.Handler):
    """Capture logs in memory so the web terminal can display them."""
    def __init__(self, max_lines: int = 2000):
        super().__init__()
        self.buffer: deque = deque(maxlen=max_lines)
        self._subscribers: List[Callable] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self.buffer.append(msg)
        for callback in self._subscribers:
            try:
                callback(msg)
            except Exception:
                pass

    def get_logs(self) -> str:
        return "\n".join(self.buffer)

    def subscribe(self, callback: Callable):
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        if callback in self._subscribers:
            self._subscribers.remove(callback)


# Create shared log handler
log_handler = InMemoryLogHandler(max_lines=2000)
log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)-5s %(name)s: %(message)s", 
    "%Y-%m-%d %H:%M:%S"
)
log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.INFO)

# Attach to relevant loggers
for logger_name in ("", "spawnpoint", "spawnpoint.steamcmd", "uvicorn", "nicegui"):
    _logger = logging.getLogger(logger_name)
    if all(h is not log_handler for h in _logger.handlers):
        _logger.addHandler(log_handler)
    _logger.setLevel(logging.INFO)

logger = logging.getLogger("spawnpoint")

# ---------------------------------------------------------------------------
# Path Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # webui/static/templates -> webui
PROJECT_DIR = BASE_DIR.parent  # webui -> project root
SERVERS_FILE = PROJECT_DIR / "SteamCMD" / "servers.json"
GAMES_DIR = PROJECT_DIR / "games"
STATIC_DIR = BASE_DIR / "static"

# Ensure directories exist
SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
GAMES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Server Data Management
# ---------------------------------------------------------------------------

_install_lock = asyncio.Lock()


def read_servers_file() -> List[Dict[str, Any]]:
    """Read servers from JSON file with error recovery."""
    try:
        if not SERVERS_FILE.exists():
            return []
        if SERVERS_FILE.stat().st_size == 0:
            logger.info("Servers file empty, initializing: %s", SERVERS_FILE)
            SERVERS_FILE.write_text("[]", encoding="utf-8")
            return []
        with SERVERS_FILE.open("r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                backup = SERVERS_FILE.with_name(f"{SERVERS_FILE.name}.corrupt.{int(time.time())}")
                shutil.copy2(SERVERS_FILE, backup)
                logger.warning("Corrupt servers.json backed up to %s", backup)
                SERVERS_FILE.write_text("[]", encoding="utf-8")
                return []
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.exception("Failed to read servers file: %s", e)
        return []


def write_servers_file(servers: List[Dict[str, Any]]) -> None:
    """Write servers to JSON file."""
    try:
        with SERVERS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(servers, fh, indent=2)
    except Exception:
        logger.exception("Failed to write servers file")


def find_server(servers: List[Dict[str, Any]], app_id: str) -> Optional[Dict[str, Any]]:
    """Find server by app ID."""
    for s in servers:
        if str(s.get("appId")) == str(app_id):
            return s
    return None


def get_servers_list() -> List[Dict[str, Any]]:
    """Get servers list, with test data if empty."""
    servers = read_servers_file()
    if not servers:
        return [{
            "appId": "111111",
            "name": "Test Game",
            "status": "stopped",
            "port": 40444,
            "installPath": str(GAMES_DIR / "app_111111"),
            "settingsFile": None,
            "version": "1.0.0",
            "updateAvailable": False,
            "ip": "127.0.0.1",
            "image": None
        }]
    return servers


# ---------------------------------------------------------------------------
# SteamCMD Installation
# ---------------------------------------------------------------------------

async def run_steamcmd_install(app_id: str, install_dir: Path) -> None:
    """Run steamcmd to install/update a game server."""
    steamcmd_logger = logging.getLogger("spawnpoint.steamcmd")
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "steamcmd",
            "+login", "anonymous",
            "+force_install_dir", str(install_dir),
            "+app_update", str(app_id), "validate",
            "+quit"
        ]
        steamcmd_logger.info("Starting steamcmd: %s", " ".join(cmd))
        try:
            proc = await asp.create_subprocess_exec(
                *cmd, stdout=asp.PIPE, stderr=asp.STDOUT
            )
        except FileNotFoundError:
            steamcmd_logger.error("steamcmd not found in PATH")
            return
        if proc.stdout:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="ignore").rstrip()
                steamcmd_logger.info("[steamcmd %s] %s", app_id, text)
        rc = await proc.wait()
        if rc == 0:
            steamcmd_logger.info("steamcmd finished successfully for app %s", app_id)
            servers = read_servers_file()
            existing = find_server(servers, app_id)
            if not existing:
                entry = {
                    "appId": str(app_id),
                    "name": f"App {app_id}",
                    "status": "stopped",
                    "port": None,
                    "installPath": str(install_dir),
                    "settingsFile": None,
                    "version": None,
                    "updateAvailable": False,
                    "ip": "",
                    "image": None
                }
                servers.append(entry)
            else:
                existing["installPath"] = str(install_dir)
            write_servers_file(servers)
        else:
            steamcmd_logger.error("steamcmd exited with code %s for app %s", rc, app_id)
    except Exception as ex:
        steamcmd_logger.exception("Error installing app %s: %s", app_id, ex)
    finally:
        try:
            _install_lock.release()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Style Constants
# ---------------------------------------------------------------------------

# Card style - fixed 200x255px like original, overflow visible for borders
CARD_STYLE = '''
    position: relative; 
    width: 200px;
    height: 255px;
    border-radius: 0; 
    overflow: visible; 
    background: #030712;
    border: 1px solid #374151;
    flex-shrink: 0;
'''

# Top/bottom glow borders - outside the card like original, blurred
BORDER_TOP = '''
    position: absolute; top: -4px; left: 0; right: 0; height: 8px; 
    background: linear-gradient(90deg, #ec4899, #a855f7, #3b82f6); 
    background-size: cover;
    filter: blur(3px);
    z-index: -1;
    border-radius: 0;
'''

BORDER_BOTTOM = '''
    position: absolute; bottom: -4px; left: 0; right: 0; height: 8px; 
    background: linear-gradient(90deg, #3b82f6, #a855f7, #ec4899); 
    background-size: cover;
    filter: blur(3px);
    z-index: -1;
    border-radius: 0;
'''

# Button styles
BTN_STYLE = '''
    background: rgba(0,0,0,0.7) !important; 
    color: #fff !important; 
    border-radius: 5px; 
    text-transform: none; 
    font-size: 11px; 
    padding: 0.5rem; 
    box-shadow: none !important;
    white-space: nowrap;
'''

MODAL_BTN = '''
    background: rgba(0,0,0,0.7) !important; 
    color: #fff !important; 
    border-radius: 0; 
    text-transform: none; 
    font-size: 12px; 
    padding: 0.5rem 1rem; 
    box-shadow: none !important;
'''

CLOSE_BTN = '''
    background: transparent !important; 
    color: #00ffff !important; 
    font-size: 1.5rem; 
    padding: 0; 
    min-height: auto !important; 
    box-shadow: none !important;
'''

# Text with background
TEXT_BG = '''
    font-size: 11px; 
    color: #fff; 
    background: rgba(0,0,0,0.7); 
    padding: 0.5rem; 
    border-radius: 5px; 
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
'''


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

def setup_static_files():
    """Setup static file serving."""
    app.add_static_files('/static', str(STATIC_DIR))


def create_main_page():
    """Create the main dashboard page."""
    
    @ui.page('/')
    async def index(client: Client):
        """Main dashboard page."""
        
        # Add custom CSS and fonts
        ui.add_head_html('''
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Audiowide&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <link rel="stylesheet" href="/static/style.css">
        ''')
        
        # State
        terminal_log = None
        card_container = None
        add_dialog = None
        edit_dialog = None
        current_edit_server = {}
        
        def refresh_cards():
            if card_container is None:
                return
            card_container.clear()
            with card_container:
                build_server_cards()
                build_add_card()
        
        def on_log_message(msg: str):
            if terminal_log:
                terminal_log.push(msg + "\n")
        
        log_handler.subscribe(on_log_message)
        client.on_disconnect(lambda: log_handler.unsubscribe(on_log_message))
        
        # ---------------------------------------------------------------------
        # Build Server Cards
        # ---------------------------------------------------------------------
        def build_server_cards():
            servers = get_servers_list()
            for server in servers:
                build_single_card(server)
        
        def build_single_card(server: Dict[str, Any]):
            app_id = server.get('appId', '')
            name = server.get('name', f'App {app_id}')
            status = server.get('status', 'stopped')
            ip_addr = server.get('ip') or 'No IP set'
            version = server.get('version', '?')
            image_url = server.get('image') or '/static/spawnpoint_add.jpg'
            is_running = status == 'running'
            
            with ui.element('div').style(CARD_STYLE):
                # Top glow border
                ui.element('div').style(BORDER_TOP)
                
                # Settings gear
                def open_edit():
                    current_edit_server.clear()
                    current_edit_server.update(server)
                    populate_edit_dialog(server)
                    edit_dialog.open()
                
                with ui.element('div').style('position: absolute; top: 0.5rem; right: 0.5rem; width: 16px; height: 16px; cursor: pointer; z-index: 10;').on('click', open_edit):
                    ui.image('/static/GameConfig.svg').style('width: 100%; height: 100%; filter: brightness(0) invert(1); opacity: 0.7; transition: opacity 0.3s;')
                
                # Card image
                ui.image(image_url).style('position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 0;')
                
                # Overlay container - full height, flex column
                with ui.element('div').style('position: relative; width: 100%; height: 100%; display: flex; flex-direction: column; padding: 0.5rem; z-index: 1;'):
                    # Top info section
                    with ui.element('div').style('display: flex; flex-direction: column; gap: 0.25rem; align-self: flex-start;'):
                        ui.label(name.upper()).style('font-family: Audiowide, cursive; font-size: 14px; font-weight: 700; color: #fff; background: rgba(0,0,0,0.7); padding: 0.25rem 0.5rem; border-radius: 5px; letter-spacing: 0.5px;')
                        ui.label(ip_addr).style('font-family: Inter, sans-serif; font-size: 12px; color: #fff; background: rgba(0,0,0,0.7); padding: 0.25rem 0.5rem; border-radius: 5px;')
                    
                    # Spacer
                    ui.element('div').style('flex: 1;')
                    
                    # Bottom controls section
                    with ui.element('div').style('display: flex; flex-direction: column; gap: 0.5rem;'):
                        # Row with button and status
                        with ui.element('div').style('display: flex; gap: 0.5rem; align-items: center;'):
                            async def toggle_server(aid=app_id, running=is_running):
                                action = 'stop' if running else 'start'
                                servers = read_servers_file()
                                srv = find_server(servers, aid)
                                if srv:
                                    srv['status'] = 'stopped' if running else 'running'
                                    write_servers_file(servers)
                                    logger.info("Server %s %s", aid, srv['status'])
                                    ui.notify(f"Server {action}ed", type='positive')
                                    refresh_cards()
                            
                            ui.button(f'{"■" if is_running else "▶"} {"Stop" if is_running else "Start"}', on_click=toggle_server).style(BTN_STYLE)
                            ui.label(f'Status: {status}').style(TEXT_BG + ' flex: 1;')
                        
                        # Version row - full width
                        ui.label(f'Ver: {version} (Current)').style(TEXT_BG + ' width: 100%;')
                
                # Bottom glow border
                ui.element('div').style(BORDER_BOTTOM)
        
        def build_add_card():
            with ui.element('div').style(CARD_STYLE):
                ui.element('div').style(BORDER_TOP)
                ui.image('/static/spawnpoint_add.jpg').style('position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover;')
                with ui.element('div').style('position: absolute; inset: 0; background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.6) 40%, transparent 70%); display: flex; align-items: flex-end; padding: 1rem; z-index: 3;'):
                    ui.button('+ Add', on_click=lambda: add_dialog.open()).style(BTN_STYLE)
                ui.element('div').style(BORDER_BOTTOM)
        
        # ---------------------------------------------------------------------
        # Add Server Dialog
        # ---------------------------------------------------------------------
        with ui.dialog().props('persistent') as add_dialog:
            with ui.card().style('background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 2px solid #00ffff; border-radius: 8px; width: 500px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 0 30px rgba(0, 255, 255, 0.3);'):
                ui.element('div').style(BORDER_TOP)
                with ui.element('div').style('display: flex; justify-content: space-between; align-items: center; padding: 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.1);'):
                    ui.label('Add New Game Server').style('color: #00ffff; font-family: Audiowide, cursive; font-size: 1.25rem;')
                    ui.button('×', on_click=add_dialog.close).style(CLOSE_BTN)
                
                with ui.element('div').style('padding: 1.25rem;'):
                    add_app_id = ui.input('Steam App ID', placeholder='e.g., 2394010 for Palworld').classes('w-full')
                    add_status = ui.label('')
                    
                    async def do_add_server():
                        aid = add_app_id.value.strip()
                        if not aid:
                            add_status.text = 'App ID is required'
                            add_status.style('color: #ff4444; margin-top: 1rem;')
                            return
                        if _install_lock.locked():
                            add_status.text = 'Another install is in progress'
                            add_status.style('color: #ff4444; margin-top: 1rem;')
                            return
                        add_status.text = 'Starting installation...'
                        add_status.style('color: #00aaff; margin-top: 1rem;')
                        await _install_lock.acquire()
                        install_path = GAMES_DIR / f"app_{aid}"
                        asyncio.create_task(run_steamcmd_install(aid, install_path))
                        add_status.text = 'Installation started! Watch terminal.'
                        add_status.style('color: #00ff88; margin-top: 1rem;')
                        await asyncio.sleep(2)
                        add_dialog.close()
                        add_app_id.value = ''
                        refresh_cards()
                
                    with ui.element('div').style('display: flex; gap: 10px; justify-content: flex-end; margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1);'):
                        ui.button('Cancel', on_click=add_dialog.close).style(MODAL_BTN)
                        ui.button('Install', on_click=do_add_server).style(MODAL_BTN)
                ui.element('div').style(BORDER_BOTTOM)
        
        # ---------------------------------------------------------------------
        # Edit Server Dialog
        # ---------------------------------------------------------------------
        edit_title_el = None
        edit_app_id_el = None
        edit_port_el = None
        edit_path_el = None
        edit_preview_el = None
        edit_status_el = None
        
        def populate_edit_dialog(server: Dict[str, Any]):
            nonlocal edit_title_el, edit_app_id_el, edit_port_el, edit_path_el, edit_preview_el
            if edit_title_el:
                edit_title_el.text = f"Edit: {server.get('name', server.get('appId', ''))}"
            if edit_app_id_el:
                edit_app_id_el.value = server.get('appId', '')
            if edit_port_el:
                edit_port_el.value = str(server.get('port', '')) if server.get('port') else ''
            if edit_path_el:
                edit_path_el.value = server.get('installPath', '')
            if edit_preview_el:
                edit_preview_el.source = server.get('image') or '/static/spawnpoint_add.jpg'
        
        with ui.dialog().props('persistent') as edit_dialog:
            with ui.card().style('background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 2px solid #00ffff; border-radius: 8px; width: 700px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 0 30px rgba(0, 255, 255, 0.3);'):
                ui.element('div').style(BORDER_TOP)
                with ui.element('div').style('display: flex; justify-content: space-between; align-items: center; padding: 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.1);'):
                    edit_title_el = ui.label('Edit Server Settings').style('color: #00ffff; font-family: Audiowide, cursive; font-size: 1.25rem;')
                    ui.button('×', on_click=edit_dialog.close).style(CLOSE_BTN)
                
                with ui.element('div').style('padding: 1.25rem;'):
                    edit_app_id_el = ui.input('App ID').props('readonly').classes('w-full')
                    edit_port_el = ui.input('Server Port', placeholder='e.g., 40401').classes('w-full')
                    edit_path_el = ui.input('Install Path').props('readonly').classes('w-full')
                    
                    ui.label('Card Image').style('color: #94a3b8; margin-top: 1rem;')
                    edit_preview_el = ui.image('/static/spawnpoint_add.jpg').style('height: 120px; width: 100%; object-fit: cover; border: 1px solid rgba(255,255,255,0.1);')
                    
                    async def on_upload(e):
                        if not current_edit_server or not e.content:
                            return
                        aid = current_edit_server.get('appId')
                        if not aid:
                            return
                        ext = Path(e.name).suffix or '.jpg'
                        dest = STATIC_DIR / "images" / f"server_{aid}{ext}"
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(e.content.read())
                        new_url = f"/static/images/server_{aid}{ext}"
                        servers = read_servers_file()
                        srv = find_server(servers, aid)
                        if srv:
                            srv['image'] = new_url
                            write_servers_file(servers)
                        edit_preview_el.source = new_url
                        ui.notify('Image uploaded!', type='positive')
                    
                    ui.upload(on_upload=on_upload, auto_upload=True).props('accept=".jpg,.jpeg,.png,.gif,.webp"')
                    ui.link('Find art at SteamGridDB', 'https://www.steamgriddb.com/', new_tab=True).style('font-size: 12px; color: #00ffff;')
                    
                    edit_status_el = ui.label('')
                    
                    async def do_save_edit():
                        if not current_edit_server:
                            return
                        aid = current_edit_server.get('appId')
                        servers = read_servers_file()
                        srv = find_server(servers, aid)
                        if srv:
                            port_val = edit_port_el.value.strip() if edit_port_el else ''
                            if port_val:
                                srv['port'] = int(port_val)
                            write_servers_file(servers)
                            edit_status_el.text = 'Saved!'
                            edit_status_el.style('color: #00ff88; margin-top: 0.5rem;')
                            await asyncio.sleep(1)
                            edit_dialog.close()
                            refresh_cards()
                    
                    with ui.element('div').style('display: flex; gap: 10px; justify-content: flex-end; margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1);'):
                        ui.button('Cancel', on_click=edit_dialog.close).style(MODAL_BTN)
                        ui.button('Save', on_click=do_save_edit).style(MODAL_BTN)
                ui.element('div').style(BORDER_BOTTOM)
        
        # ---------------------------------------------------------------------
        # Main Layout
        # ---------------------------------------------------------------------
        with ui.element('div').style('display: flex; width: 100%; height: 100vh; overflow: hidden;'):
            # Left Column - Cards
            with ui.element('div').style('flex: 1; display: flex; flex-direction: column; padding: 2rem; overflow-y: auto; min-width: 0;'):
                # Header with blurred gradient behind (like original)
                with ui.element('div').style('position: relative; display: inline-block; width: fit-content; margin-bottom: 1rem;'):
                    # Blurred gradient pseudo-element
                    ui.label('SpawnPoint').style('''
                        position: absolute; top: 0; left: 0;
                        font-family: Audiowide, cursive; font-size: 48px; font-weight: 700;
                        background: linear-gradient(180deg, #ec4899, #a855f7, #3b82f6);
                        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                        background-clip: text; filter: blur(4px); z-index: -1; opacity: 0.8;
                    ''')
                    # Actual white text
                    ui.label('SpawnPoint').style('font-family: Audiowide, cursive; font-size: 48px; font-weight: 700; color: #fff;')
                
                # Card grid - flex wrap like original
                with ui.element('div').style('display: flex; flex-wrap: wrap; gap: 1.5rem;') as cg:
                    card_container = cg
                    build_server_cards()
                    build_add_card()
            
            # Column Resizer - between cards and terminal
            ui.element('div').props('id=terminal-resizer').style('width: 8px; cursor: col-resize; background: transparent; flex-shrink: 0; align-self: stretch;')
            
            # Right Column - Terminal (fixed to right side)
            with ui.element('div').props('id=terminal-column').style('width: 400px; height: 100vh; display: flex; flex-direction: column; padding: 2rem; padding-left: 0; position: relative; flex-shrink: 0;'):
                # Glow border on left side
                ui.element('div').style('position: absolute; top: 2rem; left: 0; width: 4px; height: calc(100% - 4rem); background: linear-gradient(180deg, #ec4899, #a855f7, #3b82f6); box-shadow: 0 0 20px rgba(168, 85, 247, 0.8), 0 0 40px rgba(168, 85, 247, 0.4); border-radius: 2px;')
                
                # Header row
                with ui.element('div').style('display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; padding-left: 1.5rem;'):
                    async def toggle_terminal():
                        await ui.run_javascript('''
                            const col = document.getElementById('terminal-column');
                            const btn = document.getElementById('terminal-toggle-btn');
                            if (col) {
                                col.classList.toggle('collapsed');
                                const isCollapsed = col.classList.contains('collapsed');
                                if (btn) btn.innerText = isCollapsed ? '<' : '>';
                            }
                        ''')
                    
                    ui.button('>', on_click=toggle_terminal).props('id=terminal-toggle-btn').style('background: transparent !important; border: none; color: #fff !important; font-size: 1.5rem; cursor: pointer; padding: 0.25rem; line-height: 1; box-shadow: none !important; min-height: auto !important;')
                    ui.label('TERMINAL').classes('terminal-title-text').style('font-size: 1rem; font-weight: 700; letter-spacing: 2px; color: #fff;')
                    ui.element('div').style('flex: 1;')
                    ui.label('127.0.0.1:40400').classes('terminal-ip').style('font-size: 0.75rem; color: #9ca3af;')
                
                # Log output container - fills remaining height, no scrollbars
                with ui.element('div').classes('terminal-content').style('flex: 1; margin-left: 1.5rem; min-height: 0; display: flex; flex-direction: column;'):
                    terminal_log = ui.log(max_lines=500).classes('terminal-log').style('flex: 1; min-height: 0;')
                
                for line in log_handler.get_logs().split('\n'):
                    if line.strip():
                        terminal_log.push(line + "\n")
        
        # Terminal resize JavaScript - simple and reliable
        ui.add_body_html('''
            <script>
            (function() {
                const resizer = document.getElementById('terminal-resizer');
                const terminalColumn = document.getElementById('terminal-column');
                
                if (!resizer || !terminalColumn) {
                    console.log('Resizer elements not found');
                    return;
                }
                
                const MIN_WIDTH = 240;
                const MAX_WIDTH = 800;
                let isResizing = false;
                let startX = 0;
                let startWidth = 0;
                let lastWidth = 400;
                
                function onMouseMove(e) {
                    if (!isResizing) return;
                    e.preventDefault();
                    const delta = startX - e.clientX;
                    let newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth + delta));
                    terminalColumn.style.width = newWidth + 'px';
                    lastWidth = newWidth;
                }
                
                function onMouseUp() {
                    if (!isResizing) return;
                    isResizing = false;
                    document.removeEventListener('mousemove', onMouseMove);
                    document.removeEventListener('mouseup', onMouseUp);
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }
                
                resizer.addEventListener('mousedown', function(e) {
                    if (terminalColumn.classList.contains('collapsed')) return;
                    e.preventDefault();
                    isResizing = true;
                    startX = e.clientX;
                    startWidth = terminalColumn.getBoundingClientRect().width;
                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup', onMouseUp);
                    document.body.style.cursor = 'col-resize';
                    document.body.style.userSelect = 'none';
                });
            })();
            </script>
        ''')


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

def setup_api_routes():
    """Setup REST API endpoints."""
    
    @app.get('/api/servers')
    def api_list_servers():
        return get_servers_list()
    
    @app.post('/api/servers/add')
    async def api_add_server(request):
        data = await request.json()
        aid = str(data.get('appId') or data.get('id') or '')
        if not aid:
            return {'error': 'appId is required'}
        if _install_lock.locked():
            return {'error': 'Another install is running'}
        await _install_lock.acquire()
        install_path = GAMES_DIR / f"app_{aid}"
        asyncio.create_task(run_steamcmd_install(aid, install_path))
        return {'status': 'started', 'appId': aid, 'installPath': str(install_path)}
    
    @app.post('/api/servers/{app_id}/{action}')
    async def api_control_server(app_id: str, action: str):
        if action not in ('start', 'stop'):
            return {'error': 'action must be start or stop'}
        servers = read_servers_file()
        srv = find_server(servers, app_id)
        if not srv:
            return {'error': 'server not found'}
        srv['status'] = 'running' if action == 'start' else 'stopped'
        write_servers_file(servers)
        return {'status': srv['status']}
    
    @app.put('/api/servers/{app_id}')
    async def api_update_server(app_id: str, request):
        data = await request.json()
        servers = read_servers_file()
        srv = find_server(servers, app_id)
        if not srv:
            return {'error': 'server not found'}
        if data.get('port'):
            srv['port'] = int(data['port'])
        if data.get('settingsFile') is not None:
            srv['settingsFile'] = data['settingsFile']
        if data.get('installPath'):
            srv['installPath'] = data['installPath']
        write_servers_file(servers)
        return {'status': 'ok', 'server': srv}
    
    @app.get('/api/servers/{app_id}/version')
    def api_server_version(app_id: str):
        servers = read_servers_file()
        srv = find_server(servers, app_id)
        if not srv:
            return {'error': 'server not found'}
        return {
            'current': srv.get('version') or 'unknown',
            'latest': srv.get('version') or 'unknown',
            'updateAvailable': False
        }
    
    @app.get('/uvicorn/logs')
    def api_get_logs():
        return log_handler.get_logs()


# ---------------------------------------------------------------------------
# Application Setup
# ---------------------------------------------------------------------------

def initialize():
    """Initialize SpawnPoint application."""
    setup_static_files()
    create_main_page()
    setup_api_routes()
    logger.info("SpawnPoint initialized")
