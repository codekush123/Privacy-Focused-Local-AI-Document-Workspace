"""Application configuration.

All values can be overridden with environment variables prefixed with ``LDW_``
(Local Document Workspace), e.g. ``LDW_LLM_BASE_URL=http://127.0.0.1:8081``.
A ``.env`` file in the backend directory is also read if present.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LDW_", env_file=BACKEND_DIR / ".env", extra="ignore")

    # --- llama-server -------------------------------------------------------
    llm_base_url: str = "http://127.0.0.1:8080"
    llm_timeout_seconds: float = 600.0
    llm_health_timeout_seconds: float = 3.0

    # --- context budget -----------------------------------------------------
    # Tokens reserved for the model's answer. Kept modest on purpose: on a CPU
    # machine every reserved token is time, and it also shrinks the prompt budget.
    max_output_tokens: int = 1024
    # Extra safety margin (template tokens, BOS/EOS, rounding).
    context_safety_reserve: int = 1024
    # Fallback context size used only if llama-server does not report one.
    fallback_context_size: int = 8192
    # Default sampling temperature for chat.
    chat_temperature: float = 0.3
    # Lower temperature for structured (JSON) generation.
    structured_temperature: float = 0.2

    # --- privacy --------------------------------------------------------------
    # When true, the LLM endpoint must resolve to localhost.
    local_only: bool = True

    # --- storage --------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    url_fetch_timeout_seconds: float = 15.0
    url_max_bytes: int = 5 * 1024 * 1024  # 5 MB

    # --- CSV preview ----------------------------------------------------------
    csv_preview_rows: int = 200

    # --- vision ---------------------------------------------------------------
    # Images smaller than this (in either dimension) are ignored as decoration.
    vision_min_image_px: int = 120
    # Longest edge of an image sent to the vision model. 512 px roughly halves
    # the image tokens (and the time) versus 1024 px with no loss of reading
    # accuracy on charts in local testing.
    vision_max_image_px: int = 512
    # Hard cap on images extracted per document.
    vision_max_images_per_doc: int = 60

    # --- server ---------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def converted_dir(self) -> Path:
        return self.data_dir / "converted"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    def ensure_dirs(self) -> None:
        for d in (self.uploads_dir, self.converted_dir, self.exports_dir, self.images_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
