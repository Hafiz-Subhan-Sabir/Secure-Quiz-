"""Exam session orchestrator — wires API, app lock, webcam ML, QR, sync."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from intelliQuiz_desktop.ai.engine import OnDeviceAIEngine
from intelliQuiz_desktop.core.config import DesktopSettings, get_settings
from intelliQuiz_desktop.core.device import device_fingerprint
from intelliQuiz_desktop.runtime.app_lock import AppLockController, ProcessHit
from intelliQuiz_desktop.runtime.face_monitor import FaceMonitor
from intelliQuiz_desktop.runtime.pairing_hub import PairingHub
from intelliQuiz_desktop.storage.event_store import EncryptedEventStore
from intelliQuiz_desktop.sync.api_client import ApiClient
from intelliQuiz_desktop.sync.worker import SyncWorker


@dataclass
class SessionState:
    phase: str = "idle"  # idle|login|camera_setup|exam|submitted
    email: str = ""
    role: str = ""
    exam_id: str = ""
    exam_title: str = ""
    session_id: str = ""
    pairing_token: str = ""
    paper: dict[str, Any] | None = None
    answers: dict[str, int] = field(default_factory=dict)
    started_at: str = ""
    error: str = ""
    android_paired: bool = False
    face_verified: bool = False
    identity_source: str = ""  # webcam | phone
    quiz_paused: bool = False
    pause_reason: str = ""


class SessionController:
    """Single source of truth for the Desktop exam runtime."""

    def __init__(self, settings: DesktopSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api = ApiClient()
        self.store = EncryptedEventStore(self.settings.data_dir / "events.db")
        self.sync = SyncWorker(self.store, self.api, batch_size=self.settings.sync_batch_size)
        self.state = SessionState()
        self._lock = threading.Lock()

        self.engine = OnDeviceAIEngine(self.settings.model_path)
        try:
            self.engine.load()
        except Exception as exc:
            self.state.error = f"AI model not loaded: {exc}"

        self.monitor = FaceMonitor(self.engine, settings=self.settings, on_event=self._on_integrity_event)
        self.pairing = PairingHub(
            host=self.settings.local_ws_host,
            port=self.settings.local_ws_port,
            ui_port=self.settings.local_ui_port,
            phone_https_port=self.settings.local_phone_https_port,
            on_paired=self._on_paired,
            on_unpaired=self._on_unpaired,
            on_android_event=self._on_integrity_event,
        )
        self.app_lock = AppLockController(
            kill=self.settings.app_lock_kill,
            kill_browsers=self.settings.app_lock_kill_browsers,
            on_violation=self._on_app_violation,
        )

        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None

    # ── auth / exam bootstrap ──────────────────────────────────────────
    def login(self, email: str, password: str) -> dict[str, Any]:
        data = self.api.login(email, password)
        if data.get("role") != "student":
            raise PermissionError("Desktop exam client is for students only. Use Admin Web for staff.")
        with self._lock:
            self.state.phase = "login"
            self.state.email = email
            self.state.role = data["role"]
            self.state.error = ""
        return {"ok": True, "role": data["role"], "email": email}

    def list_exams(self) -> list[dict[str, Any]]:
        return self.api.list_exams()

    def start_exam(self, exam_id: str) -> dict[str, Any]:
        paper = self.api.get_exam_paper(exam_id)
        session = self.api.create_session(exam_id, device_fingerprint())
        with self._lock:
            self.state.exam_id = exam_id
            self.state.exam_title = paper.get("title") or ""
            self.state.session_id = session["id"]
            self.state.pairing_token = session["pairing_token"]
            self.state.paper = paper
            self.state.answers = {}
            self.state.started_at = datetime.now(UTC).isoformat()
            self.state.phase = "camera_setup"
            self.state.android_paired = False
            self.state.face_verified = False
            self.state.identity_source = ""
            self.state.quiz_paused = False
            self.state.pause_reason = ""
            self.state.error = ""

        self.monitor.start(session["id"])
        self.app_lock.enforce_once()
        pairing = self.pairing.begin_session(
            session_id=session["id"],
            pairing_token=session["pairing_token"],
            exam_code=paper.get("title"),
        )
        self._append("heartbeat", 0.0, {"source": "session_start"})
        return {
            "ok": True,
            "session_id": session["id"],
            "paper": paper,
            "pairing": pairing,
            "app_lock": self.app_lock.snapshot(),
        }

    def advance_to_pairing(self) -> dict[str, Any]:
        """Legacy alias — camera setup already includes phone QR."""
        with self._lock:
            self.state.phase = "camera_setup"
        return {"ok": True, "phase": "camera_setup", "pairing": self.pairing.status()}

    def confirm_camera(self, *, prefer_phone: bool = False) -> dict[str, Any]:
        """Hard gate: PC webcam with one face, or paired phone camera."""
        mon = self.monitor.status()
        pair = self.pairing.status()
        paired = bool(pair.get("paired") or self.state.android_paired)

        if prefer_phone or (not mon.get("camera_ok") and paired):
            if not paired:
                raise RuntimeError(
                    "Phone camera is not paired yet. Scan the QR with your phone and wait for the green lock."
                )
            with self._lock:
                self.state.face_verified = True
                self.state.identity_source = "phone"
                self.state.android_paired = True
                self.state.phase = "camera_setup"
                self.state.error = ""
            self._append(
                "heartbeat",
                0.0,
                {"source": "confirm_camera", "identity_source": "phone", "android_paired": True},
            )
            return {
                "ok": True,
                "identity_source": "phone",
                "face_verified": True,
                "pairing": pair,
                "monitor": mon,
            }

        if not mon.get("camera_ok"):
            raise RuntimeError(
                "No webcam detected on this PC. Switch to “Use phone camera” and scan the QR code."
            )
        if int(mon.get("face_count") or 0) != 1:
            raise RuntimeError(
                "Show exactly one face, centered and well lit, then try again."
            )

        with self._lock:
            self.state.face_verified = True
            self.state.identity_source = "webcam"
            self.state.phase = "camera_setup"
            self.state.error = ""
        self._append(
            "heartbeat",
            0.0,
            {"source": "confirm_camera", "identity_source": "webcam", "face_count": mon.get("face_count")},
        )
        return {
            "ok": True,
            "identity_source": "webcam",
            "face_verified": True,
            "pairing": pair,
            "monitor": mon,
        }

    def enter_exam(self, *, require_pair: bool = False) -> dict[str, Any]:
        status = self.pairing.status()
        paired = bool(status.get("paired") or self.state.android_paired)

        # Auto-confirm if phone paired but confirm_camera was not called yet
        if not self.state.face_verified:
            if paired:
                with self._lock:
                    self.state.face_verified = True
                    self.state.identity_source = self.state.identity_source or "phone"
            else:
                mon = self.monitor.status()
                if mon.get("camera_ok") and int(mon.get("face_count") or 0) == 1:
                    with self._lock:
                        self.state.face_verified = True
                        self.state.identity_source = "webcam"
                else:
                    raise RuntimeError(
                        "Complete camera setup first: pass the webcam face check, or pair your phone camera."
                    )

        if require_pair and not paired:
            raise RuntimeError("Phone camera must be paired before starting the quiz")

        self.app_lock.start()
        hits, killed = self.app_lock.enforce_once()
        if any(h.category == "hard" for h in hits) and not killed:
            pass
        with self._lock:
            self.state.phase = "exam"
            self.state.android_paired = paired
            self.state.quiz_paused = False
            self.state.pause_reason = ""
        self._start_heartbeat()
        self._append(
            "heartbeat",
            0.05,
            {
                "source": "enter_exam",
                "android_paired": self.state.android_paired,
                "identity_source": self.state.identity_source,
                "app_hits": [{"name": h.name, "category": h.category} for h in hits],
                "killed": killed,
            },
        )
        return {
            "ok": True,
            "phase": "exam",
            "paper": self.state.paper,
            "identity_source": self.state.identity_source,
            "app_lock": self.app_lock.snapshot(),
            "monitor": self.monitor.status(),
        }

    def save_answer(self, question_id: str, choice_index: int) -> dict[str, Any]:
        self._refresh_pause_state()
        if self.state.quiz_paused:
            raise RuntimeError(self.state.pause_reason or "Quiz paused — restore camera access first")
        with self._lock:
            self.state.answers[question_id] = int(choice_index)
        return {"ok": True, "answers": dict(self.state.answers)}

    def submit(self) -> dict[str, Any]:
        self._refresh_pause_state()
        if self.state.quiz_paused:
            raise RuntimeError(self.state.pause_reason or "Quiz paused — restore camera access first")
        with self._lock:
            sid = self.state.session_id
            answers = dict(self.state.answers)
            risk = self.monitor.snapshot.session_risk
        if not sid:
            raise RuntimeError("No active session")
        self._append(
            "submit",
            float(risk),
            {
                "answers": answers,
                "submitted_at": datetime.now(UTC).isoformat(),
                "session_risk": risk,
            },
        )
        result = self.sync.flush(sid)
        try:
            self.api.heartbeat(sid, risk_score=float(risk), android_paired=self.state.android_paired)
        except Exception:
            pass
        with self._lock:
            self.state.phase = "submitted"
        self.shutdown_runtime(keep_store=True)
        return {"ok": True, "sync": result, "answers": answers, "risk": risk}

    # ── status ─────────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        self._refresh_pause_state()
        with self._lock:
            st = self.state
            return {
                "phase": st.phase,
                "email": st.email,
                "exam_id": st.exam_id,
                "exam_title": st.exam_title,
                "session_id": st.session_id,
                "android_paired": st.android_paired or self.pairing.status().get("paired"),
                "face_verified": st.face_verified,
                "identity_source": st.identity_source,
                "quiz_paused": st.quiz_paused,
                "pause_reason": st.pause_reason,
                "answers": dict(st.answers),
                "error": st.error,
                "started_at": st.started_at,
                "paper": st.paper,
                "monitor": self.monitor.status(),
                "app_lock": self.app_lock.snapshot(),
                "pairing": self.pairing.status(),
                "ai_ready": self.engine.ready,
            }

    def resume_after_camera(self) -> dict[str, Any]:
        """Clear pause once the required camera is healthy again."""
        self._refresh_pause_state()
        if self.state.quiz_paused:
            raise RuntimeError(self.state.pause_reason or "Camera is still unavailable")
        return {"ok": True, "quiz_paused": False}

    def mark_phone_paired(self) -> dict[str, Any]:
        self.pairing.mark_paired_local()
        return self.pairing.status()

    def simulate_abnormal(self) -> dict[str, Any]:
        """Lab helper: force an evidence capture as if ML fired."""
        payload = self.monitor.force_capture(
            "simulated_abnormal_gesture",
            gesture_label="SH",
            plain_language="Simulated head shake / looking away — webcam + screen evidence captured.",
            severity=0.85,
            event_type="gesture_risk",
        )
        return {
            "ok": True,
            "gesture": payload.get("gesture_label"),
            "has_webcam": bool(payload.get("image_data_uri")),
            "has_screen": bool(payload.get("screen_image_data_uri")),
        }

    def shutdown_runtime(self, *, keep_store: bool = False) -> None:
        self._hb_stop.set()
        self.app_lock.stop()
        self.monitor.stop()
        self.pairing.stop()
        if not keep_store:
            self.store.close()
            self.api.close()

    # ── internal event plumbing ────────────────────────────────────────
    def _append(self, typ: str, severity: float, payload: dict[str, Any]) -> None:
        sid = self.state.session_id
        if not sid:
            return
        self.store.append(session_id=sid, type=typ, severity=severity, payload=payload)
        try:
            self.sync.flush(sid)
        except Exception:
            pass

    def _on_integrity_event(self, typ: str, severity: float, payload: dict[str, Any]) -> None:
        self._append(typ, severity, payload)

    def _on_paired(self) -> None:
        with self._lock:
            self.state.android_paired = True
            if self.state.phase == "exam" and self.state.identity_source == "phone":
                self.state.quiz_paused = False
                self.state.pause_reason = ""
        self._append("heartbeat", 0.0, {"source": "android_paired", "android_paired": True})

    def _on_unpaired(self) -> None:
        with self._lock:
            self.state.android_paired = False
            if self.state.phase == "exam" and self.state.identity_source == "phone":
                self.state.quiz_paused = True
                self.state.pause_reason = (
                    "Phone camera disconnected. Scan the QR again and allow camera access to continue."
                )
        self._append(
            "no_face",
            0.7,
            {
                "source": "android_camera",
                "plain_language": "Phone camera disconnected during the exam.",
                "gesture_label": "PHONE_LOST",
            },
        )

    def _refresh_pause_state(self) -> None:
        """Pause the quiz when the identity camera is gone; clear pause when it returns."""
        with self._lock:
            if self.state.phase != "exam":
                return
            source = self.state.identity_source

        if source == "phone":
            pair = self.pairing.status()
            ok = bool(pair.get("paired") and pair.get("camera_live"))
            with self._lock:
                if not ok:
                    self.state.quiz_paused = True
                    self.state.android_paired = False
                    self.state.pause_reason = (
                        "Phone camera is required. Open the QR link on your phone, allow the camera, "
                        "and wait until it says Paired."
                    )
                else:
                    self.state.quiz_paused = False
                    self.state.android_paired = True
                    self.state.pause_reason = ""
            return

        # Webcam identity (default)
        mon = self.monitor.status()
        ok = bool(mon.get("camera_ok"))
        with self._lock:
            if not ok:
                self.state.quiz_paused = True
                self.state.pause_reason = (
                    "PC webcam was lost. Plug it back in / allow camera access, then continue."
                )
            elif self.state.identity_source != "phone":
                self.state.quiz_paused = False
                self.state.pause_reason = ""

    def _on_app_violation(self, hits: list[ProcessHit], killed: list[str]) -> None:
        hard = [h for h in hits if h.category == "hard"]
        severity = 0.9 if hard else 0.55
        self._append(
            "app_violation",
            severity,
            {
                "hits": [{"name": h.name, "pid": h.pid, "category": h.category} for h in hits],
                "killed": killed,
                "plain_language": (
                    "Blocked app activity during exam: "
                    + ", ".join(sorted({h.name for h in hits}))
                ),
                "source": "desktop_app_lock",
            },
        )

    def _start_heartbeat(self) -> None:
        if self._hb_thread and self._hb_thread.is_alive():
            return
        self._hb_stop.clear()

        def loop() -> None:
            while not self._hb_stop.wait(self.settings.heartbeat_interval_sec):
                sid = self.state.session_id
                if not sid:
                    continue
                risk = float(self.monitor.snapshot.session_risk)
                paired = bool(self.state.android_paired or self.pairing.status().get("paired"))
                try:
                    self.api.heartbeat(sid, risk_score=risk, android_paired=paired)
                except Exception:
                    pass
                self._append(
                    "heartbeat",
                    risk,
                    {
                        "source": "periodic",
                        "monitor": self.monitor.status(),
                        "app_lock": self.app_lock.snapshot(),
                        "android_paired": paired,
                    },
                )
                try:
                    self.sync.flush(sid)
                except Exception:
                    pass

        self._hb_thread = threading.Thread(target=loop, name="heartbeat", daemon=True)
        self._hb_thread.start()
