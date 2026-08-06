import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.db.models import Exam, ExamSession, IntegrityEvent, User
from app.modules.schemas import (
    AttemptSummary,
    HeartbeatRequest,
    OkResponse,
    SessionCreate,
    SessionResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreate,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_roles("student", "admin")),
) -> ExamSession:
    exam = db.get(Exam, body.exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status != "published" and claims.get("role") != "admin":
        raise HTTPException(status_code=400, detail="Exam is not published")

    session = ExamSession(
        exam_id=exam.id,
        student_id=claims["sub"],
        status="active",
        device_fingerprint=body.device_fingerprint,
        pairing_token=secrets.token_urlsafe(24),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/attempts", response_model=list[AttemptSummary])
def list_attempts(
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> list[AttemptSummary]:
    """All student quiz attempts for admin monitoring."""
    rows = db.execute(
        select(ExamSession, User, Exam)
        .join(User, User.id == ExamSession.student_id)
        .join(Exam, Exam.id == ExamSession.exam_id)
        .order_by(ExamSession.started_at.desc())
    ).all()

    out: list[AttemptSummary] = []
    for session, student, exam in rows:
        event_count = int(
            db.scalar(
                select(func.count())
                .select_from(IntegrityEvent)
                .where(IntegrityEvent.session_id == session.id)
            )
            or 0
        )
        evidence_count = int(
            db.scalar(
                select(func.count())
                .select_from(IntegrityEvent)
                .where(
                    IntegrityEvent.session_id == session.id,
                    IntegrityEvent.payload_json.like("%image_data_uri%"),
                )
            )
            or 0
        )
        out.append(
            AttemptSummary(
                session_id=session.id,
                student_name=student.full_name,
                student_email=student.email,
                exam_title=exam.title,
                status=session.status,
                started_at=session.started_at,
                last_risk_score=session.last_risk_score,
                android_paired=session.android_paired,
                event_count=event_count,
                evidence_count=evidence_count,
                flagged=session.last_risk_score >= 0.65 or evidence_count > 0,
            )
        )
    return out


@router.post("/{session_id}/heartbeat", response_model=OkResponse)
def heartbeat(
    session_id: str,
    body: HeartbeatRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_roles("student", "admin")),
) -> OkResponse:
    session = db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.student_id != claims["sub"] and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    session.last_risk_score = body.risk_score
    session.android_paired = body.android_paired
    db.commit()
    return OkResponse(ok=True)
