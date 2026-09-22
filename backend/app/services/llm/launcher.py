"""Optional llama-server launcher.

The user enters the path to their own ``llama-server`` executable and GGUF
model in the UI. The paths are stored in ``data/llm_settings.json`` (never in
source code) so the project can be shared without machine-specific paths.

The backend then starts llama-server as a local child process bound to
127.0.0.1 on the port of ``LDW_LLM_BASE_URL``. A server started manually is
still detected and used as before - the launcher is a convenience, not a
requirement.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.config import settings

log = logging.getLogger(__name__)


class LauncherSettings(BaseModel):
    server_path: str = Field(default="", description="Full path to llama-server / llama-server.exe")
    model_path: str = Field(default="", description="Full path to a .gguf model file")
    mmproj_path: str = Field(default="", description="Optional multimodal projector (mmproj*.gguf) that enables image understanding")
    context_size: int = Field(default=16384, ge=512, le=1_048_576)
    threads: int = Field(default=0, ge=0, le=256, description="0 = let llama-server decide")
    gpu_layers: int = Field(default=0, ge=0, le=1000, description="Layers to offload to GPU (0 = CPU only)")
    extra_args: str = Field(default="", max_length=500, description="Additional llama-server flags")
    reasoning_budget_off: bool = Field(default=False, description="Add --reasoning-budget 0 (Qwen3 etc.)")


class LauncherStatus(BaseModel):
    settings: LauncherSettings
    running: bool
    managed: bool  # true when the process was started by this backend
    pid: int | None = None
    started_at: float | None = None
    host: str
    port: int
    log_tail: list[str] = Field(default_factory=list)
    last_error: str | None = None
    settings_file: str


class LauncherError(Exception):
    pass


def _endpoint_host_port() -> tuple[str, int]:
    parsed = urlparse(settings.llm_base_url)
    return parsed.hostname or "127.0.0.1", parsed.port or 8080


class LlamaServerLauncher:
    def __init__(self) -> None:
        settings.ensure_dirs()
        self._file = settings.data_dir / "llm_settings.json"
        self._log_file = settings.data_dir / "llama-server.log"
        self._settings = LauncherSettings()
        self._proc: subprocess.Popen | None = None
        self._pid: int | None = None
        self._started_at: float | None = None
        self._last_error: str | None = None
        self._lock = threading.Lock()
        self._load()

    # ------------------------------------------------------------ persist --
    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            self._settings = LauncherSettings.model_validate(raw.get("settings", {}))
            pid = raw.get("pid")
            if pid and _pid_alive(pid):
                # Reattach to a server we started before a backend restart.
                self._pid = pid
                self._started_at = raw.get("started_at")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read %s: %s", self._file, exc)

    def _save(self) -> None:
        self._file.write_text(
            json.dumps(
                {"settings": self._settings.model_dump(), "pid": self._pid, "started_at": self._started_at},
                indent=1,
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------ settings --
    @property
    def settings(self) -> LauncherSettings:
        return self._settings

    def update_settings(self, new: LauncherSettings) -> LauncherSettings:
        with self._lock:
            self._settings = new
            self._save()
        return self._settings

    # -------------------------------------------------------------- checks --
    @staticmethod
    def validate_paths(cfg: LauncherSettings) -> list[str]:
        problems: list[str] = []
        server = Path(cfg.server_path.strip().strip('"')) if cfg.server_path.strip() else None
        model = Path(cfg.model_path.strip().strip('"')) if cfg.model_path.strip() else None
        if server is None:
            problems.append("Enter the path to your llama-server executable.")
        elif not server.is_file():
            problems.append(f"llama-server executable not found: {server}")
        elif "llama-server" not in server.name.lower():
            problems.append(f"'{server.name}' does not look like a llama-server executable.")
        if model is None:
            problems.append("Enter the path to a .gguf model file.")
        elif not model.is_file():
            problems.append(f"Model file not found: {model}")
        elif model.suffix.lower() != ".gguf":
            problems.append(f"'{model.name}' is not a .gguf file.")
        if cfg.mmproj_path.strip():
            mm = Path(cfg.mmproj_path.strip().strip('"'))
            if not mm.is_file():
                problems.append(f"Projector file not found: {mm}")
            elif mm.suffix.lower() != ".gguf":
                problems.append(f"'{mm.name}' is not a .gguf projector file.")
        return problems

    def is_running(self) -> bool:
        if self._proc is not None:
            if self._proc.poll() is None:
                return True
            self._proc = None
            self._pid = None
        if self._pid is not None:
            if _pid_alive(self._pid):
                return True
            self._pid = None
        return False

    # -------------------------------------------------------------- start --
    def build_command(self, cfg: LauncherSettings) -> list[str]:
        host, port = _endpoint_host_port()
        cmd = [
            cfg.server_path.strip().strip('"'),
            "-m", cfg.model_path.strip().strip('"'),
            "-c", str(cfg.context_size),
            "--host", host,
            "--port", str(port),
            "--jinja",
        ]
        if cfg.mmproj_path.strip():
            cmd += ["--mmproj", cfg.mmproj_path.strip().strip('"')]
        if cfg.threads > 0:
            cmd += ["-t", str(cfg.threads)]
        cmd += ["-ngl", str(cfg.gpu_layers)]
        if cfg.reasoning_budget_off:
            cmd += ["--reasoning-budget", "0"]
        if cfg.extra_args.strip():
            cmd += cfg.extra_args.split()
        return cmd

    def start(self, cfg: LauncherSettings | None = None) -> LauncherStatus:
        with self._lock:
            if cfg is not None:
                self._settings = cfg
                self._save()
            cfg = self._settings
            if self.is_running():
                raise LauncherError("A llama-server started from this app is already running. Stop it first.")
            problems = self.validate_paths(cfg)
            if problems:
                raise LauncherError(" ".join(problems))
            host, _ = _endpoint_host_port()
            if settings.local_only and host not in ("127.0.0.1", "localhost", "::1"):
                raise LauncherError("LOCAL ONLY mode: the endpoint host must be localhost.")
            cmd = self.build_command(cfg)
            self._last_error = None
            try:
                log_fh = self._log_file.open("ab")
                log_fh.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {' '.join(cmd)}\n".encode())
                creation = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=str(Path(cfg.server_path.strip().strip('"')).parent),
                    creationflags=creation,
                )
            except OSError as exc:
                self._last_error = f"Could not start llama-server: {exc}"
                raise LauncherError(self._last_error) from exc
            self._pid = self._proc.pid
            self._started_at = time.time()
            self._save()
            log.info("Started llama-server pid %s (%s)", self._pid, Path(cfg.model_path).name)
        # Fail fast if the process dies immediately (bad model path, missing DLL ...)
        time.sleep(1.5)
        if not self.is_running():
            self._last_error = "llama-server exited immediately. See the log below."
            raise LauncherError(self._last_error)
        return self.status()

    # --------------------------------------------------------------- stop --
    def stop(self) -> LauncherStatus:
        with self._lock:
            if not self.is_running():
                raise LauncherError("No llama-server started from this app is running.")
            pid = self._pid
            try:
                if self._proc is not None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                elif pid is not None:
                    _kill_pid(pid)
            finally:
                self._proc = None
                self._pid = None
                self._started_at = None
                self._save()
            log.info("Stopped llama-server pid %s", pid)
        return self.status()

    # ------------------------------------------------------------- status --
    def log_tail(self, lines: int = 40) -> list[str]:
        if not self._log_file.exists():
            return []
        try:
            data = self._log_file.read_bytes()[-20000:].decode("utf-8", errors="replace")
            return data.splitlines()[-lines:]
        except OSError:
            return []

    def status(self) -> LauncherStatus:
        host, port = _endpoint_host_port()
        running = self.is_running()
        return LauncherStatus(
            settings=self._settings,
            running=running,
            managed=running,
            pid=self._pid if running else None,
            started_at=self._started_at if running else None,
            host=host,
            port=port,
            log_tail=self.log_tail(),
            last_error=self._last_error,
            settings_file=str(self._file),
        )


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=5
            ).stdout
            return str(pid) in out and "llama-server" in out.lower()
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        os.kill(pid, 15)


launcher = LlamaServerLauncher()

__all__: list[Any] = ["LauncherError", "LauncherSettings", "LauncherStatus", "launcher"]
