"""App lock — detect and terminate exam-prohibited processes (Windows-focused)."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


# Messaging / remote-control / screen-share — always treated as hard violations.
HARD_BLACKLIST = {
    "discord",
    "teamviewer",
    "anydesk",
    "anydesk.exe",
    "zoom",
    "slack",
    "telegram",
    "whatsapp",
    "signal",
    "skype",
    "remotepc",
    "rustdesk",
    "vnc",
    "ultraviewer",
    "chrome_remote_desktop_host",
    "parsec",
    "toodesk",
    "sunloginclient",
}

# Notes / docs / AI helper apps — treated as hard violations during exams.
HELPER_BLACKLIST = {
    "notepad",
    "wordpad",
    "winword",
    "excel",
    "powerpnt",
    "onenote",
    "onenotem",
    "obs64",
    "obs32",
    "obs",
    "sharex",
    "lightshot",
    "snippingtool",
    "screenclip",
    "ms-screenclip",
    "calc",
    "chatgpt",
    "claude",
    "perplexity",
    "gemini",
    "copilot",
    "notion",
    "evernote",
    "teams",
    "ms-teams",
    "msteams",
    "cursor",
    "code",
    "devenv",
    "winrar",
    "7zfm",
}

# Browsers — flagged; killed when kill_browsers is enabled (exam kiosk window is whitelisted).
BROWSER_BLACKLIST = {
    "chrome",
    "msedge",
    "firefox",
    "brave",
    "opera",
    "iexplore",
}


@dataclass
class ProcessHit:
    name: str
    pid: int
    category: str  # "hard" | "browser"


@dataclass
class AppLockState:
    active: bool = False
    hits: list[ProcessHit] = field(default_factory=list)
    killed: list[str] = field(default_factory=list)
    last_scan_at: float = 0.0
    violations: int = 0


class AppLockController:
    """Continuous process scanner + selective terminator.

    Conceptual model:
    - HARD apps (chat/remote) break exam integrity → detect + kill when enabled.
    - Browsers are cheating channels for notes/AI → flag always; kill only if
      ``kill_browsers`` is True (kiosk / native shell). While the student UI
      itself runs in a browser, killing browsers would kill the exam client.
    """

    def __init__(
        self,
        *,
        kill: bool = True,
        kill_browsers: bool = False,
        interval_sec: float = 2.0,
        on_violation: Callable[[list[ProcessHit], list[str]], None] | None = None,
    ) -> None:
        self.kill = kill
        self.kill_browsers = kill_browsers
        self.interval_sec = interval_sec
        self.on_violation = on_violation
        self.state = AppLockState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._extra_hard: set[str] = set()
        self._extra_browser: set[str] = set()
        self._allowed_pids: set[int] = set()

    def set_allowed_pids(self, pids: set[int]) -> None:
        with self._lock:
            self._allowed_pids = {p for p in pids if p > 0}

    def apply_profile(self, *, blacklist_csv: str, strictness: str) -> None:
        """Merge server proctoring blacklist into the scanner."""
        names = {n.strip().lower().removesuffix(".exe") for n in blacklist_csv.split(",") if n.strip()}
        browser_names = names & BROWSER_BLACKLIST
        hard_names = names - browser_names
        with self._lock:
            self._extra_hard = hard_names
            self._extra_browser = browser_names
            if strictness in {"medium", "high", "lockdown"}:
                self.kill_browsers = True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        with self._lock:
            self.state.active = True
        self._thread = threading.Thread(target=self._loop, name="app-lock", daemon=True)
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
                "hits": [{"name": h.name, "pid": h.pid, "category": h.category} for h in self.state.hits],
                "killed": list(self.state.killed),
                "violations": self.state.violations,
                "kill_enabled": self.kill,
                "kill_browsers": self.kill_browsers,
            }

    def scan_once(self) -> list[ProcessHit]:
        with self._lock:
            extra_hard = set(self._extra_hard)
            extra_browser = set(self._extra_browser)
        return list_prohibited(include_browsers=True, extra_hard=extra_hard, extra_browser=extra_browser)

    def enforce_once(self) -> tuple[list[ProcessHit], list[str]]:
        hits = self.scan_once()
        killed: list[str] = []
        with self._lock:
            allowed = set(self._allowed_pids)
        if self.kill:
            for hit in hits:
                if hit.pid in allowed:
                    continue
                if hit.category == "browser" and not self.kill_browsers:
                    continue
                if _terminate(hit.pid):
                    killed.append(f"{hit.name}:{hit.pid}")
        with self._lock:
            self.state.hits = hits
            self.state.killed = killed
            self.state.last_scan_at = time.time()
            if hits:
                self.state.violations += 1
        if hits and self.on_violation:
            self.on_violation(hits, killed)
        return hits, killed

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_sec):
            try:
                self.enforce_once()
            except Exception:
                continue


def list_prohibited(
    *,
    include_browsers: bool = True,
    extra_hard: set[str] | None = None,
    extra_browser: set[str] | None = None,
) -> list[ProcessHit]:
    extra_hard = extra_hard or set()
    extra_browser = extra_browser or set()
    if sys.platform != "win32":
        return _list_posix(include_browsers=include_browsers, extra_hard=extra_hard, extra_browser=extra_browser)
    hits: list[ProcessHit] = []
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except Exception:
        return hits

    for line in out.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 2:
            continue
        exe = parts[0].lower().removesuffix(".exe")
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        if exe in HARD_BLACKLIST or exe.replace(" ", "") in HARD_BLACKLIST or exe in extra_hard or exe in HELPER_BLACKLIST:
            hits.append(ProcessHit(name=exe, pid=pid, category="hard"))
        elif include_browsers and (exe in BROWSER_BLACKLIST or exe in extra_browser):
            hits.append(ProcessHit(name=exe, pid=pid, category="browser"))
    return hits


def _list_posix(
    *,
    include_browsers: bool,
    extra_hard: set[str] | None = None,
    extra_browser: set[str] | None = None,
) -> list[ProcessHit]:
    extra_hard = extra_hard or set()
    extra_browser = extra_browser or set()
    hits: list[ProcessHit] = []
    try:
        out = subprocess.check_output(["ps", "-A", "-o", "pid=,comm="], text=True)
    except Exception:
        return hits
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        name = parts[1].lower().split("/")[-1]
        if name in HARD_BLACKLIST or name in extra_hard or name in HELPER_BLACKLIST:
            hits.append(ProcessHit(name=name, pid=pid, category="hard"))
        elif include_browsers and (name in BROWSER_BLACKLIST or name in extra_browser):
            hits.append(ProcessHit(name=name, pid=pid, category="browser"))
    return hits


def _terminate(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            subprocess.check_call(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        else:
            subprocess.check_call(["kill", "-9", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
