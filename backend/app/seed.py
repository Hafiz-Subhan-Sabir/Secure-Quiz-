"""Dev seed — demo accounts + a sample student attempt with camera evidence."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.evidence import GESTURE_EVIDENCE
from app.core.security import hash_password
from app.db.models import Exam, ExamSession, IntegrityEvent, ProctoringProfile, Question, User
from app.db.session import SessionLocal


SAMPLE_QUESTIONS = [
    {
        "prompt": "Which control best reduces webcam blind spots during a proctored exam?",
        "choices": [
            "Disable the primary webcam",
            "Pair a secondary mobile camera via QR handshake",
            "Lower AI gaze sensitivity only",
            "Allow Discord for support chat",
        ],
        "correct_index": 1,
    },
    {
        "prompt": "What should the Desktop app do when a high-risk face gesture is detected?",
        "choices": [
            "Open an AI chatbot to help the student",
            "Ignore it completely",
            "Raise risk and capture a webcam photo (and optional screen snapshot)",
            "Delete the student’s answers immediately",
        ],
        "correct_index": 2,
    },
    {
        "prompt": "What is the phone QR code used for during an IntelliQuiz exam?",
        "choices": [
            "Opening study notes in a browser",
            "Pairing IntelliQuiz Mobile as a room camera only",
            "Downloading helper apps",
            "Sharing answers with classmates",
        ],
        "correct_index": 1,
    },
    {
        "prompt": "Why does IntelliQuiz lock apps like Chrome, Discord, and TeamViewer?",
        "choices": [
            "To save battery",
            "To prevent browsing, chat, and remote-control cheating channels",
            "Because they slow down the camera",
            "Only for branding reasons",
        ],
        "correct_index": 1,
    },
]

CYBER_QUESTIONS = [
    {
        "prompt": "What does TLS primarily protect?",
        "choices": [
            "CPU temperature",
            "Data in transit between client and server",
            "Hard disk fragmentation",
            "Screen brightness",
        ],
        "correct_index": 1,
    },
    {
        "prompt": "Which is the best practice for exam passwords?",
        "choices": [
            "Share one password with the class",
            "Use unique strong passwords per account",
            "Write passwords on the whiteboard",
            "Disable authentication during exams",
        ],
        "correct_index": 1,
    },
    {
        "prompt": "What is phishing?",
        "choices": [
            "A network cable type",
            "Tricking users into revealing sensitive information",
            "Encrypting a database",
            "Running antivirus scans",
        ],
        "correct_index": 1,
    },
]


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).limit(1))
        if existing is None:
            admin = User(
                email="admin@intelliquiz.dev",
                full_name="System Admin",
                hashed_password=hash_password("Admin123!"),
                role="admin",
            )
            instructor = User(
                email="instructor@intelliquiz.dev",
                full_name="Demo Instructor",
                hashed_password=hash_password("Teach123!"),
                role="instructor",
            )
            student = User(
                email="student@intelliquiz.dev",
                full_name="Demo Student",
                hashed_password=hash_password("Student123!"),
                role="student",
            )
            profile = ProctoringProfile(
                name="Default Medium",
                strictness="medium",
                warn_threshold=0.4,
                flag_threshold=0.65,
                terminate_threshold=0.9,
            )
            db.add_all([admin, instructor, student, profile])
            db.flush()

            exam = Exam(
                title="Sample Integrity Exam",
                instructions="Keep your face visible. Pair the Android camera before you start.",
                duration_minutes=60,
                status="published",
                proctoring_profile_id=profile.id,
                created_by=instructor.id,
            )
            db.add(exam)
            db.commit()

        _ensure_sample_questions(db)
        _ensure_second_exam(db)
        _ensure_demo_attempt(db)
    finally:
        db.close()


def _ensure_sample_questions(db) -> None:
    """Attach demo questions to any published exam that has none."""
    exams = list(db.scalars(select(Exam).where(Exam.status == "published")).all())
    for exam in exams:
        count = db.scalar(select(func.count()).select_from(Question).where(Question.exam_id == exam.id))
        if int(count or 0) > 0:
            continue
        for i, item in enumerate(SAMPLE_QUESTIONS):
            db.add(
                Question(
                    exam_id=exam.id,
                    prompt=item["prompt"],
                    choices_json=json.dumps(item["choices"]),
                    correct_index=item["correct_index"],
                    points=1,
                    order_index=i,
                )
            )
    db.commit()


def _ensure_second_exam(db) -> None:
    """Ensure a second published quiz exists for multi-exam selection."""
    title = "Cybersecurity Basics Quiz"
    existing = db.scalar(select(Exam).where(Exam.title == title).limit(1))
    if existing is not None:
        return
    profile = db.scalar(select(ProctoringProfile).limit(1))
    instructor = db.scalar(select(User).where(User.role == "instructor").limit(1))
    exam = Exam(
        title=title,
        instructions="Answer all questions. Phone camera pairing recommended.",
        duration_minutes=30,
        status="published",
        proctoring_profile_id=profile.id if profile else None,
        created_by=instructor.id if instructor else None,
    )
    db.add(exam)
    db.flush()
    for i, item in enumerate(CYBER_QUESTIONS):
        db.add(
            Question(
                exam_id=exam.id,
                prompt=item["prompt"],
                choices_json=json.dumps(item["choices"]),
                correct_index=item["correct_index"],
                points=1,
                order_index=i,
            )
        )
    db.commit()


def _ensure_demo_attempt(db) -> None:
    """Create one rich demo attempt so admins can see facial evidence immediately."""
    marker = db.scalar(
        select(IntegrityEvent).where(IntegrityEvent.payload_json.like("%demo_evidence%")).limit(1)
    )
    if marker is not None:
        return

    student = db.scalar(select(User).where(User.email == "student@intelliquiz.dev"))
    exam = db.scalar(select(Exam).where(Exam.status == "published").limit(1))
    if student is None or exam is None:
        return

    started = datetime.now(UTC) - timedelta(minutes=18)
    session = ExamSession(
        exam_id=exam.id,
        student_id=student.id,
        status="submitted",
        device_fingerprint="demo-desktop-fingerprint",
        pairing_token=secrets.token_urlsafe(24),
        started_at=started,
        submitted_at=datetime.now(UTC) - timedelta(minutes=2),
        last_risk_score=0.82,
        android_paired=True,
    )
    db.add(session)
    db.flush()

    samples = [
        (
            "gesture_risk",
            0.85,
            "head_shake",
            "primary_webcam",
            "SH",
            "Student shook their head and looked left/right — automatic webcam photo saved.",
            4,
        ),
        (
            "gesture_risk",
            0.9,
            "wink_tilt",
            "primary_webcam",
            "W&HT",
            "Wink plus head tilt detected — strong gaze diversion. Webcam photo saved.",
            7,
        ),
        (
            "gesture_risk",
            0.55,
            "mouth_open",
            "primary_webcam",
            "MO",
            "Mouth opened wide — possible talking. Webcam photo saved.",
            10,
        ),
        (
            "android_env_anomaly",
            0.7,
            "android_env",
            "android_camera",
            "ENV",
            "Phone camera (side view) saw unexpected movement in the room. Photo saved.",
            12,
        ),
        (
            "multi_face",
            0.88,
            "multi_face",
            "primary_webcam",
            "MULTI",
            "A second face entered the webcam frame. Photo saved for review.",
            15,
        ),
        (
            "submit",
            0.0,
            None,
            "primary_webcam",
            "SUBMIT",
            "Student clicked Submit. Final answers locked and logs queued for sync.",
            16,
        ),
    ]

    for typ, severity, evidence_key, source, label, plain, minute_offset in samples:
        payload: dict = {
            "demo_evidence": True,
            "gesture_label": label,
            "plain_language": plain,
            "source": source,
            "model": "FaceGest-Mediapipe-RF",
        }
        if evidence_key:
            payload["image_data_uri"] = GESTURE_EVIDENCE[evidence_key]
            payload["capture_reason"] = "abnormal_face_gesture" if typ == "gesture_risk" else typ

        db.add(
            IntegrityEvent(
                id=str(uuid.uuid4()),
                session_id=session.id,
                event_id=str(uuid.uuid4()),
                type=typ,
                ts=started + timedelta(minutes=minute_offset),
                severity=severity,
                payload_json=json.dumps(payload, separators=(",", ":")),
            )
        )

    db.commit()
