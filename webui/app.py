from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import logging
from collections import deque
import json
import asyncio
from pathlib import Path
import shutil
import sys
import asyncio.subprocess as asp

# --- in-memory log buffer for exposing uvicorn/app logs to the UI ---
class InMemoryLogHandler(logging.Handler):
    def __init__(self, max_lines: int = 1000):
        super().__init__()
        self.buffer = deque(maxlen=max_lines)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self.buffer.append(msg)

    def get_logs(self) -> str:
        return "\n".join(self.buffer)

# create a single shared handler and attach to relevant loggers
_log_handler = InMemoryLogHandler(max_lines=2000)
_formatter = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
_log_handler.setFormatter(_formatter)
_log_handler.setLevel(logging.INFO)

# --- Create FastAPI app with lifespan first ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: re-attach loggers and emit test message
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if all(h is not _log_handler for h in logger.handlers):
            logger.addHandler(_log_handler)
        logger.setLevel(logging.INFO)
    logging.getLogger("spawnpoint.startup").info("SpawnPoint webui startup - log capture enabled")
    
    yield  # Server is running
    
    # Shutdown: cleanup if needed
    pass

app = FastAPI(lifespan=lifespan)

# --- InMemoryLogHandler and logging setup ---
# Resolve directories first
_base = Path(__file__).resolve().parent

# Simplified: use the webui subdirectories directly (they exist in the repo)
templates_dir = _base / "templates"
logging.getLogger("uvicorn").info("Using templates directory: %s", templates_dir)

# Initialize templates with resolved directory
templates = Jinja2Templates(directory=str(templates_dir))

# Resolve static directory (simplified)
static_dir = _base / "static"
logging.getLogger("uvicorn").info("Mounting static directory: %s at /static", static_dir)

# --- Now mount static files (after app is created) ---
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# --- servers.json persistence and install locking --- 
_base_project = Path(__file__).resolve().parent.parent  # c:\Projects\SpawnPoint
_SERVERS_FILE = _base_project / "SteamCMD" / "servers.json"
_SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)

# simple in-process lock so only one steam/install operation runs at a time
_install_lock = asyncio.Lock()

def _read_servers_file():
    try:
        if not _SERVERS_FILE.exists():
            return []
        with _SERVERS_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logging.getLogger("spawnpoint").exception("Failed to read servers file: %s", e)
        return []

def _write_servers_file(servers):
    try:
        with _SERVERS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(servers, fh, indent=2)
    except Exception:
        logging.getLogger("spawnpoint").exception("Failed to write servers file")

def _find_server(servers, appId):
    for s in servers:
        if str(s.get("appId")) == str(appId):
            return s
    return None

async def _run_steamcmd_install(appId: str, install_dir: Path):
    """
    Run steamcmd in background to install the app.
    This function is async and will release the install lock when finished.
    """
    logger = logging.getLogger("spawnpoint.steamcmd")
    try:
        install_dir.mkdir(parents=True, exist_ok=True)

        # Example steamcmd command, adjust as needed for your environment.
        # This uses anonymous login and sets the install directory.
        # On Windows you might need to point to steamcmd.exe path.
        cmd = [
            "steamcmd",
            "+login", "anonymous",
            "+force_install_dir", str(install_dir),
            "+app_update", str(appId), "validate",
            "+quit"
        ]

        logger.info("Starting steamcmd install: %s", " ".join(cmd))

        # spawn the process and stream output to the logger
        proc = await asp.create_subprocess_exec(
            *cmd,
            stdout=asp.PIPE,
            stderr=asp.STDOUT
        )

        # read lines as they arrive
        if proc.stdout:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="ignore").rstrip()
                logger.info("[steamcmd %s] %s", appId, text)

        rc = await proc.wait()
        if rc == 0:
            logger.info("steamcmd finished successfully for app %s", appId)
            # update servers.json with a new entry (or update existing)
            servers = _read_servers_file()
            existing = _find_server(servers, appId)
            if not existing:
                entry = {
                    "appId": str(appId),
                    "name": f"App {appId}",
                    "status": "stopped",
                    "port": None,
                    "installPath": str(install_dir),
                    "settingsFile": None,
                    "version": None,
                    "updateAvailable": False,
                    "ip": ""
                }
                servers.append(entry)
                _write_servers_file(servers)
            else:
                existing["installPath"] = str(install_dir)
                _write_servers_file(servers)
        else:
            logger.error("steamcmd exited with code %s for app %s", rc, appId)
    except Exception as ex:
        logging.getLogger("spawnpoint.steamcmd").exception("Error while installing app %s: %s", appId, ex)
    finally:
        # release the lock so future installs can start
        try:
            _install_lock.release()
        except RuntimeError:
            # lock wasn't acquired or already released; ignore
            pass

# --- Routes and other handlers ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the `index.html` template."""
    # must pass request into template so request.url_for is available
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/uvicorn/logs", response_class=PlainTextResponse)
async def uvicorn_logs():
    """Return recent collected logs as plain text for the in-page terminal to poll."""
    return PlainTextResponse(_log_handler.get_logs(), media_type="text/plain")


