"""OB-1 multi-account token manager."""
from __future__ import annotations

import json
import os
import random
import time
import httpx

from ..core.config import (
    OB1_WORKOS_AUTH_URL,
    OB1_WORKOS_CLIENT_ID,
    OB1_REFRESH_BUFFER,
    OB1_API_BASE,
)
from ..core import config as _config
from ..core.logger import get_logger

log = get_logger("token")

DEVICE_AUTH_URL = "https://api.workos.com/user_management/authorize/device"
ORG_API_URL = f"{OB1_API_BASE}/auth/organizations"


def _accounts_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "config", "accounts.json")


class Account:
    def __init__(self, data: dict):
        self.email: str = data.get("email", "")
        self.access_token: str = data.get("access_token", "")
        self.refresh_token: str = data.get("refresh_token", "")
        self.expires_at: float = data.get("expires_at", 0)
        self.org_id: str = data.get("org_id", "")
        self.org_name: str = data.get("org_name", "")
        self.user_id: str = data.get("user_id", "")
        self.user_data: dict = data.get("user_data", {})

    @property
    def active(self) -> bool:
        return bool(self.access_token) and self.expires_at > time.time()

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "org_id": self.org_id,
            "org_name": self.org_name,
            "user_id": self.user_id,
            "user_data": self.user_data,
        }

    @staticmethod
    def _mask(token: str) -> str:
        if not token:
            return ""
        if len(token) <= 8:
            return token[:2] + "..." + token[-2:]
        return token[:4] + "..." + token[-4:]

    def to_public(self) -> dict:
        return {
            "email": self.email,
            "org_id": self.org_id,
            "org_name": self.org_name,
            "at_mask": self._mask(self.access_token),
            "rt_mask": self._mask(self.refresh_token),
            "active": self.active,
            "expires_at": int(self.expires_at * 1000),
        }


