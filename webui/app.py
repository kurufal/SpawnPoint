from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import logging
from collections import deque

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
_candidates_templates = [
    _base / "templates",            # webui/templates
    _base / "app" / "templates",    # webui/app/templates (your current layout)
    _base.parent / "templates",     # project-root/templates
]
templates_dir = next((p for p in _candidates_templates if p.exists()), _base / "templates")
logging.getLogger("uvicorn").info("Using templates directory: %s", templates_dir)

# Initialize templates with resolved directory
templates = Jinja2Templates(directory=str(templates_dir))

# Resolve static directory
_candidates_static = [
    _base / "static",               # webui/static
    _base / "app" / "static",       # webui/app/static (your current layout)
    _base.parent / "static",        # project-root/static
]
static_dir = next((p for p in _candidates_static if p.exists()), _base / "static")
logging.getLogger("uvicorn").info("Mounting static directory: %s at /static", static_dir)

# --- Now mount static files (after app is created) ---
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

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


# attach handler to uvicorn and root loggers
logging.getLogger().addHandler(_log_handler)
logging.getLogger("uvicorn").addHandler(_log_handler)
logging.getLogger("uvicorn.error").addHandler(_log_handler)
logging.getLogger("uvicorn.access").addHandler(_log_handler)

if __name__ == "__main__":
    import uvicorn

    # Run with uvicorn (ASGI). Port 8000 is conventional for uvicorn.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")