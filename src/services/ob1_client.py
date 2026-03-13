"""OB-1 API client — proxies requests to dashboard.openblocklabs.com/api/v1."""
from __future__ import annotations

from typing import AsyncIterator, NamedTuple
import httpx

from ..core import config as _config
from ..core.config import OB1_API_BASE
from ..core.logger import get_logger

log = get_logger("client")

_HEADERS = {
    "HTTP-Referer": "https://github.com/delta-hq/ob1",
    "X-Title": "OB1 CLI",
}


class StreamResponse:
    """Wrapper that keeps httpx client alive during streaming."""
    def __init__(self, resp: httpx.Response, client: httpx.AsyncClient):
        self._resp = resp
        self._client = client

    def __getattr__(self, name):
        return getattr(self._resp, name)

    async def aclose(self):
        await self._resp.aclose()
        await self._client.aclose()


class OB1Client:
    """Async HTTP client to OBL OpenRouter-compatible API."""

    def __init__(self):
        self.base_url = OB1_API_BASE
        self._models_cache: list | None = None

    def _proxy(self) -> str | None:
        url = _config.PROXY_URL
        return url if url else None

    async def fetch_models(self, api_key: str) -> list:
        """Fetch available models from OB-1. Cached after first call."""
        if self._models_cache is not None:
            return self._models_cache
        try:
            log.debug("Fetching models from %s/models", self.base_url)
            async with httpx.AsyncClient(timeout=15, proxy=self._proxy()) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={**_HEADERS, "Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code == 200:
                self._models_cache = resp.json().get("data", [])
                log.info("Fetched %d models", len(self._models_cache))
                return self._models_cache
            log.warning("Models fetch returned %d", resp.status_code)
        except Exception as e:
            log.error("Models fetch failed: %s", e)
        return []

    async def chat(
        self,
        api_key: str,
        messages: list,
        model: str = "anthropic/claude-opus-4.6",
        stream: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> httpx.Response:
        """Send chat completion request. Returns raw httpx Response."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stream:
            payload["stream_options"] = {"include_usage": True}

        headers = {
            **_HEADERS,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        client = httpx.AsyncClient(timeout=300, proxy=self._proxy())
        try:
            if stream:
                log.debug("Sending stream request to %s model=%s", self.base_url, model)
                req = client.build_request(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp = await client.send(req, stream=True)
                return StreamResponse(resp, client)
            else:
                log.debug("Sending request to %s model=%s", self.base_url, model)
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                log.debug("Response status=%d", resp.status_code)
                await client.aclose()
                return resp
        except Exception as e:
            log.error("Request failed: %s", e)
            await client.aclose()
            raise
