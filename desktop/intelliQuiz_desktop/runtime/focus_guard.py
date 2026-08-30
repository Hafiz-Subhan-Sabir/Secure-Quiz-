"""Detect when the student leaves the exam window during an active session."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FocusState:
    active: bool = False
    focused: bool = True
    foreground_process: str = ""
    away_since: float = 0.0
    away_events: int = 0
    allowed_pids: set[int] = field(default_factory=set)


class FocusGuard:
    """Windows foreground monitor — flags when another app steals focus."""

    def __init__(
        self,
        *,
        interval_sec: float = 1.0,
        away_threshold_sec: float = 3.0,
        on_away: Callable[[str], None] | None = None,
        on_return: Callable[[], None] | None = None,
    ) -> None:
        self.interval_sec = interval_sec
        self.away_threshold_sec = away_threshold_sec
        self.on_away = on_away
        self.on_return = on_return
        self.state = FocusState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._was_away = False

    def set_allowed_pids(self, pids: set[int]) -> None:
        with self._lock:
            self.state.allowed_pids = {p for p in pids if p > 0}

    def start(self) -> None:
        if sys.platform != "win32":
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        with self._lock:
            self.state.active = True
            self.state.focused = True
            self.state.away_since = 0.0
        self._was_away = False
        self._thread = threading.Thread(target=self._loop, name="focus-guard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            self.state.active = False

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": self.state.active,
                "focused": self.state.focused,
                "foreground_process": self.state.foreground_process,
                "away_events": self.state.away_events,
            }

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_sec):
            try:
                self._tick()
            except Exception:
                continue

    def _tick(self) -> None:
        pid, name = _foreground_process()
        now = time.time()
        with self._lock:
            allowed = set(self.state.allowed_pids)
            self.state.foreground_process = name

        allowed_names = {
            "python",
            "pythonw",
            "py",
            "msedge",
            "chrome",
            "intelliquiz-desktop",
            "intelliquizdesktop",
            "explorer",
            "searchhost",
            "shellexperiencehost",
            "applicationframehost",
            "systemsettings",
            "textinputhost",
            "dwm",
            "csrss",
            "winlogon",
        }
        focused = pid in allowed or name in allowed_names or name.startswith("msedge") or name.startswith("chrome")

        if focused:
            if self._was_away and self.on_return:
                self.on_return()
            self._was_away = False
            with self._lock:
                self.state.focused = True
                self.state.away_since = 0.0
            return

        with self._lock:
            if self.state.away_since <= 0:
                self.state.away_since = now
            away_for = now - self.state.away_since
            self.state.focused = False
            if away_for >= self.away_threshold_sec and not self._was_away:
                self.state.away_events += 1
                self._was_away = True
                if self.on_away:
                    self.on_away(name or "unknown")


def _foreground_process() -> tuple[int, str]:
    if sys.platform != "win32":
        return 0, ""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0, ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_pid = int(pid.value)
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {proc_pid}", "/FO", "CSV", "/NH"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        line = out.strip().splitlines()[0] if out.strip() else ""
        parts = [p.strip().strip('"') for p in line.split(",")]
        name = parts[0].lower().removesuffix(".exe") if parts else ""
        return proc_pid, name
    except Exception:
        return 0, ""
