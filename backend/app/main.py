"""FastAPI application entry point.

Run with:  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, documents, features, generate, system
from app.services.privacy.policy import is_localhost_url
from app.utils.logging import setup_logging

setup_logging()
log = logging.getLogger("app")

app = FastAPI(
    title="Privacy-Focused Local AI Document Workspace",
    version="0.1.0-prototype",
    description="Local document import, full-context prompting against llama-server, and Office file generation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(generate.router)
app.include_router(features.router)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    """Uniform error shape: {"error": str, "suggestions": [...], "detail": {...}}."""
    if isinstance(exc.detail, dict):
        body = {"error": exc.detail.get("error", "Request failed."), **{k: v for k, v in exc.detail.items() if k != "error"}}
    else:
        body = {"error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(status_code=422, content={"error": f"Invalid request: {loc} {first.get('msg', '')}".strip()})


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": "An unexpected error occurred. See the backend log."})


@app.on_event("startup")
async def on_startup() -> None:
    settings.ensure_dirs()
    log.info("Data directory: %s", settings.data_dir)
    log.info("LLM endpoint: %s (local-only mode: %s)", settings.llm_base_url, settings.local_only)
    if settings.local_only and not is_localhost_url(settings.llm_base_url):
        log.warning("LOCAL ONLY mode is enabled but LDW_LLM_BASE_URL is not localhost. AI requests will be blocked.")
