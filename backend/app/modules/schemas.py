"""Shared Pydantic schemas aligned with contracts/openapi/intelliQuiz.v1.yaml."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["admin", "instructor", "student"]
    expires_in: int
    full_name: str = ""
    email: str = ""


class ExamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(ge=1, le=600)
    proctoring_profile_id: str | None = None
    instructions: str = ""


class ExamSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: str
    duration_minutes: int
    proctoring_profile_id: str | None = None


class ExamDetail(ExamSummary):
    instructions: str = ""
    question_count: int = 0


class QuestionOut(BaseModel):
    id: str
    prompt: str
    choices: list[str]
    order_index: int
    points: int = 1


class QuestionAdminOut(QuestionOut):
    correct_index: int = 0


class QuestionCreate(BaseModel):
    prompt: str = Field(min_length=1)
    choices: list[str] = Field(min_length=2, max_length=8)
    correct_index: int = Field(ge=0)
    points: int = Field(default=1, ge=1, le=100)
    order_index: int | None = None


class QuestionUpdate(BaseModel):
    prompt: str | None = None
    choices: list[str] | None = Field(default=None, min_length=2, max_length=8)
    correct_index: int | None = Field(default=None, ge=0)
    points: int | None = Field(default=None, ge=1, le=100)
    order_index: int | None = None


class ExamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    instructions: str | None = None
    proctoring_profile_id: str | None = None


class ProctoringProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strictness: Literal["low", "medium", "high", "lockdown"] = "medium"
    warn_threshold: float = Field(default=0.4, ge=0, le=1)
    flag_threshold: float = Field(default=0.65, ge=0, le=1)
    terminate_threshold: float = Field(default=0.9, ge=0, le=1)
    require_android_camera: bool = True
    blacklist_apps_csv: str = "chrome,discord,teamviewer,anydesk"


class ProctoringProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    strictness: str
    warn_threshold: float
    flag_threshold: float
    terminate_threshold: float
    require_android_camera: bool
    blacklist_apps_csv: str


class ExamPaper(BaseModel):
    exam_id: str
    title: str
    instructions: str
    duration_minutes: int
    questions: list[QuestionOut]


class SessionCreate(BaseModel):
    exam_id: str
    device_fingerprint: str = Field(min_length=4, max_length=255)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exam_id: str
    status: str
    started_at: datetime
    pairing_token: str


class HeartbeatRequest(BaseModel):
    client_ts: datetime
    risk_score: float = Field(ge=0, le=1)
    android_paired: bool = False


class OkResponse(BaseModel):
    ok: bool = True


class IntegrityEventIn(BaseModel):
    event_id: str
    type: str
    ts: datetime
    severity: float = Field(ge=0, le=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    session_id: str
    events: list[IntegrityEventIn] = Field(min_length=1, max_length=500)


class SyncResult(BaseModel):
    accepted: int
    duplicates: int
    rejected: int


class EvidenceFrame(BaseModel):
    event_id: str
    captured_at: str
    source: Literal["primary_webcam", "android_camera", "screen"]
    gesture_label: str
    plain_language: str
    severity: float
    image_data_uri: str


class IntegrityReport(BaseModel):
    session_id: str
    student_name: str = ""
    student_email: str = ""
    exam_title: str = ""
    status: str = ""
    cheating_probability: float
    flags: list[str]
    event_count: int
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceFrame] = Field(default_factory=list)
    summary_plain: str = ""
    quiz_score: int = 0
    quiz_max_score: int = 0
    quiz_percent: float = 0.0


class AttemptSummary(BaseModel):
    session_id: str
    student_name: str
    student_email: str
    exam_title: str
    status: str
    started_at: datetime
    last_risk_score: float
    android_paired: bool
    event_count: int
    evidence_count: int
    flagged: bool
    quiz_score: int = 0
    quiz_max_score: int = 0
    quiz_percent: float = 0.0


class StudentAttemptResult(BaseModel):
    """Score + status a student can see after submitting (no evidence photos)."""

    session_id: str
    exam_id: str
    exam_title: str = ""
    status: str
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    quiz_score: int = 0
    quiz_max_score: int = 0
    quiz_percent: float = 0.0
    last_risk_score: float = 0.0
