"""API key + JWT verification."""
import time
import secrets

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..services.api_key_manager import ApiKeyManager
from ..core import config

_security = HTTPBearer()
_key_manager: ApiKeyManager = None
_JWT_SECRET = secrets.token_hex(32)
_JWT_EXPIRE = 86400 * 7  # 7 days


def init_auth(key_manager: ApiKeyManager):
    global _key_manager
    _key_manager = key_manager


def create_login_token(username: str) -> str:
    payload = {"sub": username, "exp": int(time.time()) + _JWT_EXPIRE}
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")


def verify_login(username: str, password: str) -> bool:
    return username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> str:
    token = credentials.credentials
    # Try JWT first
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
        if payload.get("exp", 0) > time.time():
            return token
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        pass
    # Fallback to API key
    if _key_manager and _key_manager.validate(token):
        return token
    raise HTTPException(status_code=401, detail="Invalid token")
