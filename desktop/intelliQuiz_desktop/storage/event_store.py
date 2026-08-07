"""Encrypted local event store (SQLite + Fernet)."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class LocalEvent:
    event_id: str
    session_id: str
    type: str
    ts: str
    severity: float
    payload: dict
    synced: bool = False


class EncryptedEventStore:
    """Offline-first integrity log. Zero-loss: write before network sync."""

    def __init__(self, db_path: Path, key: bytes | None = None) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        key_path = db_path.with_suffix(".key")
        if key is None:
            if key_path.exists():
                key = key_path.read_bytes()
            else:
                key = Fernet.generate_key()
                key_path.write_bytes(key)
        self._fernet = Fernet(key)
        self._lock = threading.RLock()
        # check_same_thread=False: FastAPI serves requests on worker threads
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              event_id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              type TEXT NOT NULL,
              ts TEXT NOT NULL,
              severity REAL NOT NULL,
              payload_enc BLOB NOT NULL,
              synced INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_unsynced ON events(session_id, synced)"
        )
        self._conn.commit()

    def append(
        self,
        *,
        session_id: str,
        type: str,
        severity: float,
        payload: dict,
        event_id: str | None = None,
    ) -> LocalEvent:
        eid = event_id or str(uuid.uuid4())
        ts = datetime.now(UTC).isoformat()
        blob = self._fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode())
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(event_id, session_id, type, ts, severity, payload_enc, synced) VALUES (?,?,?,?,?,?,0)",
                (eid, session_id, type, ts, float(severity), blob),
            )
            self._conn.commit()
        return LocalEvent(eid, session_id, type, ts, float(severity), payload, False)

    def unsynced(self, session_id: str, limit: int = 100) -> list[LocalEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, session_id, type, ts, severity, payload_enc FROM events "
                "WHERE session_id=? AND synced=0 ORDER BY ts ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out: list[LocalEvent] = []
        for event_id, sid, typ, ts, severity, payload_enc in rows:
            payload = json.loads(self._fernet.decrypt(payload_enc).decode())
            out.append(LocalEvent(event_id, sid, typ, ts, severity, payload, False))
        return out

    def mark_synced(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE events SET synced=1 WHERE event_id=?",
                [(eid,) for eid in event_ids],
            )
            self._conn.commit()

    def delete_session(self, session_id: str) -> int:
        """Remove local encrypted events for a finished session (server copy stays)."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            self._conn.commit()
            return int(cur.rowcount or 0)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
