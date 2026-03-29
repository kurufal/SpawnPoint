"""
SpawnPoint - Game Server Manager
Core logic and UI components for managing game servers via SteamCMD.
"""

import asyncio
import asyncio.subprocess as asp
import json
import logging
import os
import re
import shutil
import signal
import time
from collections import deque
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

import psutil
from dotenv import load_dotenv
from nicegui import app, ui, Client

load_dotenv()

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
_running_processes: Dict[str, asp.Process] = {}  # app_id -> running subprocess

_APP_ID_RE = re.compile(r'^\d{1,10}$')


def validate_app_id(app_id: str) -> bool:
    """Validate that app_id is a plain numeric Steam App ID."""
    return bool(_APP_ID_RE.match(str(app_id).strip()))


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
            "image": None,
            "launchParams": ""
        }]
    return servers


# ---------------------------------------------------------------------------
# SteamCMD Installation
# ---------------------------------------------------------------------------

async def run_steamcmd_install(app_id: str, install_dir: Path) -> None:
    """Run steamcmd to install/update a game server."""
    steamcmd_logger = logging.getLogger("spawnpoint.steamcmd")
    try:
        if not validate_app_id(app_id):
            steamcmd_logger.error("Invalid app ID rejected: %s", app_id)
            return
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
                    "image": None,
                    "launchParams": ""
                }
                servers.append(entry)
            else:
                existing["installPath"] = str(install_dir)
                if existing.get("status") == "installing":
                    existing["status"] = "stopped"
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
            <script src="/static/terminal.js" defer></script>
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
                            
                            safe_name = name.replace("'", "\\'")
                            ui.button(f'Status: {status}').style(BTN_STYLE + ' flex: 1; text-align: left;').on(
                                'click', js_handler=f"() => window.spOpenTab('server-{app_id}', '{safe_name}')"
                            )
                        
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
                # Header (drag handle)
                with ui.row().classes('w-full items-center drag-handle').style('padding: 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.1); cursor: move;'):
                    ui.label('Add New Game Server').style('color: #00ffff; font-family: Audiowide, cursive; font-size: 1.25rem;')
                
                # Form body
                with ui.column().classes('w-full').style('padding: 1.25rem; gap: 0.75rem;'):
                    ui.label('Steam App ID').classes('form-label')
                    add_app_id = ui.input(placeholder='e.g., 2394010 for Palworld').props('dense outlined').classes('w-full')
                    ui.label('Server Name').classes('form-label')
                    add_name = ui.input(placeholder='e.g., My Palworld Server').props('dense outlined').classes('w-full')
                    ui.label('Server Port').classes('form-label')
                    add_port = ui.input(placeholder='e.g., 8211').props('dense outlined').classes('w-full')
                    
                    add_status = ui.label('')
                    
                    async def do_add_server():
                        aid = add_app_id.value.strip()
                        if not aid:
                            add_status.text = 'App ID is required'
                            add_status.style('color: #ff4444; margin-top: 0.5rem;')
                            return
                        if not validate_app_id(aid):
                            add_status.text = 'App ID must be numeric'
                            add_status.style('color: #ff4444; margin-top: 0.5rem;')
                            return
                        if _install_lock.locked():
                            add_status.text = 'Another install is in progress'
                            add_status.style('color: #ff4444; margin-top: 0.5rem;')
                            return
                        
                        # Save server entry immediately with user-provided name/port
                        server_name = add_name.value.strip() or f'App {aid}'
                        port_val = None
                        if add_port.value.strip():
                            try:
                                port_val = int(add_port.value.strip())
                            except ValueError:
                                add_status.text = 'Port must be a number'
                                add_status.style('color: #ff4444; margin-top: 0.5rem;')
                                return
                        
                        install_path = GAMES_DIR / f"app_{aid}"
                        servers = read_servers_file()
                        if not find_server(servers, aid):
                            servers.append({
                                "appId": str(aid),
                                "name": server_name,
                                "status": "installing",
                                "port": port_val,
                                "installPath": str(install_path),
                                "settingsFile": None,
                                "version": None,
                                "updateAvailable": False,
                                "ip": "",
                                "image": None,
                                "launchParams": ""
                            })
                            write_servers_file(servers)
                        
                        add_status.text = 'Starting installation...'
                        add_status.style('color: #00aaff; margin-top: 0.5rem;')
                        await _install_lock.acquire()
                        asyncio.create_task(run_steamcmd_install(aid, install_path))
                        add_status.text = 'Installation started! Watch terminal.'
                        add_status.style('color: #00ff88; margin-top: 0.5rem;')
                        await asyncio.sleep(2)
                        add_dialog.close()
                        add_app_id.value = ''
                        add_name.value = ''
                        add_port.value = ''
                        refresh_cards()
                
                    # Buttons
                    with ui.row().classes('w-full justify-end').style('margin-top: 0.5rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1); gap: 10px;'):
                        ui.button('Cancel', on_click=add_dialog.close).style(MODAL_BTN)
                        ui.button('Install', on_click=do_add_server).style(MODAL_BTN)
        
        # ---------------------------------------------------------------------
        # Edit Server Dialog
        # ---------------------------------------------------------------------
        edit_title_el = None
        edit_app_id_el = None
        edit_name_el = None
        edit_port_el = None
        edit_path_el = None
        edit_launch_params_el = None
        edit_ip_el = None
        edit_preview_el = None
        edit_status_el = None
        edit_cpu_el = None
        edit_ram_el = None
        
        def populate_edit_dialog(server: Dict[str, Any]):
            nonlocal edit_title_el, edit_app_id_el, edit_name_el, edit_port_el
            nonlocal edit_path_el, edit_launch_params_el, edit_ip_el, edit_preview_el
            nonlocal edit_cpu_el, edit_ram_el
            if edit_title_el:
                edit_title_el.text = f"Edit: {server.get('name', server.get('appId', ''))}"
            if edit_app_id_el:
                edit_app_id_el.value = server.get('appId', '')
            if edit_name_el:
                edit_name_el.value = server.get('name', '')
            if edit_port_el:
                edit_port_el.value = str(server.get('port', '')) if server.get('port') else ''
            if edit_path_el:
                edit_path_el.value = server.get('installPath', '')
            if edit_launch_params_el:
                edit_launch_params_el.value = server.get('launchParams', '')
            if edit_ip_el:
                edit_ip_el.value = server.get('ip', '')
            if edit_preview_el:
                img = server.get('image') or '/static/spawnpoint_add.jpg'
                edit_preview_el.source = f"{img}?t={int(time.time())}"
            if edit_cpu_el:
                edit_cpu_el.text = f'CPU: {psutil.cpu_percent(interval=0)}%'
            if edit_ram_el:
                mem = psutil.virtual_memory()
                edit_ram_el.text = f'RAM: {round(mem.used / (1024**3), 1)}GB / {round(mem.total / (1024**3), 1)}GB ({mem.percent}%)'
        
        with ui.dialog().props('persistent') as edit_dialog:
            with ui.card().style('background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 2px solid #00ffff; border-radius: 8px; width: 600px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 0 30px rgba(0, 255, 255, 0.3);'):
                # Header (drag handle)
                with ui.row().classes('w-full items-center drag-handle').style('padding: 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.1); cursor: move;'):
                    edit_title_el = ui.label('Edit Server Settings').style('color: #00ffff; font-family: Audiowide, cursive; font-size: 1.25rem;')
                
                # Form body
                with ui.column().classes('w-full').style('padding: 1.25rem; gap: 0.5rem;'):
                    # -- Identity section --
                    ui.label('Server Identity').classes('modal-section-label')
                    ui.label('App ID').classes('form-label')
                    edit_app_id_el = ui.input().props('readonly dense outlined').classes('w-full')
                    ui.label('Server Name').classes('form-label')
                    edit_name_el = ui.input(placeholder='Friendly display name').props('dense outlined').classes('w-full')
                    
                    # -- Network section --
                    ui.label('Network').classes('modal-section-label')
                    with ui.row().classes('w-full').style('gap: 0.75rem;'):
                        with ui.column().style('flex: 2; gap: 0.25rem;'):
                            ui.label('IP / Hostname').classes('form-label')
                            edit_ip_el = ui.input(placeholder='0.0.0.0').props('dense outlined').classes('w-full')
                        with ui.column().style('flex: 1; gap: 0.25rem;'):
                            ui.label('Port').classes('form-label')
                            edit_port_el = ui.input(placeholder='e.g., 8211').props('dense outlined').classes('w-full')
                    
                    # -- Launch section --
                    ui.label('Launch').classes('modal-section-label')
                    ui.label('Install Path').classes('form-label')
                    edit_path_el = ui.input().props('readonly dense outlined').classes('w-full')
                    ui.label('Launch Parameters').classes('form-label')
                    edit_launch_params_el = ui.input(placeholder='e.g., -players=32 -port=8211').props('dense outlined').classes('w-full')
                    
                    # -- Card Image + System Stats --
                    ui.label('Card Image & System Stats').classes('modal-section-label')
                    with ui.element('div').style('display: flex; gap: 1rem; width: 100%;'):
                        # Left: portrait preview + upload button
                        with ui.element('div').style('display: flex; flex-direction: column; gap: 0.5rem; align-items: center; flex-shrink: 0;'):
                            edit_preview_el = ui.image('/static/spawnpoint_add.jpg').style(
                                'width: 150px; height: 192px; object-fit: cover;'
                                ' border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;'
                            )
                            
                            async def on_upload(e):
                                if not current_edit_server or not e.content:
                                    return
                                aid = current_edit_server.get('appId')
                                if not aid:
                                    return
                                ext = Path(e.name).suffix.lower() or '.jpg'
                                images_dir = STATIC_DIR / "images"
                                images_dir.mkdir(parents=True, exist_ok=True)
                                for old in images_dir.glob(f"server_{aid}.*"):
                                    old.unlink(missing_ok=True)
                                dest = images_dir / f"server_{aid}{ext}"
                                dest.write_bytes(e.content.read())
                                new_url = f"/static/images/server_{aid}{ext}?t={int(time.time())}"
                                servers = read_servers_file()
                                srv = find_server(servers, aid)
                                if srv:
                                    srv['image'] = f"/static/images/server_{aid}{ext}"
                                    write_servers_file(servers)
                                edit_preview_el.source = new_url
                                ui.notify('Image updated!', type='positive')
                            
                            hidden_upload = ui.upload(
                                on_upload=on_upload, auto_upload=True
                            ).props('accept=".jpg,.jpeg,.png,.gif,.webp"').style(
                                'position: fixed; left: -9999px; top: -9999px; width: 1px; height: 1px; opacity: 0;'
                            )
                            
                            def pick_image():
                                hidden_upload.run_method('pickFiles')
                            
                            ui.button('Change Image', on_click=pick_image).style(
                                BTN_STYLE + ' font-size: 10px !important; padding: 0.3rem 0.6rem !important;'
                            )
                            ui.link('SteamGridDB', 'https://www.steamgriddb.com/', new_tab=True).style(
                                'font-size: 10px; color: #00ffff;'
                            )
                        
                        # Right: system / server stats
                        with ui.element('div').style(
                            'flex: 1; display: flex; flex-direction: column; gap: 0.4rem;'
                            ' padding: 0.75rem; background: rgba(0,0,0,0.3);'
                            ' border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;'
                        ):
                            ui.label('System Stats').style(
                                'font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px;'
                                ' color: #64748b; margin-bottom: 0.25rem;'
                            )
                            cpu_pct = psutil.cpu_percent(interval=0)
                            mem = psutil.virtual_memory()
                            disk = psutil.disk_usage(str(GAMES_DIR))
                            edit_cpu_el = ui.label(f'CPU: {cpu_pct}%').style(
                                'font-family: "Courier New", monospace; font-size: 0.75rem; color: #9ca3af;'
                            )
                            edit_ram_el = ui.label(
                                f'RAM: {round(mem.used / (1024**3), 1)}GB / {round(mem.total / (1024**3), 1)}GB ({mem.percent}%)'
                            ).style(
                                'font-family: "Courier New", monospace; font-size: 0.75rem; color: #9ca3af;'
                            )
                            ui.label(
                                f'Disk: {round(disk.free / (1024**3), 1)}GB free'
                            ).style(
                                'font-family: "Courier New", monospace; font-size: 0.75rem; color: #9ca3af;'
                            )
                            ui.separator().style('margin: 0.25rem 0; border-color: rgba(255,255,255,0.08);')
                            ui.label('Server Stats').style(
                                'font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px;'
                                ' color: #64748b;'
                            )
                            edit_srv_cpu_el = ui.label('CPU: --').style(
                                'font-family: "Courier New", monospace; font-size: 0.75rem; color: #6b7280;'
                            )
                            edit_srv_ram_el = ui.label('RAM: --').style(
                                'font-family: "Courier New", monospace; font-size: 0.75rem; color: #6b7280;'
                            )
                            edit_srv_uptime_el = ui.label('Uptime: --').style(
                                'font-family: "Courier New", monospace; font-size: 0.75rem; color: #6b7280;'
                            )
                    
                    edit_status_el = ui.label('')
                    
                    async def do_save_edit():
                        if not current_edit_server:
                            return
                        aid = current_edit_server.get('appId')
                        servers = read_servers_file()
                        srv = find_server(servers, aid)
                        if srv:
                            # Name
                            name_val = edit_name_el.value.strip() if edit_name_el else ''
                            if name_val:
                                srv['name'] = name_val
                            # Port
                            port_val = edit_port_el.value.strip() if edit_port_el else ''
                            if port_val:
                                try:
                                    srv['port'] = int(port_val)
                                except ValueError:
                                    edit_status_el.text = 'Port must be a number'
                                    edit_status_el.style('color: #ff4444; margin-top: 0.5rem;')
                                    return
                            # IP
                            ip_val = edit_ip_el.value.strip() if edit_ip_el else ''
                            srv['ip'] = ip_val
                            # Launch params
                            params_val = edit_launch_params_el.value.strip() if edit_launch_params_el else ''
                            srv['launchParams'] = params_val
                            
                            write_servers_file(servers)
                            edit_status_el.text = 'Saved!'
                            edit_status_el.style('color: #00ff88; margin-top: 0.5rem;')
                            await asyncio.sleep(1)
                            edit_dialog.close()
                            refresh_cards()
                    
                    async def do_delete_server():
                        if not current_edit_server:
                            return
                        aid = current_edit_server.get('appId')
                        servers = read_servers_file()
                        servers = [s for s in servers if str(s.get('appId')) != str(aid)]
                        write_servers_file(servers)
                        logger.info("Server %s removed", aid)
                        ui.notify('Server removed', type='warning')
                        edit_dialog.close()
                        refresh_cards()
                    
                    async def do_restart_server():
                        if not current_edit_server:
                            return
                        aid = current_edit_server.get('appId')
                        servers = read_servers_file()
                        srv = find_server(servers, aid)
                        if srv:
                            srv['status'] = 'running'
                            write_servers_file(servers)
                            logger.info("Server %s restarted", aid)
                            ui.notify('Server restarted', type='positive')
                            refresh_cards()

                    # Buttons — all on one row
                    with ui.row().classes('w-full items-center').style('margin-top: 0.5rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1); gap: 10px;'):
                        ui.button('Delete', on_click=do_delete_server).style(MODAL_BTN + ' color: #ff4444 !important;')
                        ui.button('Restart', on_click=do_restart_server).style(MODAL_BTN + ' color: #ffaa00 !important;')
                        ui.element('div').style('flex: 1;')
                        ui.button('Cancel', on_click=edit_dialog.close).style(MODAL_BTN)
                        ui.button('Save', on_click=do_save_edit).style(MODAL_BTN)
        
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
            
            # Neon Resizer / Divider
            ui.element('div').props('id=terminal-resizer').style(
                'width: 4px; flex-shrink: 0; align-self: stretch; position: relative; z-index: 50;'
                ' background: linear-gradient(180deg, #ec4899, #a855f7, #3b82f6);'
                ' box-shadow: 0 0 15px rgba(168, 85, 247, 0.6), 0 0 30px rgba(168, 85, 247, 0.3);'
                ' cursor: col-resize; border-radius: 2px;'
            )

            # ── Terminal Column ──
            with ui.element('div').props('id=terminal-column').style(
                'width: 400px; height: 100vh; display: flex; flex-direction: row;'
                ' position: relative; overflow: hidden;'
            ):
                # Left part: tabs + log content (fills remaining width)
                with ui.element('div').props('id=terminal-left').style(
                    'flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden;'
                ):
                    # Tab bar (tabs only, no collapse button)
                    ui.html('''
                        <div class="terminal-tab-bar" id="terminal-tab-bar">
                            <button class="terminal-tab active" data-tab="main"
                                    onclick="window.spSwitchTab('main')">Main</button>
                            <span style="flex:1" data-role="spacer"></span>
                        </div>
                    ''', sanitize=False).classes('terminal-tabs-wrapper')

                    # Log content
                    with ui.element('div').classes('terminal-content').props('id=terminal-content'):
                        with ui.element('div').classes('terminal-tab-panel active').props(
                            'data-tab=main id=tab-panel-main'
                        ):
                            terminal_log = ui.log(max_lines=500).classes('terminal-log')

                # Right side: TERMINAL title column with collapse button at top
                with ui.element('div').classes('terminal-title-col').style(
                    'width: 36px; flex-shrink: 0; display: flex; flex-direction: column;'
                    ' align-items: center; position: relative; overflow: hidden;'
                    ' background: linear-gradient(180deg, rgba(3,7,18,0.5) 0%, rgba(15,23,42,0.5) 100%);'
                    ' border-left: 1px solid #374151;'
                ):
                    # Collapse/expand button at top
                    ui.html('''
                        <button id="terminal-toggle-btn" class="terminal-toggle-btn"
                                onclick="window.spToggleTerminal()"
                                style="margin-top: 0.4rem;">&#x276F;</button>
                    ''', sanitize=False)
                    # Blurred glow layer
                    ui.label('TERMINAL').style('''
                        position: absolute; top: 40px;
                        writing-mode: vertical-rl; text-orientation: mixed;
                        font-family: Audiowide, cursive; font-size: 1rem; font-weight: 700;
                        letter-spacing: 4px; text-transform: uppercase;
                        background: linear-gradient(180deg, #ec4899, #a855f7, #3b82f6);
                        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                        background-clip: text; filter: blur(4px); opacity: 0.7;
                        pointer-events: none;
                    ''')
                    # Actual white text
                    ui.label('TERMINAL').style('''
                        position: absolute; top: 40px;
                        writing-mode: vertical-rl; text-orientation: mixed;
                        font-family: Audiowide, cursive; font-size: 1rem; font-weight: 700;
                        letter-spacing: 4px; text-transform: uppercase;
                        color: #fff; pointer-events: none;
                    ''')

                for line in log_handler.get_logs().split('\n'):
                    if line.strip():
                        terminal_log.push(line + "\n")


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
        if not validate_app_id(aid):
            return {'error': 'appId must be numeric'}
        if _install_lock.locked():
            return {'error': 'Another install is running'}
        await _install_lock.acquire()
        install_path = GAMES_DIR / f"app_{aid}"
        asyncio.create_task(run_steamcmd_install(aid, install_path))
        return {'status': 'started', 'appId': aid, 'installPath': str(install_path)}
    
    @app.post('/api/servers/{app_id}/{action}')
    async def api_control_server(app_id: str, action: str):
        if action not in ('start', 'stop', 'restart'):
            return {'error': 'action must be start, stop, or restart'}
        if not validate_app_id(app_id):
            return {'error': 'invalid app_id'}
        servers = read_servers_file()
        srv = find_server(servers, app_id)
        if not srv:
            return {'error': 'server not found'}
        # TODO: Replace with real process management
        srv['status'] = 'running' if action in ('start', 'restart') else 'stopped'
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
    
    @app.post('/api/upload-image/{app_id}')
    async def api_upload_image(request):
        from starlette.responses import JSONResponse
        app_id = request.path_params.get('app_id', '')
        if not validate_app_id(app_id):
            return JSONResponse({'error': 'Invalid app ID'}, status_code=400)
        form = await request.form()
        upload_file = form.get('file')
        if not upload_file:
            return JSONResponse({'error': 'No file provided'}, status_code=400)
        ext = Path(upload_file.filename).suffix.lower() or '.jpg'
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            return JSONResponse({'error': 'Invalid file type'}, status_code=400)
        images_dir = STATIC_DIR / 'images'
        images_dir.mkdir(parents=True, exist_ok=True)
        for old in images_dir.glob(f'server_{app_id}.*'):
            old.unlink(missing_ok=True)
        dest = images_dir / f'server_{app_id}{ext}'
        content = await upload_file.read()
        dest.write_bytes(content)
        url = f'/static/images/server_{app_id}{ext}'
        servers = read_servers_file()
        srv = find_server(servers, app_id)
        if srv:
            srv['image'] = url
            write_servers_file(servers)
        return JSONResponse({'url': url + '?t=' + str(int(time.time()))})


# ---------------------------------------------------------------------------
# Application Setup
# ---------------------------------------------------------------------------

def initialize():
    """Initialize SpawnPoint application."""
    setup_static_files()
    create_main_page()
    setup_api_routes()
    logger.info("SpawnPoint initialized")
