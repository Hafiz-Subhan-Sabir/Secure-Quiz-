"""Push unsynced local events to the central server (idempotent)."""

from __future__ import annotations

import time

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
        "heartbeat",
        "submit",
    }
)


class SyncWorker:
    def __init__(self, store: EncryptedEventStore, api: ApiClient, batch_size: int = 100) -> None:
        self.store = store
        self.api = api
        self.batch_size = batch_size
        self.max_retries = 3

    def flush(self, session_id: str) -> dict:
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
                    time.sleep(0.5 * (2**attempt))
        return {
            "accepted": 0,
            "duplicates": 0,
            "rejected": 0,
            "flushed": 0,
            "rejected_local": len(invalid_ids),
            "error": last_error or "sync failed",
        }
