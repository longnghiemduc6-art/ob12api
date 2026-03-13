"""Admin routes — login, accounts, device auth, settings, keys."""
from __future__ import annotations

import json
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.auth import verify_api_key, verify_login, create_login_token
from ..core import config
from ..core.config import update_setting
from ..core.logger import get_logger, set_level
from ..services.token_manager import OB1TokenManager, DEVICE_AUTH_URL, OB1_WORKOS_AUTH_URL
from ..services.api_key_manager import ApiKeyManager

log = get_logger("admin")

router = APIRouter(prefix="/admin")
# Public login route (no auth)
login_router = APIRouter()

_tm: OB1TokenManager = None
_km: ApiKeyManager = None


def init(token_manager: OB1TokenManager, key_manager: ApiKeyManager):
    global _tm, _km
    _tm = token_manager
    _km = key_manager


# ===== Login (public) =====

class LoginRequest(BaseModel):
    username: str
    password: str


@login_router.post("/api/login")
async def login(req: LoginRequest):
    if verify_login(req.username, req.password):
        token = create_login_token(req.username)
        return {"success": True, "token": token}
    return JSONResponse(status_code=401, content={"success": False, "message": "用户名或密码错误"})


# ===== Protected routes =====
_auth = [Depends(verify_api_key)]


@router.get("/status", dependencies=_auth)
async def status():
    return {"loaded": _tm.is_loaded, "user": _tm.user_email, "org": _tm.org_id, "current_idx": _tm.current_idx, **_tm.stats}


# ===== Accounts =====

@router.get("/accounts", dependencies=_auth)
async def list_accounts():
    return {"accounts": _tm.list_accounts(), "stats": _tm.stats}


@router.post("/accounts/{idx}/refresh", dependencies=_auth)
async def refresh_account(idx: int):
    ok = await _tm.refresh_account(idx)
    return {"ok": ok, "error": "" if ok else "refresh failed"}


@router.delete("/accounts/{idx}", dependencies=_auth)
async def remove_account(idx: int):
    ok = _tm.remove_account(idx)
    return {"ok": ok}


@router.post("/refresh", dependencies=_auth)
async def force_refresh():
    ok = await _tm.refresh()
    return {"ok": ok}


@router.post("/accounts/export", dependencies=_auth)
async def export_accounts():
    return {"accounts": [a.to_dict() for a in _tm._accounts]}


class ImportRequest(BaseModel):
    accounts: list[dict]


@router.post("/accounts/import", dependencies=_auth)
async def import_accounts(req: ImportRequest):
    count = _tm.import_accounts(req.accounts)
    return {"ok": True, "imported": count}


class BatchDeleteRequest(BaseModel):
    indices: list[int]


@router.post("/accounts/batch-delete", dependencies=_auth)
async def batch_delete_accounts(req: BatchDeleteRequest):
    removed = _tm.batch_remove(req.indices)
    return {"ok": True, "removed": removed}


# ===== Device Auth =====

