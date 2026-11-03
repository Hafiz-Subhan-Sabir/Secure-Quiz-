"""App lock — detect and terminate exam-prohibited processes (Windows-focused)."""

from __future__ import annotations

import json
import os
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

# Browsers — flagged only. Never force-killed while the exam UI itself runs in
# Edge/Chrome (killing sibling browser processes closes the quiz window).
BROWSER_BLACKLIST = {
    "chrome",
    "msedge",
    "firefox",
    "brave",
    "opera",
    "iexplore",
}

# Never terminate the exam runtime / its console host.
PROTECTED_NAMES = {
    "intelliquizdesktop",
    "intelliquiz-desktop",
    "uvicorn",
    "windowsterminal",
    "openconsole",
    "conhost",
    "powershell",
    "pwsh",
    "cmd",
}

# Optional lab protect list (enabled via IQ_DESKTOP_APP_LOCK_PROTECT_DEV=true).
DEV_PROTECT_NAMES = {
    "cursor",
    "code",
    "devenv",
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
    - HARD/HELPER apps (chat/remote/notes/IDE) → detect + kill when enabled.
    - Browsers → flag + capture evidence; kill only unprotected PIDs when
      ``kill_browsers`` is True (exam Edge/Chrome profile stays protected).
    """

    def __init__(
        self,
        *,
        kill: bool = True,
        kill_browsers: bool = False,
        interval_sec: float = 1.5,
        on_violation: Callable[[list[ProcessHit], list[str]], None] | None = None,
    ) -> None:
        self.kill = kill
        self.kill_browsers = bool(kill_browsers)
        self._want_kill_browsers = bool(kill_browsers)
        self.interval_sec = interval_sec
        self.on_violation = on_violation
        self.state = AppLockState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._extra_hard: set[str] = set()
        self._extra_browser: set[str] = set()
        self._allowed_pids: set[int] = set()
        self._allowed_roots: set[int] = set()
        self._protected_markers: set[str] = set()
        self._protect_dev_tools: bool = False
        self._last_kill_errors: list[str] = []

    def set_protect_dev_tools(self, enabled: bool) -> None:
        with self._lock:
            self._protect_dev_tools = bool(enabled)

    def set_allowed_pids(self, pids: set[int]) -> None:
        with self._lock:
            self._allowed_pids = {p for p in pids if p > 0}
            self._allowed_roots = {p for p in pids if p > 0}

    def set_protected_cmdline_markers(self, markers: set[str]) -> None:
        """Protect browser processes whose command line contains these substrings."""
        with self._lock:
            self._protected_markers = {m for m in markers if m}
            # Once exam profile is known, always kill other Chrome/Edge instances.
            if self._protected_markers:
                self.kill_browsers = True
                self._want_kill_browsers = True

    def apply_profile(self, *, blacklist_csv: str, strictness: str) -> None:
        """Merge server proctoring blacklist into the scanner."""
        names = {n.strip().lower().removesuffix(".exe") for n in blacklist_csv.split(",") if n.strip()}
        browser_names = names & BROWSER_BLACKLIST
        hard_names = names - browser_names
        with self._lock:
            self._extra_hard = hard_names
            self._extra_browser = browser_names
            # Always intend to kill non-exam browsers during any proctored exam.
            self._want_kill_browsers = True
            self.kill_browsers = bool(self._protected_markers)

    def force_clear_other_browsers(self) -> list[str]:
        """Immediately terminate Chrome/Edge PIDs that are not the exam profile."""
        with self._lock:
            self.kill_browsers = True
            self._want_kill_browsers = True
            protect_dev = self._protect_dev_tools
        hits = self.scan_once()
        killed: list[str] = []
        errors: list[str] = []
        protected = self._protected_pids()
        for hit in hits:
            if hit.category != "browser":
                continue
            if hit.pid in protected or hit.name in PROTECTED_NAMES:
                continue
            if protect_dev and hit.name in DEV_PROTECT_NAMES:
                continue
            ok, err = _terminate_with_reason(hit.pid)
            if ok:
                killed.append(f"{hit.name}:{hit.pid}")
            elif err:
                errors.append(f"{hit.name}:{hit.pid}:{err}")
        with self._lock:
            self._last_kill_errors = errors
        return killed

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
                "kill_errors": list(self._last_kill_errors),
                "violations": self.state.violations,
                "kill_enabled": self.kill,
                "kill_browsers": self.kill_browsers,
                "protect_dev_tools": self._protect_dev_tools,
            }

    def scan_once(self) -> list[ProcessHit]:
        with self._lock:
            extra_hard = set(self._extra_hard)
            extra_browser = set(self._extra_browser)
        return list_prohibited(include_browsers=True, extra_hard=extra_hard, extra_browser=extra_browser)

    def enforce_once(self) -> tuple[list[ProcessHit], list[str]]:
        hits = self.scan_once()
        killed: list[str] = []
        errors: list[str] = []
        protected = self._protected_pids()
        with self._lock:
            protect_dev = self._protect_dev_tools
        # Exam browser / runtime / protected PIDs are never violations.
        actionable = [
            h
            for h in hits
            if h.pid not in protected
            and h.name not in PROTECTED_NAMES
            and not (protect_dev and h.name in DEV_PROTECT_NAMES)
        ]
        if self.kill:
            for hit in actionable:
                if hit.category == "browser" and not self.kill_browsers:
                    continue
                ok, err = _terminate_with_reason(hit.pid)
                if ok:
                    killed.append(f"{hit.name}:{hit.pid}")
                elif err:
                    errors.append(f"{hit.name}:{hit.pid}:{err}")
        with self._lock:
            self.state.hits = actionable
            self.state.killed = killed
            self._last_kill_errors = errors
            self.state.last_scan_at = time.time()
            if actionable:
                self.state.violations += 1
        if actionable and self.on_violation:
            self.on_violation(actionable, killed)
        return actionable, killed

    def _protected_pids(self) -> set[int]:
        with self._lock:
            roots = set(self._allowed_roots)
            seeds = set(self._allowed_pids)
            markers = set(self._protected_markers)
        protected = set(seeds)
        protected |= _process_tree(roots)
        if markers:
            protected |= _pids_matching_cmdline(markers)
        protected.add(os.getpid())
        return protected

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
        if exe in PROTECTED_NAMES:
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
        if name in PROTECTED_NAMES:
            continue
        if name in HARD_BLACKLIST or name in extra_hard or name in HELPER_BLACKLIST:
            hits.append(ProcessHit(name=name, pid=pid, category="hard"))
        elif include_browsers and (name in BROWSER_BLACKLIST or name in extra_browser):
            hits.append(ProcessHit(name=name, pid=pid, category="browser"))
    return hits


def _process_tree(roots: set[int]) -> set[int]:
    """Expand parent PIDs to include all descendants (Edge/Chrome multi-process)."""
    if not roots:
        return set()
    children_map = _parent_child_map()
    out = set(roots)
    stack = list(roots)
    while stack:
        parent = stack.pop()
        for child in children_map.get(parent, ()):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def _cim_processes() -> list[dict]:
    """Enumerate processes via PowerShell CIM (WMIC is removed on many Win11 installs)."""
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            timeout=8,
        )
    except Exception:
        return []
    out = (out or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []


def _parent_child_map() -> dict[int, list[int]]:
    mapping: dict[int, list[int]] = {}
    for row in _cim_processes():
        try:
            pid = int(row.get("ProcessId") or 0)
            ppid = int(row.get("ParentProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        mapping.setdefault(ppid, []).append(pid)
    return mapping


def _pids_matching_cmdline(markers: set[str]) -> set[int]:
    """Find PIDs whose command line contains any protected marker (exam profile dir)."""
    if not markers or sys.platform != "win32":
        return set()
    markers_l = [m.lower().replace("/", "\\") for m in markers]
    matched: set[int] = set()
    for row in _cim_processes():
        cmd = str(row.get("CommandLine") or "").lower().replace("/", "\\")
        if not cmd or not any(m in cmd for m in markers_l):
            continue
        try:
            matched.add(int(row.get("ProcessId") or 0))
        except (TypeError, ValueError):
            continue
    return {p for p in matched if p > 0}


def _terminate(pid: int) -> bool:
    ok, _ = _terminate_with_reason(pid)
    return ok


def _terminate_with_reason(pid: int) -> tuple[bool, str]:
    if pid <= 0:
        return False, "invalid_pid"
    try:
        if sys.platform == "win32":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                check=False,
            )
            if completed.returncode == 0:
                return True, ""
            detail = (completed.stderr or completed.stdout or "").strip() or f"exit_{completed.returncode}"
            low = detail.lower()
            if "access is denied" in low or "not allowed" in low:
                return False, "access_denied_needs_elevation"
            if "not found" in low:
                return True, ""  # already gone
            return False, detail[:120]
        subprocess.check_call(["kill", "-9", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, ""
    except Exception as exc:
        return False, str(exc)[:120]
