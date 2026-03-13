"""Config loader with hot-reload support."""
import os
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import tomli_w

_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "setting.toml")
)


def _load():
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _save(cfg: dict):
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


_cfg = _load()

API_KEY = _cfg["global"]["api_key"]
HOST = _cfg["server"]["host"]
PORT = _cfg["server"]["port"]

# Admin credentials
ADMIN_USERNAME = _cfg.get("admin", {}).get("username", "admin")
ADMIN_PASSWORD = _cfg.get("admin", {}).get("password", "admin")

# Proxy
PROXY_URL = _cfg.get("proxy", {}).get("url", "")

# Retry
MAX_RETRIES = _cfg.get("retry", {}).get("max_retries", 3)
RETRY_DELAY = _cfg.get("retry", {}).get("retry_delay", 1)

# OB-1 config
OB1_CREDENTIALS_PATH = _cfg["ob1"].get("credentials_path", "")
OB1_WORKOS_AUTH_URL = _cfg["ob1"]["workos_auth_url"]
OB1_WORKOS_CLIENT_ID = _cfg["ob1"]["workos_client_id"]
OB1_API_BASE = _cfg["ob1"]["api_base"]
OB1_REFRESH_BUFFER = _cfg["ob1"].get("refresh_buffer_seconds", 600)
OB1_ROTATION_MODE = _cfg["ob1"].get("rotation_mode", "cache-first")
OB1_REFRESH_INTERVAL = _cfg["ob1"].get("refresh_interval", 0)

# Logging
LOG_LEVEL = _cfg.get("logging", {}).get("level", "INFO")


def reload():
    """Reload config from disk into module-level variables."""
    global _cfg, API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD, PROXY_URL, MAX_RETRIES, RETRY_DELAY, OB1_ROTATION_MODE, OB1_REFRESH_INTERVAL, LOG_LEVEL
    _cfg = _load()
    API_KEY = _cfg["global"]["api_key"]
    ADMIN_USERNAME = _cfg.get("admin", {}).get("username", "admin")
    ADMIN_PASSWORD = _cfg.get("admin", {}).get("password", "admin")
    PROXY_URL = _cfg.get("proxy", {}).get("url", "")
    MAX_RETRIES = _cfg.get("retry", {}).get("max_retries", 3)
    RETRY_DELAY = _cfg.get("retry", {}).get("retry_delay", 1)
    OB1_ROTATION_MODE = _cfg["ob1"].get("rotation_mode", "cache-first")
    OB1_REFRESH_INTERVAL = _cfg["ob1"].get("refresh_interval", 0)
    LOG_LEVEL = _cfg.get("logging", {}).get("level", "INFO")


def update_setting(section: str, key: str, value):
    """Update a single setting, persist to disk, and reload."""
    cfg = _load()
    if section not in cfg:
        cfg[section] = {}
    cfg[section][key] = value
    _save(cfg)
    reload()
