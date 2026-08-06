"""Integrity report assembly with facial-evidence frames."""

from __future__ import annotations

import json
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.db.models import Exam, ExamSession, IntegrityEvent, User
from app.modules.schemas import EvidenceFrame, IntegrityReport

router = APIRouter(prefix="/reports", tags=["reports"])

PLAIN = {
    "gesture_risk": "Unusual face or head movement was detected.",
    "gaze_away": "The student looked away from the screen.",
    "multi_face": "More than one face appeared in the camera.",
    "no_face": "No face was visible in the camera.",
    "app_violation": "A blocked app was running in the background.",
    "android_env_anomaly": "The phone camera saw something unusual in the room.",
    "heartbeat": "Routine check-in from the student computer.",
    "submit": "The student submitted the exam.",
}

SourceName = Literal["primary_webcam", "android_camera", "screen"]

_SOURCE_MAP: dict[str, SourceName] = {
    "primary_webcam": "primary_webcam",
    "webcam": "primary_webcam",
    "android_camera": "android_camera",
    "phone": "android_camera",
    "screen": "screen",
}


def _normalize_source(raw: object) -> SourceName:
    key = str(raw or "primary_webcam")
    return _SOURCE_MAP.get(key, "primary_webcam")


def _compute_cheating_probability(severities: list[float], last_risk: float) -> float:
    if not severities:
        return float(last_risk)
    peak = max(severities)
    mean = sum(severities) / len(severities)
    return round(min(1.0, 0.55 * peak + 0.35 * mean + 0.10 * last_risk), 4)


def _summary_plain(prob: float, flags: list[str], evidence_n: int) -> str:
    if prob < 0.35 and not flags:
        return "This attempt looks normal. Face stayed visible and no strong warning signals were saved."
    if prob < 0.65:
        return (
            f"This attempt needs a light review. We saved {evidence_n} camera photo(s) "
            "when something looked unusual. Open the photos below to decide."
        )
    return (
        f"This attempt is high risk ({int(prob * 100)}% integrity concern). "
        f"Abnormal face gestures or room alerts triggered {evidence_n} automatic photo capture(s). "
        "Review each photo before accepting the score."
    )


@router.get("/sessions/{session_id}", response_model=IntegrityReport)
def get_session_report(
    session_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> IntegrityReport:
    session = db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    student = db.get(User, session.student_id)
    exam = db.get(Exam, session.exam_id)

    events = list(
        db.scalars(
            select(IntegrityEvent)
            .where(IntegrityEvent.session_id == session_id)
            .order_by(IntegrityEvent.ts.asc())
        ).all()
    )

    severities = [e.severity for e in events]
    flags = sorted({e.type for e in events if e.severity >= 0.65})

    timeline: list[dict] = []
    evidence: list[EvidenceFrame] = []

    for e in events:
        payload = json.loads(e.payload_json or "{}")
        plain = str(payload.get("plain_language") or PLAIN.get(e.type, e.type))
        timeline.append(
            {
                "event_id": e.event_id,
                "type": e.type,
                "ts": e.ts.isoformat(),
                "severity": e.severity,
                "plain_language": plain,
                "payload": payload,
            }
        )
        image = payload.get("image_data_uri")
        if image:
            evidence.append(
                EvidenceFrame(
                    event_id=e.event_id,
                    captured_at=e.ts.isoformat(),
                    source=_normalize_source(payload.get("source")),
                    gesture_label=str(payload.get("gesture_label", e.type)),
                    plain_language=plain,
                    severity=e.severity,
                    image_data_uri=str(image),
                )
            )
        screen = payload.get("screen_image_data_uri")
        if screen:
            evidence.append(
                EvidenceFrame(
                    event_id=f"{e.event_id}-screen",
                    captured_at=e.ts.isoformat(),
                    source=cast(SourceName, "screen"),
                    gesture_label=str(payload.get("gesture_label", e.type)),
                    plain_language=f"Screen snapshot · {plain}",
                    severity=e.severity,
                    image_data_uri=str(screen),
                )
            )

    prob = _compute_cheating_probability(severities, session.last_risk_score)
    return IntegrityReport(
        session_id=session_id,
        student_name=student.full_name if student else "",
        student_email=student.email if student else "",
        exam_title=exam.title if exam else "",
        status=session.status,
        cheating_probability=prob,
        flags=flags,
        event_count=len(events),
        timeline=timeline,
        evidence=evidence,
        summary_plain=_summary_plain(prob, flags, len(evidence)),
    )
