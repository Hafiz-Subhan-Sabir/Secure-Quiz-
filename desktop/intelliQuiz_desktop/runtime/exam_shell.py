"""Launch a dedicated exam browser window (app/kiosk mode) so other browsers can be blocked."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


@dataclass
class ExamShell:
    process: subprocess.Popen | None = None
    pid: int = 0
    browser: str = ""

    def launch(self, url: str, *, kiosk: bool = True) -> bool:
        self.close()
        for name, builder in _CANDIDATES:
            exe = shutil.which(name)
            if not exe:
                continue
            args = builder(exe, url, kiosk=kiosk)
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                self.process = proc
                self.pid = int(proc.pid or 0)
                self.browser = name
                return True
            except Exception:
                continue
        return False

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        self.process = None
        self.pid = 0
        self.browser = ""


def _edge(exe: str, url: str, *, kiosk: bool) -> list[str]:
    if kiosk:
        return [exe, f"--app={url}", "--edge-kiosk-type=fullscreen", "--no-first-run"]
    return [exe, f"--app={url}", "--new-window", "--no-first-run"]


def _chrome(exe: str, url: str, *, kiosk: bool) -> list[str]:
    if kiosk:
        return [exe, f"--app={url}", "--kiosk", "--no-first-run", "--disable-pinch"]
    return [exe, f"--app={url}", "--new-window", "--no-first-run"]


_CANDIDATES: list[tuple[str, Callable[..., list[str]]]] = [
    ("msedge", _edge),
    ("chrome", _chrome),
    ("google-chrome", _chrome),
]
