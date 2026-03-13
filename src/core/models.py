"""Pydantic models for OB1 2API."""
from __future__ import annotations
from typing import List, Optional, Union
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: Union[str, list]


class ChatCompletionRequest(BaseModel):
    model: str = "anthropic/claude-opus-4.6"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
