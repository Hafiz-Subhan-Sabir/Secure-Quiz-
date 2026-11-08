from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _pkg_dir() -> Path:
    """Package dir (intelliQuiz_desktop/), including PyInstaller _MEIPASS."""
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent / "_internal"))
        return meipass / "intelliQuiz_desktop"
    return Path(__file__).resolve().parents[1]


def _resource_root() -> Path:
    """Repo root in dev; PyInstaller _MEIPASS when frozen (bundled ml/, etc.)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent / "_internal"))
    return Path(__file__).resolve().parents[3]


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def _env_files() -> tuple[str, ...]:
    """Prefer cwd/.env, then desktop/.env next to the package (dev), then EXE dir."""
    candidates = [
        _exe_dir() / ".env",
        Path(__file__).resolve().parents[2] / ".env",  # desktop/.env in repo
    ]
    found: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            found.append(str(path))
    # Always include cwd path last so pydantic can still look there if created later.
    if not found:
        found.append(str(_exe_dir() / ".env"))
    return tuple(found)


_PKG = _pkg_dir()
_ROOT = _resource_root()


class DesktopSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_prefix="IQ_DESKTOP_",
        extra="ignore",
    )

    api_base_url: str = "http://127.0.0.1:8080/api/v1"
    api_verify_ssl: bool = False
    api_ca_cert: Path | None = None
    data_dir: Path = Path.home() / ".intelliquiz" / "desktop"
    model_path: Path = _ROOT / "ml" / "artifacts" / "models" / "best_model.joblib"
    face_landmarker_path: Path = _PKG / "models" / "face_landmarker.task"
    # Bind 0.0.0.0 so phones on the LAN can open the mobile camera page.
    # The desktop browser still opens http://127.0.0.1:{port}/.
    local_ui_host: str = "0.0.0.0"
    local_ui_port: int = 8765
    # HTTPS port for phone camera (getUserMedia requires a secure context on phones).
    local_phone_https_port: int = 8767
    local_ws_host: str = "0.0.0.0"
    local_ws_port: int = 8766
    sync_batch_size: int = 100
    heartbeat_interval_sec: int = 15
    monitor_fps: float = 4.0
    gesture_capture_threshold: float = 0.4
    capture_cooldown_sec: float = 3.0
    # Kill chat/remote tools during exam. Non-exam browsers are killed when the
    # exam Edge/Chrome profile is protected; exam browser PIDs are never flagged.
    app_lock_kill: bool = True
    app_lock_kill_browsers: bool = True
    # When True, Cursor/VS Code/devenv are spared from app-lock kills (lab only).
    # Production exams must close those tools — keep False so Cursor is terminated
    # on continue/start. Override with IQ_DESKTOP_APP_LOCK_PROTECT_DEV=true for labs.
    app_lock_protect_dev: bool = False
    # Lab-only endpoints (/api/pairing/mark, /api/simulate-abnormal) — localhost only when False.
    allow_lab_bypasses: bool = False
    exam_kiosk_mode: bool = True
    # Always require a paired phone camera during exams (even if PC has a webcam).
    require_android_camera_always: bool = True
    identity_match_threshold: float = 0.88
    focus_loss_pause_sec: float = 3.0
    camera_index: int = 0
    build_sha: str = "dev"


@lru_cache
def get_settings() -> DesktopSettings:
    settings = DesktopSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "evidence").mkdir(parents=True, exist_ok=True)
    return settings
