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
    "gesture_risk": "Odd face or head move.",
    "gaze_away": "Looked away from the screen.",
    "multi_face": "More than one face on camera.",
    "no_face": "No face on camera.",
    "app_violation": "Opened a blocked app.",
    "android_env_anomaly": "Phone camera saw something odd.",
    "heartbeat": "Normal check-in.",
    "submit": "Exam submitted.",
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


def _short_plain(text: str, typ: str) -> str:
    """Keep admin timeline easy to read (old long payloads get shortened)."""
    t = (text or "").strip()
    low = t.lower()
    if "phone" in low and ("disconnect" in low or "lost" in low):
        return "Phone camera lost."
    if "phone" in low and ("moved" in low or "cover" in low):
        return "Phone moved or covered."
    if "left the" in low and "app" in low:
        return "Left the phone camera app."
    if "blocked app" in low or "prohibited" in low or typ == "app_violation":
        return "Opened a blocked app."
    if "looked away" in low or typ == "gaze_away":
        return "Looked away from the screen."
    if "second face" in low or "more than one" in low or typ == "multi_face":
        return "More than one face on camera."
    if "no face" in low or typ == "no_face":
        return "No face on camera."
    if len(t) > 90:
        return t[:87] + "…"
    return t or PLAIN.get(typ, typ)


def _summary_plain(prob: float, flags: list[str], evidence_n: int) -> str:
    flag_bits: list[str] = []
    for f in flags:
        fl = f.lower()
        if "phone" in fl or "android" in fl or "no_face" in fl:
            flag_bits.append("phone / camera")
        elif "app" in fl:
            flag_bits.append("blocked app")
        elif "face" in fl or "gaze" in fl or "gesture" in fl:
            flag_bits.append("face")
        else:
            flag_bits.append(f.replace("_", " "))
    flag_text = ", ".join(dict.fromkeys(flag_bits)) if flag_bits else "none"

    if prob < 0.35 and not flags and evidence_n == 0:
        return "Looks fine. No strong cheating signs. You can accept the score."
    if prob < 0.65:
        return (
            f"Please check. Saved {evidence_n} photo(s). "
            f"Warnings: {flag_text}. Open photos, then decide."
        )
    return (
        f"High concern ({int(prob * 100)}% risk). Saved {evidence_n} photo(s). "
        f"Warnings: {flag_text}. Review photos before accepting."
    )


def _resolve_student_name(session: ExamSession, student: User | None, events: list) -> str:
    display = (getattr(session, "display_name", None) or "").strip()
    if display and display.lower() not in {"demo student", "student"}:
        return display
    # Prefer name typed on desktop (stored on events).
    for e in reversed(events):
        try:
            payload = json.loads(e.payload_json or "{}")
        except Exception:
            continue
        name = str(payload.get("student_name") or "").strip()
        if name and name.lower() not in {"demo student", "student"}:
            return name
    if display:
        return display
    return (student.full_name if student else "") or "Student"


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

    severities = [e.severity for e in events if e.type not in ("heartbeat", "submit")]
    flags = sorted(
        {
            e.type
            for e in events
            if e.severity >= 0.65 and e.type not in ("heartbeat", "submit")
        }
    )

    timeline: list[dict] = []
    evidence: list[EvidenceFrame] = []

    for e in events:
        payload = json.loads(e.payload_json or "{}")
        plain = _short_plain(
            str(payload.get("plain_language") or PLAIN.get(e.type, e.type)),
            e.type,
        )
        # Strip bulky images from timeline JSON so the admin UI stays fast
        timeline_payload = {
            k: v
            for k, v in payload.items()
            if k not in ("image_data_uri", "screen_image_data_uri")
        }
        timeline.append(
            {
                "event_id": e.event_id,
                "type": e.type,
                "ts": e.ts.isoformat(),
                "severity": e.severity,
                "plain_language": plain,
                "gesture_label": payload.get("gesture_label"),
                "student_name": payload.get("student_name"),
                "payload": timeline_payload,
            }
        )
        # Real evidence photos only (skip heartbeat noise)
        if e.type == "heartbeat":
            continue
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
                    plain_language="Screen photo · " + plain,
                    severity=e.severity,
                    image_data_uri=str(screen),
                )
            )

    # Meaningful event count excludes routine heartbeats
    meaningful = [e for e in events if e.type != "heartbeat"]
    prob = _compute_cheating_probability(severities, session.last_risk_score)
    return IntegrityReport(
        session_id=session_id,
        student_name=_resolve_student_name(session, student, events),
        student_email=student.email if student else "",
        exam_title=exam.title if exam else "",
        status=session.status,
        cheating_probability=prob,
        flags=flags,
        event_count=len(meaningful),
        timeline=[t for t in timeline if t["type"] != "heartbeat"],
        evidence=evidence,
        summary_plain=_summary_plain(prob, flags, len(evidence)),
        quiz_score=int(getattr(session, "quiz_score", 0) or 0),
        quiz_max_score=int(getattr(session, "quiz_max_score", 0) or 0),
        quiz_percent=float(getattr(session, "quiz_percent", 0.0) or 0.0),
    )
