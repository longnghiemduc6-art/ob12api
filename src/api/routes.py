"""OpenAI-compatible API routes — proxies to OB-1 backend."""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..core.auth import verify_api_key
from ..core.logger import get_logger
from ..core.models import ChatCompletionRequest
from ..services.ob1_client import OB1Client
from ..services.token_manager import OB1TokenManager

log = get_logger("routes")

router = APIRouter()

_token_manager: OB1TokenManager = None
_ob1_client: OB1Client = None


def init(token_manager: OB1TokenManager, ob1_client: OB1Client):
    global _token_manager, _ob1_client
    _token_manager = token_manager
    _ob1_client = ob1_client


@router.get("/v1/models")
async def list_models(_: str = Depends(verify_api_key)):
    api_key = await _token_manager.get_api_key()
    if not api_key:
        return {"object": "list", "data": []}
    raw = await _ob1_client.fetch_models(api_key)
    models = []
    for m in raw:
        models.append({
            "id": m["id"],
            "object": "model",
            "created": m.get("created", 0),
            "owned_by": m["id"].split("/")[0] if "/" in m["id"] else "ob1",
            "name": m.get("name", m["id"]),
        })
    return {"object": "list", "data": models}


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    _: str = Depends(verify_api_key),
):
    api_key = await _token_manager.get_api_key()
    if not api_key:
        log.warning("No valid OB-1 token available")
        return JSONResponse(status_code=503, content={"error": "No valid OB-1 token. Run ob1 auth to login."})

    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    log.info("Chat request: model=%s stream=%s messages=%d", request.model, request.stream, len(messages))

    try:
        resp = await _ob1_client.chat(
            api_key=api_key,
            messages=messages,
            model=request.model,
            stream=request.stream,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        log.error("Backend error: %s", e)
        return JSONResponse(status_code=502, content={"error": f"Backend error: {e}"})

    if resp.status_code == 401:
        await resp.aclose()
        log.warning("Token rejected (401), refreshing...")
        ok = await _token_manager.refresh()
        if not ok:
            log.error("Token refresh failed")
            return JSONResponse(status_code=401, content={"error": "Token expired and refresh failed"})
        api_key = await _token_manager.get_api_key()
        try:
            resp = await _ob1_client.chat(
                api_key=api_key,
                messages=messages,
                model=request.model,
                stream=request.stream,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
            )
        except Exception as e:
            log.error("Backend error after refresh: %s", e)
            return JSONResponse(status_code=502, content={"error": f"Backend error: {e}"})

    if resp.status_code != 200:
        try:
            body = (await resp.aread()).decode()
        except Exception:
            body = "unable to read response body"
        await resp.aclose()
        log.error("OB-1 returned %d: %s", resp.status_code, body[:200])
        return JSONResponse(
            status_code=resp.status_code,
            content={"error": f"OB-1 returned {resp.status_code}: {body[:500]}"},
        )

    if request.stream:
        log.debug("Streaming response started")
        return StreamingResponse(
            _proxy_stream(resp, _token_manager),
            media_type="text/event-stream",
        )
    else:
        data = resp.json()
        usage = data.get("usage", {})
        _track_usage(usage)
        log.info("Chat response: model=%s prompt_tokens=%d completion_tokens=%d",
                 data.get("model", "?"), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return JSONResponse(content=data)


def _track_usage(usage: dict):
    """Extract token counts from usage and record cost."""
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    if pt or ct:
        # Rough OpenRouter-style cost estimate (per 1M tokens)
        cost = pt * 0.000015 + ct * 0.000075
        _token_manager.add_cost(cost)
    elif usage:
        _token_manager.add_cost(0)


async def _proxy_stream(resp, tm) -> None:
    """Proxy SSE stream from OB-1 backend directly to client."""
    try:
        async for line in resp.aiter_lines():
            if line:
                yield f"{line}\n\n"
                # Extract usage from the final chunk
                if line.startswith("data: ") and '"usage"' in line:
                    try:
                        chunk = json.loads(line[6:])
                        usage = chunk.get("usage") or {}
                        if usage:
                            _track_usage(usage)
                    except Exception:
                        pass
    finally:
        await resp.aclose()
