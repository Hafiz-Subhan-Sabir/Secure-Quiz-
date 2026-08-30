from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import json

from app.core.deps import get_db, require_roles
from app.db.models import Exam, ProctoringProfile, Question
from app.modules.schemas import (
    ExamCreate,
    ExamDetail,
    ExamPaper,
    ExamSummary,
    ExamUpdate,
    QuestionAdminOut,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
)

router = APIRouter(prefix="/exams", tags=["exams"])


def _question_admin(q: Question) -> QuestionAdminOut:
    return QuestionAdminOut(
        id=q.id,
        prompt=q.prompt,
        choices=json.loads(q.choices_json or "[]"),
        correct_index=q.correct_index,
        order_index=q.order_index,
        points=q.points,
    )


def _question_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        prompt=q.prompt,
        choices=json.loads(q.choices_json or "[]"),
        order_index=q.order_index,
        points=q.points,
    )


@router.get("", response_model=list[ExamSummary])
def list_exams(
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor", "student")),
) -> list[Exam]:
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
    if body.proctoring_profile_id:
        if db.get(ProctoringProfile, body.proctoring_profile_id) is None:
            raise HTTPException(status_code=400, detail="Proctoring profile not found")
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


@router.patch("/{exam_id}", response_model=ExamDetail)
def update_exam(
    exam_id: str,
    body: ExamUpdate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> ExamDetail:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if body.proctoring_profile_id is not None:
        if body.proctoring_profile_id and db.get(ProctoringProfile, body.proctoring_profile_id) is None:
            raise HTTPException(status_code=400, detail="Proctoring profile not found")
        exam.proctoring_profile_id = body.proctoring_profile_id or None
    if body.title is not None:
        exam.title = body.title
    if body.duration_minutes is not None:
        exam.duration_minutes = body.duration_minutes
    if body.instructions is not None:
        exam.instructions = body.instructions
    db.commit()
    db.refresh(exam)
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


@router.get("/{exam_id}/questions", response_model=list[QuestionAdminOut])
def list_questions(
    exam_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> list[QuestionAdminOut]:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    rows = list(
        db.scalars(
            select(Question).where(Question.exam_id == exam_id).order_by(Question.order_index.asc())
        ).all()
    )
    return [_question_admin(q) for q in rows]


@router.post("/{exam_id}/questions", response_model=QuestionAdminOut, status_code=status.HTTP_201_CREATED)
def create_question(
    exam_id: str,
    body: QuestionCreate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> QuestionAdminOut:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if body.correct_index >= len(body.choices):
        raise HTTPException(status_code=400, detail="correct_index out of range")
    if body.order_index is None:
        max_order = db.scalar(
            select(func.max(Question.order_index)).where(Question.exam_id == exam_id)
        )
        order_index = int(max_order or -1) + 1
    else:
        order_index = body.order_index
    q = Question(
        exam_id=exam_id,
        prompt=body.prompt,
        choices_json=json.dumps(body.choices),
        correct_index=body.correct_index,
        points=body.points,
        order_index=order_index,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_admin(q)


@router.put("/{exam_id}/questions/{question_id}", response_model=QuestionAdminOut)
def update_question(
    exam_id: str,
    question_id: str,
    body: QuestionUpdate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> QuestionAdminOut:
    q = db.get(Question, question_id)
    if q is None or q.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="Question not found")
    if body.prompt is not None:
        q.prompt = body.prompt
    if body.choices is not None:
        q.choices_json = json.dumps(body.choices)
    if body.correct_index is not None:
        choices = body.choices or json.loads(q.choices_json or "[]")
        if body.correct_index >= len(choices):
            raise HTTPException(status_code=400, detail="correct_index out of range")
        q.correct_index = body.correct_index
    if body.points is not None:
        q.points = body.points
    if body.order_index is not None:
        q.order_index = body.order_index
    db.commit()
    db.refresh(q)
    return _question_admin(q)


@router.delete("/{exam_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    exam_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> None:
    q = db.get(Question, question_id)
    if q is None or q.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(q)
    db.commit()


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
    questions = [_question_out(q) for q in rows]
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
    q_count = int(
        db.scalar(select(func.count()).select_from(Question).where(Question.exam_id == exam_id)) or 0
    )
    if q_count < 1:
        raise HTTPException(
            status_code=400,
            detail="Add at least one question before publishing this exam.",
        )
    exam.status = "published"
    db.commit()
    db.refresh(exam)
    return exam
