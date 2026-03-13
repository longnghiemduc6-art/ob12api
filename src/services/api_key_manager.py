"""API key manager — multi-key support with CRUD."""
from __future__ import annotations

import json
import os
import secrets
import time

from ..core.logger import get_logger

log = get_logger("api-keys")


def _keys_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "config", "api_keys.json")


class ApiKey:
    def __init__(self, data: dict):
        self.key: str = data["key"]
        self.name: str = data.get("name", "")
        self.created_at: float = data.get("created_at", 0)
        self.last_used: float = data.get("last_used", 0)
        self.requests: int = data.get("requests", 0)
        self.enabled: bool = data.get("enabled", True)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "requests": self.requests,
            "enabled": self.enabled,
        }

    def to_public(self) -> dict:
        k = self.key
        masked = k[:7] + "..." + k[-4:] if len(k) > 12 else k
        return {
            "key": masked,
            "full_key": self.key,
            "name": self.name,
            "created_at": int(self.created_at * 1000),
            "last_used": int(self.last_used * 1000) if self.last_used else 0,
            "requests": self.requests,
            "enabled": self.enabled,
        }


class ApiKeyManager:
    def __init__(self):
        self._keys: list[ApiKey] = []
        self._path = _keys_path()
        self._dirty = False

    def load(self, default_key: str = ""):
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._keys = [ApiKey(k) for k in data]
        if not self._keys and default_key:
            self._keys.append(ApiKey({
                "key": default_key,
                "name": "默认密钥",
                "created_at": time.time(),
            }))
            self._save()
        log.info("Loaded %d keys", len(self._keys))

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([k.to_dict() for k in self._keys], f, indent=2)

    def validate(self, key: str) -> bool:
        for k in self._keys:
            if k.key == key and k.enabled:
                k.last_used = time.time()
                k.requests += 1
                self._dirty = True
                return True
        return False

    def flush(self):
        """Persist pending changes to disk."""
        if self._dirty:
            self._save()
            self._dirty = False

    def list_keys(self) -> list[dict]:
        return [k.to_public() for k in self._keys]

    def create_key(self, name: str = "") -> dict:
        key = "sk-" + secrets.token_hex(24)
        ak = ApiKey({
            "key": key,
            "name": name or f"Key-{len(self._keys) + 1}",
            "created_at": time.time(),
        })
        self._keys.append(ak)
        self._save()
        return ak.to_public()

    def create_key_with_value(self, key: str, name: str = "") -> dict:
        """Create a key with a specific value (for syncing from settings)."""
        for k in self._keys:
            if k.key == key:
                return k.to_public()
        ak = ApiKey({
            "key": key,
            "name": name or f"Key-{len(self._keys) + 1}",
            "created_at": time.time(),
        })
        self._keys.append(ak)
        self._save()
        return ak.to_public()

    def delete_key(self, key: str) -> bool:
        for i, k in enumerate(self._keys):
            if k.key == key:
                self._keys.pop(i)
                self._save()
                return True
        return False

    def toggle_key(self, key: str) -> bool:
        for k in self._keys:
            if k.key == key:
                k.enabled = not k.enabled
                self._save()
                return True
        return False
