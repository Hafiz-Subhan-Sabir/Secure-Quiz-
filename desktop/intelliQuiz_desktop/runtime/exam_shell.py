"""Launch a dedicated exam browser window (app/kiosk mode) so other browsers can be blocked."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


def default_exam_profile_dir() -> Path:
    return Path.home() / ".intelliquiz" / "desktop" / "exam-browser-profile"


@dataclass
class ExamShell:
    process: subprocess.Popen | None = None
    pid: int = 0
    browser: str = ""
    profile_dir: Path = field(default_factory=default_exam_profile_dir)
    was_launched: bool = False

    def launch(self, url: str, *, kiosk: bool = True, profile_dir: Path | None = None) -> bool:
        self.close()
        if profile_dir is not None:
            self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        marker = str(self.profile_dir.resolve())

        for label, exe, builder in _browser_candidates():
            args = builder(exe, url, kiosk=kiosk, profile_dir=marker)
            try:
                creationflags = 0
                if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                    creationflags = subprocess.CREATE_NO_WINDOW
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                self.process = proc
                self.pid = int(proc.pid or 0)
                self.browser = label
                self.was_launched = True
                return True
            except Exception:
                continue
        return False

    def living_pids(self) -> set[int]:
        """PIDs still running the exam browser profile (Edge/Chrome often reparent)."""
        pids: set[int] = set()
        if self.process is not None and self.process.poll() is None and self.pid:
            pids.add(int(self.pid))
        try:
            from intelliQuiz_desktop.runtime.app_lock import _pids_matching_cmdline

            marker = str(self.profile_dir.resolve())
            pids |= _pids_matching_cmdline({marker})
        except Exception:
            pass
        if pids and not self.pid:
            self.pid = next(iter(pids))
        elif pids and self.pid not in pids:
            self.pid = next(iter(pids))
        return pids

    def is_alive(self) -> bool:
        return bool(self.living_pids())

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
        # Keep was_launched so lockdown does not open a fresh login window.


def _edge(exe: str, url: str, *, kiosk: bool, profile_dir: str) -> list[str]:
    args = [
        exe,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--app={url}",
    ]
    if kiosk:
        args.insert(1, "--edge-kiosk-type=fullscreen")
    else:
        args.append("--new-window")
    return args


def _chrome(exe: str, url: str, *, kiosk: bool, profile_dir: str) -> list[str]:
    args = [
        exe,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--app={url}",
    ]
    if kiosk:
        args[1:1] = ["--kiosk", "--disable-pinch"]
    else:
        args.append("--new-window")
    return args


def _browser_candidates() -> list[tuple[str, str, Callable[..., list[str]]]]:
    """Return (label, exe_path, arg_builder) for installed Edge/Chrome."""
    found: list[tuple[str, str, Callable[..., list[str]]]] = []
    seen: set[str] = set()

    def add(label: str, path: str | None, builder: Callable[..., list[str]]) -> None:
        if not path:
            return
        resolved = str(Path(path).resolve()) if Path(path).exists() else ""
        if not resolved or resolved.lower() in seen:
            return
        seen.add(resolved.lower())
        found.append((label, resolved, builder))

    for name, builder in (("msedge", _edge), ("chrome", _chrome), ("google-chrome", _chrome)):
        add(name, shutil.which(name), builder)

    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        win_paths: list[tuple[str, str, Callable[..., list[str]]]] = [
            ("msedge", rf"{pf86}\Microsoft\Edge\Application\msedge.exe", _edge),
            ("msedge", rf"{pf}\Microsoft\Edge\Application\msedge.exe", _edge),
            ("chrome", rf"{pf}\Google\Chrome\Application\chrome.exe", _chrome),
            ("chrome", rf"{pf86}\Google\Chrome\Application\chrome.exe", _chrome),
        ]
        if local:
            win_paths.extend(
                [
                    ("msedge", rf"{local}\Microsoft\Edge\Application\msedge.exe", _edge),
                    ("chrome", rf"{local}\Google\Chrome\Application\chrome.exe", _chrome),
                ]
            )
        for label, path, builder in win_paths:
            add(label, path, builder)

    return found
