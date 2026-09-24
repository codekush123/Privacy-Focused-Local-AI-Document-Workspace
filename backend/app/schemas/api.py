"""Request / response models for the REST API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    detail: dict[str, Any] | None = None
    suggestions: list[str] = Field(default_factory=list)


class LlmStatus(BaseModel):
    connected: bool
    endpoint: str
    model_name: str | None = None
    model_path: str | None = None
    context_size: int | None = None
    train_context_size: int | None = None
    max_output_tokens: int
    safety_reserve: int
    allowed_prompt_tokens: int | None = None
    total_slots: int | None = None
    build_info: str | None = None
    supports_vision: bool = False
    prompt_tokens_per_second: float | None = None
    generated_tokens_per_second: float | None = None
    speed_warning: str | None = None
    error: str | None = None
    ai_requests_allowed: bool = True


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    document_ids: list[str] = Field(default_factory=list)
    strategy: Literal["full", "retrieval", "auto"] | None = None
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    stream: bool = True
    max_output_tokens: int | None = Field(default=None, ge=16, le=32768)


class ContextCheckRequest(BaseModel):
    prompt: str = ""
    document_ids: list[str] = Field(default_factory=list)
    history: list[ChatMessage] = Field(default_factory=list)
    strategy: Literal["full", "retrieval", "auto"] | None = None


class TextImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000_000)
    name: str | None = None


class UrlImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    document_ids: list[str] = Field(default_factory=list)
    filename: str | None = None


class SaveTextRequest(BaseModel):
    text: str = Field(min_length=1)
    kind: Literal["md", "txt", "docx", "pdf", "tex"] = "md"
    filename: str | None = None
    title: str | None = Field(default=None, max_length=200)
    prompt: str = ""
    document_ids: list[str] = Field(default_factory=list)
