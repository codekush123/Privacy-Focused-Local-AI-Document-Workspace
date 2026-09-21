"""Health, llama-server status, privacy and llama-server launcher endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.api import LlmStatus
from app.services.llm.client import llm_client
from app.services.llm.launcher import LauncherError, LauncherSettings, LauncherStatus, launcher
from app.services.privacy.policy import PrivacyStatus, is_localhost_url, privacy_status

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "Local AI Document Workspace", "local_only": settings.local_only}


@router.get("/llm/status", response_model=LlmStatus)
async def llm_status() -> LlmStatus:
    allowed = (not settings.local_only) or is_localhost_url(settings.llm_base_url)
    if not allowed:
        return LlmStatus(
            connected=False,
            endpoint=settings.llm_base_url,
            max_output_tokens=settings.max_output_tokens,
            safety_reserve=settings.context_safety_reserve,
            ai_requests_allowed=False,
            error="LOCAL ONLY mode: the configured LLM endpoint is not localhost, so AI requests are blocked.",
        )
    info = await llm_client.server_info()
    allowed_prompt = None
    if info.context_size:
        allowed_prompt = max(info.context_size - settings.max_output_tokens - settings.context_safety_reserve, 0)
    return LlmStatus(
        connected=info.reachable,
        endpoint=info.endpoint,
        model_name=info.model_name,
        model_path=info.model_path,
        context_size=info.context_size if info.reachable else None,
        train_context_size=info.train_context_size,
        max_output_tokens=settings.max_output_tokens,
        safety_reserve=settings.context_safety_reserve,
        allowed_prompt_tokens=allowed_prompt if info.reachable else None,
        total_slots=info.total_slots,
        build_info=info.build_info,
        error=info.error if not info.reachable else info.error,
        ai_requests_allowed=True,
    )


@router.get("/privacy", response_model=PrivacyStatus)
async def privacy() -> PrivacyStatus:
    return privacy_status()


# ------------------------------------------------------------- launcher ---

@router.get("/llm/launcher", response_model=LauncherStatus)
async def launcher_status() -> LauncherStatus:
    return launcher.status()


@router.put("/llm/launcher/settings", response_model=LauncherStatus)
async def launcher_update(body: LauncherSettings) -> LauncherStatus:
    launcher.update_settings(body)
    return launcher.status()


@router.post("/llm/launcher/validate")
async def launcher_validate(body: LauncherSettings) -> dict:
    problems = launcher.validate_paths(body)
    return {"ok": not problems, "problems": problems, "command": launcher.build_command(body) if not problems else []}


@router.post("/llm/launcher/start", response_model=LauncherStatus)
async def launcher_start(body: LauncherSettings | None = None) -> LauncherStatus:
    try:
        return launcher.start(body)
    except LauncherError as exc:
        raise HTTPException(400, detail={"error": str(exc), "log_tail": launcher.log_tail()}) from exc


@router.post("/llm/launcher/stop", response_model=LauncherStatus)
async def launcher_stop() -> LauncherStatus:
    try:
        return launcher.stop()
    except LauncherError as exc:
        raise HTTPException(400, str(exc)) from exc