# --- API endpoints for servers management ---
@app.get("/api/servers")
async def api_list_servers():
    servers = _read_servers_file()
    # If there are no persisted servers yet, return a single testing card so the UI can render.
    if not servers:
        sample_install = str(_base_project / "games" / "app_111111")
        test_server = {
            "appId": "111111",
            "name": "Test Game ",
            "status": "stopped",
            "port": 40444,
            "installPath": sample_install,
            "settingsFile": None,
            "version": "1.0.0",
            "updateAvailable": False,
            "ip": "127.0.0.1"
        }
        return JSONResponse([test_server])
    return JSONResponse(servers)

@app.post("/api/servers/add")
async def api_add_server(payload: dict):
    """
    Start installing a server via steamcmd. Returns immediately once the install task is queued.
    Only one install can run at a time (install lock).
    """
    appId = str(payload.get("appId") or payload.get("appid") or payload.get("id") or "")
    if not appId:
        raise HTTPException(status_code=400, detail={"error": "appId is required"})

    if _install_lock.locked():
        raise HTTPException(status_code=409, detail={"error": "Another install is currently running"})

    # acquire the lock before launching the installer task
    await _install_lock.acquire()

    # decide install dir (simple heuristic; adjust per your environment)
    install_dir = _base_project / "games" / f"app_{appId}"
    # schedule background task
    asyncio.create_task(_run_steamcmd_install(appId, install_dir))

    return JSONResponse({"status": "started", "appId": appId, "installPath": str(install_dir)})

@app.get("/api/servers/{appId}/settings-files")
async def api_settings_files(appId: str):
    """
    Detect potential settings files (e.g., *.ini) under the server install directory.
    Returns a JSON: { files: [...], installPath: "..." }
    """
    servers = _read_servers_file()
    server = _find_server(servers, appId)
    candidate_dirs = []

    if server and server.get("installPath"):
        candidate_dirs.append(Path(server["installPath"]))
    # common fallback locations (project-local)
    candidate_dirs.append(_base_project / "games" / f"app_{appId}")
    candidate_dirs.append(_base_project / "games" / f"{appId}")
    # user's home "games" (linux-ish)
    candidate_dirs.append(Path.home() / "games" / f"{appId}")
    candidate_dirs.append(Path("/home/steam/games") / f"{appId}")

    found_files = []
    found_path = None
    for d in candidate_dirs:
        try:
            if d and d.exists() and d.is_dir():
                # look recursively for ini files (shallow recursion)
                for p in d.rglob("*.ini"):
                    found_files.append(str(p.relative_to(d)) if p.is_file() else str(p))
                found_path = str(d)
                break
        except Exception:
            continue

    if not found_files and not found_path:
        return JSONResponse({"files": [], "installPath": None})

    return JSONResponse({"files": found_files, "installPath": found_path})

@app.post("/api/servers/{appId}/{action}")
async def api_control_server(appId: str, action: str):
    """
    Control server lifecycle (start/stop). This minimal implementation only updates the
    stored status in servers.json. Replace with actual process management as needed.
    """
    if action not in ("start", "stop"):
        raise HTTPException(status_code=400, detail={"error": "action must be 'start' or 'stop'"})

    servers = _read_servers_file()
    server = _find_server(servers, appId)
    if not server:
        raise HTTPException(status_code=404, detail={"error": "server not found"})

    # naive state toggle
    if action == "start":
        if server.get("status") == "running":
            return JSONResponse({"status": "already running"})
        server["status"] = "running"
    else:
        if server.get("status") != "running":
            return JSONResponse({"status": "already stopped"})
        server["status"] = "stopped"

    _write_servers_file(servers)
    return JSONResponse({"status": server["status"]})

@app.put("/api/servers/{appId}")
async def api_update_server(appId: str, payload: dict):
    """
    Update server meta: port, settingsFile, etc.
    """
    servers = _read_servers_file()
    server = _find_server(servers, appId)
    if not server:
        raise HTTPException(status_code=404, detail={"error": "server not found"})

    port = payload.get("port")
    settings_file = payload.get("settingsFile")
    install_path = payload.get("installPath")

    if port:
        server["port"] = int(port)
    if settings_file is not None:
        server["settingsFile"] = settings_file
    if install_path:
        server["installPath"] = install_path

    _write_servers_file(servers)
    return JSONResponse({"status": "ok", "server": server})

@app.get("/api/servers/{appId}/version")
async def api_server_version(appId: str):
    """
    Return simple version info. This is a placeholder; replace with a real check if needed.
    """
    servers = _read_servers_file()
    server = _find_server(servers, appId)
    if not server:
        raise HTTPException(status_code=404, detail={"error": "server not found"})

    # placeholder values; implement real version detection if desired
    current = server.get("version") or "unknown"
    latest = server.get("version") or "unknown"
    update_available = False

    return JSONResponse({"current": current, "latest": latest, "updateAvailable": update_available})

# attach handler to uvicorn and root loggers
logging.getLogger().addHandler(_log_handler)
logging.getLogger("uvicorn").addHandler(_log_handler)
logging.getLogger("uvicorn.error").addHandler(_log_handler)
logging.getLogger("uvicorn.access").addHandler(_log_handler)

if __name__ == "__main__":
    import uvicorn

    # Run with uvicorn (ASGI). Port 8000 is conventional for uvicorn.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")