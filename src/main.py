"""OB1 2API — FastAPI application."""
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .api import routes, admin
from .services.token_manager import OB1TokenManager
from .services.ob1_client import OB1Client
from .services.api_key_manager import ApiKeyManager
from .core.auth import init_auth
from .core.config import API_KEY
from .core import config as _config
from .core.logger import setup_logging, get_logger

setup_logging()
log = get_logger("main")

app = FastAPI(title="OB1 2API", version="1.0.0")

# Auto-refresh task handle
_auto_refresh_task: asyncio.Task | None = None

# Static files
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=os.path.abspath(_static_dir)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services
token_manager = OB1TokenManager()
ob1_client = OB1Client()
api_key_manager = ApiKeyManager()

# Init auth with key manager
init_auth(api_key_manager)

# Inject dependencies
routes.init(token_manager, ob1_client)
admin.init(token_manager, api_key_manager)

# Register routers
app.include_router(routes.router)
app.include_router(admin.login_router)
app.include_router(admin.router)


@app.on_event("startup")
async def startup():
    api_key_manager.load(default_key=API_KEY)
    token_manager.load()
    if token_manager.is_loaded:
        api_key = await token_manager.get_api_key()
        log.info("OB1 2API started — user=%s token=%s", token_manager.user_email, "valid" if api_key else "needs refresh")
    else:
        log.info("OB1 2API started (no credentials loaded)")
    # Periodic flush for api key stats
    asyncio.create_task(_periodic_flush())
    # Start auto-refresh if configured
    restart_auto_refresh()


async def _periodic_flush():
    while True:
        await asyncio.sleep(60)
        api_key_manager.flush()


async def _auto_refresh_loop(interval: int):
    """Periodically refresh all account tokens."""
    while True:
        await asyncio.sleep(interval * 60)
        log.info("Auto-refreshing all accounts (interval=%dm)", interval)
        await token_manager.refresh()


def restart_auto_refresh():
    """(Re)start the auto-refresh task based on current config."""
    global _auto_refresh_task
    if _auto_refresh_task and not _auto_refresh_task.done():
        _auto_refresh_task.cancel()
        _auto_refresh_task = None
    _config.reload()
    interval = _config.OB1_REFRESH_INTERVAL
    if interval and interval > 0:
        _auto_refresh_task = asyncio.create_task(_auto_refresh_loop(interval))
        log.info("Auto-refresh enabled: every %d minutes", interval)
    else:
        log.info("Auto-refresh disabled")


@app.on_event("shutdown")
async def shutdown():
    api_key_manager.flush()


@app.get("/")
async def root():
    return RedirectResponse("/static/login.html")
