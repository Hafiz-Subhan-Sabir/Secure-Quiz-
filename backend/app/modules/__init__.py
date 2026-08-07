"""Shared Pydantic schemas."""

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


class IntegrityReport(BaseModel):
    session_id: str
    cheating_probability: float
    flags: list[str]
    event_count: int
    timeline: list[dict[str, Any]] = Field(default_factory=list)
