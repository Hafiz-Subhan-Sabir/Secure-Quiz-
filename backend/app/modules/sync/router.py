"""Idempotent integrity event ingest — batch-optimized."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db, require_roles
from app.db.models import ExamSession, IntegrityEvent
from app.modules.schemas import EventBatch, SyncResult

router = APIRouter(prefix="/sync", tags=["sync"])

ALLOWED_TYPES = frozenset(
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


@router.post("/events", response_model=SyncResult, status_code=status.HTTP_202_ACCEPTED)
def sync_events(
    body: EventBatch,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_roles("student", "admin")),
) -> SyncResult:
    session = db.get(ExamSession, body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.student_id != claims["sub"] and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    rejected = 0
    candidates: list[dict] = []
    seen_ids: set[str] = set()
    has_submit = False

    for event in body.events:
        if event.type not in ALLOWED_TYPES:
            rejected += 1
            continue
        if event.event_id in seen_ids:
            continue
        seen_ids.add(event.event_id)
        if event.type == "submit":
            has_submit = True
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "session_id": body.session_id,
                "event_id": event.event_id,
                "type": event.type,
                "ts": event.ts,
                "severity": event.severity,
                "payload_json": json.dumps(event.payload, separators=(",", ":")),
            }
        )

    if not candidates:
        return SyncResult(accepted=0, duplicates=0, rejected=rejected)

    existing = set(
        db.scalars(
            select(IntegrityEvent.event_id).where(
                IntegrityEvent.session_id == body.session_id,
                IntegrityEvent.event_id.in_([c["event_id"] for c in candidates]),
            )
        ).all()
    )
    duplicates = len(existing)
    to_insert = [c for c in candidates if c["event_id"] not in existing]

    if to_insert:
        # Fast path: SQLite upsert-ignore in one round-trip when available
        if get_settings().database_url.startswith("sqlite"):
            stmt = sqlite_insert(IntegrityEvent).values(to_insert)
            stmt = stmt.on_conflict_do_nothing(index_elements=["session_id", "event_id"])
            db.execute(stmt)
        else:
            db.bulk_insert_mappings(IntegrityEvent, to_insert)

    if has_submit:
        session.status = "submitted"

    # Peak risk hint for heartbeat dashboards
    if to_insert:
        peak = max(c["severity"] for c in to_insert)
        if peak > session.last_risk_score:
            session.last_risk_score = peak

    db.commit()
    return SyncResult(accepted=len(to_insert), duplicates=duplicates, rejected=rejected)
