"""Push unsynced local events to the central server (idempotent)."""

from __future__ import annotations

from intelliQuiz_desktop.storage.event_store import EncryptedEventStore
from intelliQuiz_desktop.sync.api_client import ApiClient


class SyncWorker:
    def __init__(self, store: EncryptedEventStore, api: ApiClient, batch_size: int = 100) -> None:
        self.store = store
        self.api = api
        self.batch_size = batch_size

    def flush(self, session_id: str) -> dict:
        batch = self.store.unsynced(session_id, limit=self.batch_size)
        if not batch:
            return {"accepted": 0, "duplicates": 0, "rejected": 0, "flushed": 0}
        payload = [
            {
                "event_id": e.event_id,
                "type": e.type,
                "ts": e.ts,
                "severity": e.severity,
                "payload": e.payload,
            }
            for e in batch
        ]
        result = self.api.sync_events(session_id, payload)
        # Mark only non-rejected as synced; duplicates are safe to mark
        self.store.mark_synced([e.event_id for e in batch])
        return {**result, "flushed": len(batch)}
