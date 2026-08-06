"""Selective application control — re-exports runtime app lock."""

from __future__ import annotations

from intelliQuiz_desktop.runtime.app_lock import (
    BROWSER_BLACKLIST,
    HARD_BLACKLIST,
    AppLockController,
    ProcessHit,
    list_prohibited,
)

# Backward-compatible alias used by older smoke helpers
DEFAULT_BLACKLIST = HARD_BLACKLIST | BROWSER_BLACKLIST


def list_blacklisted(blacklist: set[str] | None = None) -> list[ProcessHit]:
    hits = list_prohibited(include_browsers=True)
    if blacklist is None:
        return hits
    names = {n.lower() for n in blacklist}
    return [h for h in hits if h.name in names]


__all__ = [
    "AppLockController",
    "BROWSER_BLACKLIST",
    "DEFAULT_BLACKLIST",
    "HARD_BLACKLIST",
    "ProcessHit",
    "list_blacklisted",
    "list_prohibited",
]
