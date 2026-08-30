from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PKG = Path(__file__).resolve().parents[1]  # intelliQuiz_desktop/
_REPO = Path(__file__).resolve().parents[3]  # Intelligence Quiz/


class DesktopSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IQ_DESKTOP_", extra="ignore")

    api_base_url: str = "http://127.0.0.1:8080/api/v1"
    api_verify_ssl: bool = False
    api_ca_cert: Path | None = None
    data_dir: Path = Path.home() / ".intelliquiz" / "desktop"
    model_path: Path = _REPO / "ml" / "artifacts" / "models" / "best_model.joblib"
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
    gesture_capture_threshold: float = 0.5
    capture_cooldown_sec: float = 6.0
    # Kill chat/remote tools during exam. Browsers are flagged but not killed
    # while the exam UI runs in a browser (production would use kiosk WebView).
    app_lock_kill: bool = True
    app_lock_kill_browsers: bool = False
    exam_kiosk_mode: bool = True
    identity_match_threshold: float = 0.88
    focus_loss_pause_sec: float = 3.0
    camera_index: int = 0


@lru_cache
def get_settings() -> DesktopSettings:
    settings = DesktopSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "evidence").mkdir(parents=True, exist_ok=True)
    return settings
