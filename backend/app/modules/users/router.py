"""Admin endpoints to list and create student accounts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.core.security import hash_password
from app.db.models import User

router = APIRouter(prefix="/users", tags=["users"])


class StudentCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=6, max_length=128)


class StudentOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    created_at: str | None = None


@router.get("", response_model=list[StudentOut])
def list_students(
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> list[StudentOut]:
    rows = db.scalars(select(User).where(User.role == "student").order_by(User.created_at.desc())).all()
    return [
        StudentOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            created_at=u.created_at.isoformat() if u.created_at else None,
        )
        for u in rows
    ]


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    body: StudentCreate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> StudentOut:
    email = str(body.email).lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with that email already exists.")

    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return StudentOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    user_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin")),
) -> None:
    from app.db.models import ExamSession

    user = db.get(User, user_id)
    if user is None or user.role != "student":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    has_sessions = db.scalar(select(ExamSession.id).where(ExamSession.student_id == user_id).limit(1))
    if has_sessions is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This student has exam attempts. Clear their reports first, then remove the login.",
        )
    db.delete(user)
    db.commit()
