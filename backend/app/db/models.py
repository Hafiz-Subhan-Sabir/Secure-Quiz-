import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProctoringProfile(Base):
    __tablename__ = "proctoring_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    strictness: Mapped[str] = mapped_column(String(32), default="medium")
    warn_threshold: Mapped[float] = mapped_column(Float, default=0.4)
    flag_threshold: Mapped[float] = mapped_column(Float, default=0.65)
    terminate_threshold: Mapped[float] = mapped_column(Float, default=0.9)
    require_android_camera: Mapped[bool] = mapped_column(default=True)
    blacklist_apps_csv: Mapped[str] = mapped_column(
        Text, default="chrome,discord,teamviewer,anydesk"
    )


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    proctoring_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("proctoring_profiles.id"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    questions: Mapped[list["Question"]] = relationship(back_populates="exam")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    exam_id: Mapped[str] = mapped_column(String(36), ForeignKey("exams.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    choices_json: Mapped[str] = mapped_column(Text, default="[]")
    correct_index: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=1)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    exam: Mapped[Exam] = relationship(back_populates="questions")


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    exam_id: Mapped[str] = mapped_column(String(36), ForeignKey("exams.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(255), default="")
    pairing_token: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    android_paired: Mapped[bool] = mapped_column(default=False)
    quiz_score: Mapped[int] = mapped_column(Integer, default=0)
    quiz_max_score: Mapped[int] = mapped_column(Integer, default=0)
    quiz_percent: Mapped[float] = mapped_column(Float, default=0.0)


class IntegrityEvent(Base):
    __tablename__ = "integrity_events"
    __table_args__ = (UniqueConstraint("session_id", "event_id", name="uq_session_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("exam_sessions.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36))
    type: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
