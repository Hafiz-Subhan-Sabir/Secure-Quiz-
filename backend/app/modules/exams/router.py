from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import json

from app.core.deps import get_db, require_roles
from app.db.models import Exam, Question
from app.modules.schemas import ExamCreate, ExamDetail, ExamPaper, ExamSummary, QuestionOut

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("", response_model=list[ExamSummary])
def list_exams(
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor", "student")),
) -> list[Exam]:
    # Students (Desktop) only see published exams; admins see everything.
    q = select(Exam).order_by(Exam.created_at.desc())
    if _claims.get("role") == "student":
        q = q.where(Exam.status == "published")
    return list(db.scalars(q).all())


@router.post("", response_model=ExamSummary, status_code=status.HTTP_201_CREATED)
def create_exam(
    body: ExamCreate,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_roles("admin", "instructor")),
) -> Exam:
    exam = Exam(
        title=body.title,
        duration_minutes=body.duration_minutes,
        instructions=body.instructions,
        proctoring_profile_id=body.proctoring_profile_id,
        created_by=claims["sub"],
        status="draft",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@router.get("/{exam_id}", response_model=ExamDetail)
def get_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor", "student")),
) -> ExamDetail:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    q_count = db.scalar(select(func.count()).select_from(Question).where(Question.exam_id == exam_id))
    return ExamDetail(
        id=exam.id,
        title=exam.title,
        status=exam.status,
        duration_minutes=exam.duration_minutes,
        proctoring_profile_id=exam.proctoring_profile_id,
        instructions=exam.instructions,
        question_count=int(q_count or 0),
    )


@router.get("/{exam_id}/paper", response_model=ExamPaper)
def get_exam_paper(
    exam_id: str,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_roles("student", "admin", "instructor")),
) -> ExamPaper:
    """Student exam paper — choices only, never includes correct answers."""
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status != "published" and claims.get("role") == "student":
        raise HTTPException(status_code=400, detail="Exam is not published")

    rows = list(
        db.scalars(
            select(Question).where(Question.exam_id == exam_id).order_by(Question.order_index.asc())
        ).all()
    )
    questions = [
        QuestionOut(
            id=q.id,
            prompt=q.prompt,
            choices=json.loads(q.choices_json or "[]"),
            order_index=q.order_index,
            points=q.points,
        )
        for q in rows
    ]
    return ExamPaper(
        exam_id=exam.id,
        title=exam.title,
        instructions=exam.instructions,
        duration_minutes=exam.duration_minutes,
        questions=questions,
    )


@router.post("/{exam_id}/publish", response_model=ExamSummary)
def publish_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> Exam:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    exam.status = "published"
    db.commit()
    db.refresh(exam)
    return exam