@router.post("/device-auth", dependencies=_auth)
async def start_device_auth():
    try:
        proxy = config.PROXY_URL or None
        async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
            resp = await client.post(
                DEVICE_AUTH_URL,
                data={"client_id": config.OB1_WORKOS_CLIENT_ID},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            return {"error": f"WorkOS returned {resp.status_code}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


class PollRequest(BaseModel):
    device_code: str


@router.post("/device-auth/poll", dependencies=_auth)
async def poll_device_auth(req: PollRequest):
    try:
        proxy = config.PROXY_URL or None
        async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
            resp = await client.post(
                OB1_WORKOS_AUTH_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": req.device_code,
                    "client_id": config.OB1_WORKOS_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
        if resp.status_code == 200:
            result = resp.json()
            email = await _tm.add_account_from_device(result)
            return {"status": "complete", "email": email}
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        error = body.get("error", "")
        if error == "authorization_pending":
            return {"status": "pending", "message": "等待用户授权..."}
        if error == "slow_down":
            return {"status": "pending", "message": "请稍候..."}
        if error == "expired_token":
            return {"status": "expired", "message": "授权已过期"}
        return {"status": "error", "message": body.get("error_description", error or f"HTTP {resp.status_code}")}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ===== API Keys =====

class CreateKeyRequest(BaseModel):
    name: str = ""


@router.get("/keys", dependencies=_auth)
async def list_keys():
    return {"keys": _km.list_keys()}


@router.post("/keys", dependencies=_auth)
async def create_key(req: CreateKeyRequest):
    key = _km.create_key(req.name)
    return {"ok": True, "key": key}


@router.delete("/keys/{key}", dependencies=_auth)
async def delete_key(key: str):
    ok = _km.delete_key(key)
    return {"ok": ok}


@router.post("/keys/{key}/toggle", dependencies=_auth)
async def toggle_key(key: str):
    ok = _km.toggle_key(key)
    return {"ok": ok}


# ===== Settings =====

@router.get("/settings", dependencies=_auth)
async def get_settings():
    return {
        "username": config.ADMIN_USERNAME,
        "api_key": _km._keys[0].key if _km and _km._keys else config.API_KEY,
        "proxy_url": config.PROXY_URL,
        "max_retries": config.MAX_RETRIES,
        "retry_delay": config.RETRY_DELAY,
        "rotation_mode": config.OB1_ROTATION_MODE,
        "refresh_interval": config.OB1_REFRESH_INTERVAL,
        "log_level": config.LOG_LEVEL,
    }


class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str


@router.post("/settings/password", dependencies=_auth)
async def update_password(req: PasswordUpdate):
    if req.old_password != config.ADMIN_PASSWORD:
        return JSONResponse(status_code=400, content={"ok": False, "message": "旧密码错误"})
    update_setting("admin", "password", req.new_password)
    return {"ok": True}


class UsernameUpdate(BaseModel):
    username: str


@router.post("/settings/username", dependencies=_auth)
async def update_username(req: UsernameUpdate):
    update_setting("admin", "username", req.username)
    return {"ok": True}


class ApiKeyUpdate(BaseModel):
    api_key: str


@router.post("/settings/api-key", dependencies=_auth)
async def update_api_key_setting(req: ApiKeyUpdate):
    old_key = config.API_KEY
    update_setting("global", "api_key", req.api_key)
    # Sync to ApiKeyManager so the new key is immediately usable
    if _km:
        _km.delete_key(old_key)
        _km.create_key_with_value(req.api_key, "默认密钥")
    return {"ok": True}


class ProxyUpdate(BaseModel):
    url: str = ""


@router.post("/settings/proxy", dependencies=_auth)
async def update_proxy(req: ProxyUpdate):
    update_setting("proxy", "url", req.url)
    return {"ok": True}


class ProxyTestRequest(BaseModel):
    url: str = ""


@router.post("/settings/proxy-test", dependencies=_auth)
async def test_proxy(req: ProxyTestRequest):
    proxy_url = req.url.strip()
    if not proxy_url:
        return {"ok": False, "error": "代理地址为空"}
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=10) as client:
            resp = await client.get("https://httpbin.org/ip")
        if resp.status_code == 200:
            ip = resp.json().get("origin", "unknown")
            return {"ok": True, "ip": ip}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class RetryUpdate(BaseModel):
    max_retries: int = 3
    retry_delay: int = 1


@router.post("/settings/retry", dependencies=_auth)
async def update_retry(req: RetryUpdate):
    update_setting("retry", "max_retries", req.max_retries)
    update_setting("retry", "retry_delay", req.retry_delay)
    return {"ok": True}


class RotationModeUpdate(BaseModel):
    mode: str


@router.post("/settings/rotation-mode", dependencies=_auth)
async def update_rotation_mode(req: RotationModeUpdate):
    if req.mode not in ("cache-first", "balanced", "performance"):
        return JSONResponse(status_code=400, content={"ok": False, "message": "无效的调度模式"})
    update_setting("ob1", "rotation_mode", req.mode)
    return {"ok": True}


class LogLevelUpdate(BaseModel):
    level: str


@router.post("/settings/log-level", dependencies=_auth)
async def update_log_level(req: LogLevelUpdate):
    lvl = req.level.upper()
    if lvl not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        return JSONResponse(status_code=400, content={"ok": False, "message": "无效的日志级别"})
    update_setting("logging", "level", lvl)
    set_level(lvl)
    return {"ok": True}


class RefreshIntervalUpdate(BaseModel):
    interval: int = 0


@router.post("/settings/refresh-interval", dependencies=_auth)
async def update_refresh_interval(req: RefreshIntervalUpdate):
    if req.interval < 0:
        return JSONResponse(status_code=400, content={"ok": False, "message": "刷新间隔不能为负数"})
    update_setting("ob1", "refresh_interval", req.interval)
    # Restart the periodic refresh task
    from ..main import restart_auto_refresh
    restart_auto_refresh()
    return {"ok": True}
