"""Push unsynced local events to the central server (idempotent).

Runs as a dedicated background thread so exam UI / webcam loops never block
on network I/O.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from intelliQuiz_desktop.storage.event_store import EncryptedEventStore
from intelliQuiz_desktop.sync.api_client import ApiClient

ALLOWED_SYNC_TYPES = frozenset(
    {
        "gesture_risk",
        "gaze_away",
        "multi_face",
        "no_face",
        "app_violation",
        "android_env_anomaly",
        "android_snapshot",
        "heartbeat",
        "submit",
    }
)


class SyncWorker:
    def __init__(self, store: EncryptedEventStore, api: ApiClient, batch_size: int = 100) -> None:
        self.store = store
        self.api = api
        self.batch_size = batch_size
        self.max_retries = 6
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._active_session: str = ""
        self._last_result: dict[str, Any] = {"accepted": 0, "flushed": 0}

    def start(self, session_id: str | None = None) -> None:
        if session_id:
            with self._lock:
                self._active_session = session_id
        if self._thread and self._thread.is_alive():
            self._wake.set()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="iq-sync-loop", daemon=True)
        self._thread.start()

    def stop(self, *, wait: bool = False) -> None:
        self._stop.set()
        self._wake.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._thread = None

    def request_flush(self, session_id: str | None = None) -> None:
        if session_id:
            with self._lock:
                self._active_session = session_id
        self.start()
        self._wake.set()

    def last_result(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_result)

    def flush(self, session_id: str) -> dict[str, Any]:
        """Synchronous flush (used by smoke tests / final submit)."""
        with self._lock:
            self._active_session = session_id
        result = self._flush_once(session_id)
        with self._lock:
            self._last_result = dict(result)
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                sid = self._active_session
            if sid:
                try:
                    result = self._flush_once(sid)
                    with self._lock:
                        self._last_result = dict(result)
                except Exception as exc:
                    with self._lock:
                        self._last_result = {"accepted": 0, "flushed": 0, "error": str(exc)}
            # Idle wait — wake early on request_flush / stop.
            self._wake.wait(timeout=2.5)
            self._wake.clear()

    def _flush_once(self, session_id: str) -> dict[str, Any]:
        batch = self.store.unsynced(session_id, limit=self.batch_size)
        if not batch:
            return {"accepted": 0, "duplicates": 0, "rejected": 0, "flushed": 0}

        valid = [e for e in batch if e.type in ALLOWED_SYNC_TYPES]
        invalid_ids = [e.event_id for e in batch if e.type not in ALLOWED_SYNC_TYPES]
        if invalid_ids:
            self.store.mark_synced(invalid_ids)

        if not valid:
            return {"accepted": 0, "duplicates": 0, "rejected": len(invalid_ids), "flushed": 0}

        payload = [
            {
                "event_id": e.event_id,
                "type": e.type,
                "ts": e.ts,
                "severity": e.severity,
                "payload": e.payload,
            }
            for e in valid
        ]

        last_error: str | None = None
        for attempt in range(self.max_retries):
            try:
                result = self.api.sync_events(session_id, payload)
                self.store.mark_synced([e.event_id for e in valid])
                return {**result, "flushed": len(valid), "rejected_local": len(invalid_ids)}
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_retries - 1:
                    time.sleep(0.4 * (2**attempt))
        return {
            "accepted": 0,
            "duplicates": 0,
            "rejected": 0,
            "flushed": 0,
            "rejected_local": len(invalid_ids),
            "error": last_error or "sync failed",
        }