class OB1TokenManager:
    """Manages multiple OB-1 accounts with round-robin and auto-refresh."""

    def __init__(self):
        self._accounts: list[Account] = []
        self._current_idx: int = 0
        self._path = _accounts_path()
        self._request_count: int = 0
        self._cost_today: float = 0

    def load(self):
        # Load from accounts.json
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._accounts = [Account(a) for a in data]
            log.info("Loaded %d accounts", len(self._accounts))
        # Also import from ~/.ob1/credentials.json if accounts.json is empty
        if not self._accounts:
            cred_path = os.path.join(os.path.expanduser("~"), ".ob1", "credentials.json")
            if os.path.exists(cred_path):
                self._import_credentials(cred_path)

    def _import_credentials(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        oauth = data.get("oauth", {})
        if not oauth.get("access_token"):
            return
        user = oauth.get("user", {})
        acct = Account({
            "email": user.get("email", ""),
            "access_token": oauth.get("access_token", ""),
            "refresh_token": oauth.get("refresh_token", ""),
            "expires_at": oauth.get("expires_at", 0) / 1000,
            "org_id": oauth.get("organization_id", ""),
            "user_id": user.get("id", ""),
            "user_data": user,
        })
        self._accounts.append(acct)
        self._save()
        log.info("Imported %s from credentials.json", acct.email)

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([a.to_dict() for a in self._accounts], f, indent=2)

    @property
    def is_loaded(self) -> bool:
        return len(self._accounts) > 0

    @property
    def user_email(self) -> str:
        if self._accounts:
            return self._accounts[0].email
        return ""

    @property
    def org_id(self) -> str:
        if self._accounts:
            return self._accounts[0].org_id
        return ""

    def list_accounts(self) -> list[dict]:
        return [a.to_public() for a in self._accounts]

    @property
    def current_idx(self) -> int:
        return self._current_idx

    @property
    def stats(self) -> dict:
        active = sum(1 for a in self._accounts if a.active)
        return {
            "total": len(self._accounts),
            "active": active,
            "cost": self._cost_today,
            "requests": self._request_count,
        }

    def add_cost(self, cost: float):
        self._cost_today += cost
        self._request_count += 1

    async def refresh_account(self, idx: int, force: bool = False) -> bool:
        if idx < 0 or idx >= len(self._accounts):
            return False
        acct = self._accounts[idx]
        if not acct.refresh_token:
            return False
        # Skip if token still valid (not within buffer), unless forced
        if not force and acct.expires_at - time.time() > OB1_REFRESH_BUFFER:
            log.debug("Skipping refresh for %s, token still valid (%.0fh remaining)",
                      acct.email, (acct.expires_at - time.time()) / 3600)
            return True
        try:
            proxy = _config.PROXY_URL or None
            async with httpx.AsyncClient(proxy=proxy, timeout=30) as client:
                resp = await client.post(
                    OB1_WORKOS_AUTH_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": acct.refresh_token,
                        "client_id": OB1_WORKOS_CLIENT_ID,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                log.warning("Refresh failed for %s: %d %s", acct.email, resp.status_code, resp.text)
                return False
            result = resp.json()
            acct.access_token = result["access_token"]
            acct.refresh_token = result.get("refresh_token", acct.refresh_token)
            acct.expires_at = time.time() + result.get("expires_in", 3600)
            self._save()
            log.info("Refreshed %s", acct.email)
            return True
        except Exception as e:
            log.error("Refresh error for %s: %s", acct.email, e)
            return False

    def remove_account(self, idx: int) -> bool:
        if idx < 0 or idx >= len(self._accounts):
            return False
        removed = self._accounts.pop(idx)
        self._save()
        log.info("Removed %s", removed.email)
        return True

    async def add_account_from_device(self, auth_result: dict) -> str:
        """Add account from device auth result. Returns email."""
        user = auth_result.get("user", {})
        at = auth_result["access_token"]
        rt = auth_result["refresh_token"]
        expires_in = auth_result.get("expires_in", 3600)
        user_id = user.get("id", "")
        email = user.get("email", "")

        # Fetch org
        org_id = ""
        org_name = ""
        try:
            proxy = _config.PROXY_URL or None
            async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
                resp = await client.get(
                    f"{ORG_API_URL}?user_id={user_id}",
                    headers={"Authorization": f"Bearer {at}"},
                )
            if resp.status_code == 200:
                orgs = resp.json().get("data", [])
                if orgs:
                    org_id = orgs[0].get("organizationId", "")
                    org_name = orgs[0].get("organizationName", "")
        except Exception as e:
            log.error("Org fetch error: %s", e)

        # Check duplicate
        for a in self._accounts:
            if a.email == email:
                a.access_token = at
                a.refresh_token = rt
                a.expires_at = time.time() + expires_in
                a.org_id = org_id or a.org_id
                a.org_name = org_name or a.org_name
                self._save()
                return email

        acct = Account({
            "email": email,
            "access_token": at,
            "refresh_token": rt,
            "expires_at": time.time() + expires_in,
            "org_id": org_id,
            "org_name": org_name,
            "user_id": user_id,
            "user_data": user,
        })
        self._accounts.append(acct)
        self._save()
        log.info("Added account %s (org: %s)", email, org_name)
        return email

    async def get_api_key(self) -> str | None:
        """Get a valid API key based on rotation mode."""
        if not self._accounts:
            return None
        n = len(self._accounts)
        mode = _config.OB1_ROTATION_MODE

        if mode == "performance":
            order = random.sample(range(n), n)
        elif mode == "cache-first":
            # 优先使用上次成功的账号
            order = [self._current_idx] + [i for i in range(n) if i != self._current_idx]
        else:  # balanced (default) — 轮流使用
            order = [(self._current_idx + i) % n for i in range(n)]
            self._current_idx = (self._current_idx + 1) % n

        for idx in order:
            acct = self._accounts[idx]
            if acct.expires_at - time.time() < OB1_REFRESH_BUFFER:
                await self.refresh_account(idx)
            if acct.active:
                if acct.org_id:
                    return f"{acct.access_token}:{acct.org_id}"
                return acct.access_token
        return None

    async def refresh(self) -> bool:
        """Refresh all accounts."""
        ok = False
        for i in range(len(self._accounts)):
            if await self.refresh_account(i):
                ok = True
        return ok

    def import_accounts(self, data: list[dict]) -> int:
        """Import accounts from a list of dicts, skip duplicates by email."""
        existing = {a.email for a in self._accounts}
        count = 0
        for d in data:
            if d.get("email") and d["email"] not in existing:
                self._accounts.append(Account(d))
                existing.add(d["email"])
                count += 1
        if count:
            self._save()
        return count

    def batch_remove(self, indices: list[int]) -> int:
        """Remove accounts by indices (descending to keep order)."""
        removed = 0
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self._accounts):
                self._accounts.pop(i)
                removed += 1
        if removed:
            self._save()
        return removed
