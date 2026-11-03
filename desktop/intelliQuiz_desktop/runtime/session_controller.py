"""Exam session orchestrator — wires API, app lock, webcam ML, QR, sync."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intelliQuiz_desktop.ai.engine import OnDeviceAIEngine
from intelliQuiz_desktop.core.config import DesktopSettings, get_settings
from intelliQuiz_desktop.core.device import device_fingerprint
from intelliQuiz_desktop.runtime.app_lock import AppLockController, ProcessHit
from intelliQuiz_desktop.runtime.exam_shell import ExamShell
from intelliQuiz_desktop.runtime.face_monitor import FaceMonitor
from intelliQuiz_desktop.runtime.focus_guard import FocusGuard
from intelliQuiz_desktop.runtime.pairing_hub import PairingHub
from intelliQuiz_desktop.runtime.workers import shutdown_workers, submit_sync
from intelliQuiz_desktop.security.identity import embedding_from_jpeg, merge_samples, verify
from intelliQuiz_desktop.storage.identity_store import IdentityStore
from intelliQuiz_desktop.storage.event_store import EncryptedEventStore
from intelliQuiz_desktop.sync.api_client import ApiClient
from intelliQuiz_desktop.sync.worker import SyncWorker


@dataclass
class SessionState:
    phase: str = "idle"  # idle|login|camera_setup|exam|submitted
    email: str = ""
    full_name: str = ""
    role: str = ""
    exam_id: str = ""
    exam_title: str = ""
    session_id: str = ""
    pairing_token: str = ""
    paper: dict[str, Any] | None = None
    answers: dict[str, int] = field(default_factory=dict)
    started_at: str = ""
    identity_deferred_phone: bool = False
    error: str = ""
    android_paired: bool = False
    face_verified: bool = False
    identity_source: str = ""  # webcam | phone
    quiz_paused: bool = False
    pause_reason: str = ""
    # Independent pause channels — camera/phone refresh must not wipe focus/app.
    pause_reasons: dict[str, str] = field(default_factory=dict)
    student_alert: str = ""
    require_android_camera: bool = False
    last_result: dict[str, Any] | None = None


class SessionController:
    """Single source of truth for the Desktop exam runtime."""

    def __init__(self, settings: DesktopSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api = ApiClient()
        self.store = EncryptedEventStore(self.settings.data_dir / "events.db")
        self.sync = SyncWorker(self.store, self.api, batch_size=self.settings.sync_batch_size)
        self.state = SessionState()
        self._lock = threading.RLock()

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
        self.app_lock.set_protect_dev_tools(bool(self.settings.app_lock_protect_dev))
        self.focus_guard = FocusGuard(
            away_threshold_sec=self.settings.focus_loss_pause_sec,
            on_away=self._on_focus_away,
            on_return=self._on_focus_return,
        )
        self.exam_shell = ExamShell()
        self.identity_store = IdentityStore(self.settings.data_dir)

        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None
        self.sync.start()
        self._flush_pending_sync()

    def identity_status(self) -> dict[str, Any]:
        with self._lock:
            email = self.state.email
            deferred = self.state.identity_deferred_phone
        if not email:
            return {"enrolled": False, "needs_enrollment": True, "camera_ok": False}
        enrolled = self.identity_store.is_enrolled(email)
        mon = self.monitor.status()
        pair = self.pairing.status()
        return {
            "enrolled": enrolled or deferred,
            "needs_enrollment": not enrolled and not deferred,
            "email": email,
            "deferred_phone": deferred,
            "camera_ok": bool(mon.get("camera_ok")),
            "phone_paired": bool(pair.get("paired")),
            "phone_frames": int(pair.get("android_frames") or 0),
            "pairing": pair,
        }

    def begin_enrollment_pairing(self, *, force_new: bool = False) -> dict[str, Any]:
        """Start a phone QR session before an exam so identity can enroll from phone.

        Reuses the current enroll session/token when already active so a Refresh
        (or auto “no webcam” switch) does not invalidate a phone that already
        opened the previous QR — that was causing WS connect + enroll 400.
        """
        import secrets
        import uuid

        with self._lock:
            email = self.state.email
            existing_sid = self.state.session_id or ""
            existing_tok = self.state.pairing_token or ""
        if not email:
            raise RuntimeError("Sign in before phone enrollment")

        pair_now = self.pairing.status()
        reuse = (
            not force_new
            and existing_sid.startswith("enroll-")
            and bool(existing_tok)
            and bool(pair_now.get("active") or pair_now.get("paired") or pair_now.get("mobile_camera_url"))
        )
        if reuse:
            session_id = existing_sid
            token = existing_tok
        else:
            session_id = f"enroll-{uuid.uuid4().hex[:12]}"
            token = secrets.token_urlsafe(18)
            with self._lock:
                if not self.state.session_id or self.state.session_id.startswith("enroll-"):
                    self.state.session_id = session_id
                    self.state.pairing_token = token

        pairing = self.pairing.begin_session(
            session_id=session_id,
            pairing_token=token,
            exam_code="Face enrollment",
            preserve_live=reuse,
        )
        return {"ok": True, "pairing": pairing, "reused": reuse}

    def defer_enrollment_to_phone(self) -> dict[str, Any]:
        """Skip PC webcam enroll; student will use phone camera at the exam camera step."""
        with self._lock:
            if not self.state.email:
                raise RuntimeError("Sign in first")
            self.state.identity_deferred_phone = True
            self.state.identity_source = "phone"
        return {"ok": True, "deferred_phone": True, "needs_enrollment": False}

    def enroll_identity(self, *, samples: int = 5, source: str = "auto") -> dict[str, Any]:
        with self._lock:
            email = self.state.email
        if not email:
            raise RuntimeError("Sign in before enrolling your face")
        if self.identity_store.is_enrolled(email):
            return {"ok": True, "enrolled": True, "message": "Already enrolled"}

        prefer = (source or "auto").strip().lower()
        pair = self.pairing.status()
        phone_ready = bool(pair.get("paired"))

        if prefer == "phone":
            return self._enroll_from_phone(email=email, samples=samples)

        # Start webcam before judging camera_ok — otherwise first enroll always fails.
        if not self.monitor.snapshot.running:
            self.monitor.start("identity-enroll")
        cam_deadline = time.time() + 10.0
        while time.time() < cam_deadline:
            mon = self.monitor.status()
            if mon.get("camera_ok"):
                break
            # If phone already paired, don't wait the full open timeout.
            if prefer == "auto" and phone_ready and time.time() > cam_deadline - 6.0:
                break
            time.sleep(0.25)

        mon = self.monitor.status()
        # No webcam (or already on phone path): do not block forever waiting for a missing camera
        if prefer == "auto" and not mon.get("camera_ok"):
            if phone_ready:
                return self._enroll_from_phone(email=email, samples=samples)
            raise RuntimeError(
                "No PC webcam detected. Tap “Use phone to enroll”, scan the QR, "
                "or tap “Skip for now — use phone at camera step”."
            )

        captured: list = []
        deadline = time.time() + 12.0
        while len(captured) < samples and time.time() < deadline:
            mon = self.monitor.status()
            if mon.get("camera_ok") and int(mon.get("face_count") or 0) == 1:
                sample = self.monitor.identity_sample()
                if sample is not None:
                    captured.append(sample)
            time.sleep(0.45)

        if len(captured) >= max(3, samples // 2):
            embedding = merge_samples(captured)
            self.identity_store.save(email, embedding)
            with self._lock:
                self.state.identity_deferred_phone = False
                self.state.identity_source = "webcam"
            return {
                "ok": True,
                "enrolled": True,
                "samples_used": len(captured),
                "source": "webcam",
            }

        if self.pairing.status().get("paired"):
            return self._enroll_from_phone(email=email, samples=samples)

        raise RuntimeError(
            "Could not enroll from webcam. Tap “Use phone to enroll” or "
            "“Skip for now — use phone at camera step”."
        )

    def _enroll_from_phone(self, *, email: str, samples: int = 5) -> dict[str, Any]:
        pair = self.pairing.status()
        if not pair.get("paired"):
            raise RuntimeError(
                "Phone is not paired yet. Scan the enrollment QR and allow camera on the phone."
            )

        from intelliQuiz_desktop.ai.landmarks import FaceLandmarkerBundle

        landmarker = FaceLandmarkerBundle(self.settings.face_landmarker_path)
        captured: list = []
        seen_hashes: set[int] = set()
        deadline = time.time() + 25.0
        try:
            while len(captured) < samples and time.time() < deadline:
                jpeg = self.pairing.latest_jpeg()
                if jpeg:
                    h = hash(jpeg[:64] + jpeg[-64:] if len(jpeg) > 128 else jpeg)
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        emb = embedding_from_jpeg(
                            jpeg,
                            landmarker_path=self.settings.face_landmarker_path,
                            landmarker=landmarker,
                        )
                        if emb is not None:
                            captured.append(emb)
                time.sleep(0.4)
        finally:
            try:
                landmarker.close()
            except Exception:
                pass

        if len(captured) < max(2, samples // 2):
            raise RuntimeError(
                "Could not capture enough face samples from the phone. "
                "Hold the phone so your face is centered, well lit, then try again."
            )

        embedding = merge_samples(captured)
        self.identity_store.save(email, embedding)
        with self._lock:
            self.state.identity_deferred_phone = False
            self.state.identity_source = "phone"
            self.state.android_paired = True
        return {
            "ok": True,
            "enrolled": True,
            "samples_used": len(captured),
            "source": "phone",
        }

    def _phone_face_embedding(self):
        """Build an identity embedding from the latest phone JPEG, if any."""
        jpeg = self.pairing.latest_jpeg()
        if not jpeg:
            return None
        try:
            return embedding_from_jpeg(
                jpeg,
                landmarker_path=self.settings.face_landmarker_path,
            )
        except Exception:
            return None

    def _verify_identity(self, *, source: str = "webcam") -> tuple[bool, float]:
        with self._lock:
            email = self.state.email
            deferred = self.state.identity_deferred_phone
        if not email:
            raise RuntimeError("Sign in before verifying your face")
        enrolled = self.identity_store.load(email)
        src = (source or "webcam").strip().lower()
        if src == "phone":
            sample = self._phone_face_embedding()
            if sample is None:
                raise RuntimeError(
                    "No face visible on the phone camera. Center your face and try again."
                )
            if enrolled is None:
                if deferred:
                    # First-time phone path: enroll from this verified sample.
                    self.identity_store.save(email, sample)
                    with self._lock:
                        self.state.identity_deferred_phone = False
                    return True, 1.0
                raise RuntimeError("Enroll your face before starting the exam.")
            return verify(enrolled, sample, threshold=self.settings.identity_match_threshold)

        if enrolled is None:
            raise RuntimeError("Enroll your face before starting the exam.")
        sample = self.monitor.identity_sample()
        if sample is None:
            raise RuntimeError("Face sample unavailable — look at the webcam and try again.")
        return verify(enrolled, sample, threshold=self.settings.identity_match_threshold)

    def _set_pause_reason(self, key: str, message: str) -> None:
        with self._lock:
            self.state.pause_reasons[key] = message
            self._recompute_pause_locked()

    def _clear_pause_reason(self, key: str) -> None:
        with self._lock:
            self.state.pause_reasons.pop(key, None)
            self._recompute_pause_locked()

    def _clear_all_pauses(self) -> None:
        with self._lock:
            self.state.pause_reasons.clear()
            self.state.quiz_paused = False
            self.state.pause_reason = ""

    def _recompute_pause_locked(self) -> None:
        """Caller must hold self._lock. Prefer phone/camera messages over focus/app."""
        reasons = self.state.pause_reasons
        if not reasons:
            self.state.quiz_paused = False
            self.state.pause_reason = ""
            return
        self.state.quiz_paused = True
        for key in ("phone", "camera", "app", "focus", "phone_motion"):
            if key in reasons:
                self.state.pause_reason = reasons[key]
                return
        self.state.pause_reason = next(iter(reasons.values()))

    # ── auth / exam bootstrap ──────────────────────────────────────────
    def login(self, email: str, password: str, *, display_name: str = "") -> dict[str, Any]:
        data = self.api.login(email, password)
        if data.get("role") != "student":
            raise PermissionError("Desktop exam client is for students only. Use Admin Web for staff.")
        typed_name = (display_name or "").strip()
        account_name = str(data.get("full_name") or "").strip()
        # Prefer the name the student typed (what admins should see on reports).
        shown_name = typed_name or account_name or email.split("@")[0]
        with self._lock:
            # Fresh login must not inherit a prior student's session / face flags.
            self.state = SessionState(
                phase="login",
                email=email,
                full_name=shown_name,
                role=data["role"],
            )
        # Open webcam early so enroll/setup does not race a cold camera open.
        if not self.monitor.snapshot.running:
            self.monitor.start("identity-enroll")
        return {
            "ok": True,
            "role": data["role"],
            "email": email,
            "full_name": self.state.full_name,
        }

    def _may_capture_screenshots(self) -> bool:
        """PC screen capture once an exam session is active (pairing or quiz)."""
        with self._lock:
            return self.state.phase in {"camera_setup", "exam"} and bool(self.state.session_id)

    def _arm_app_lock(self, *, student_message: str | None = None) -> list[str]:
        """Close blocked apps / other browsers and keep only the exam Edge/Chrome profile."""
        allowed = {os.getpid()}
        # Never relaunch the exam browser here. Edge/Chrome often reparents so the
        # original Popen pid dies while the window stays open; launching again opens
        # a second window that resets to the login screen (client complaint B3).
        living_pids = self.exam_shell.living_pids()
        allowed |= living_pids
        if self.exam_shell.pid:
            allowed.add(self.exam_shell.pid)
        marker = str(self.exam_shell.profile_dir.resolve())
        self.app_lock.set_protect_dev_tools(bool(getattr(self.settings, "app_lock_protect_dev", False)))
        self.app_lock.set_protected_cmdline_markers({marker})
        self.app_lock.set_allowed_pids(allowed)
        self.focus_guard.set_allowed_pids(allowed)
        # Always enforce hard/helper kills. Browser force-clear needs either a
        # known exam profile PID or a successful cmdline marker match so we do
        # not kill the exam window itself.
        killed_browsers: list[str] = []
        protected_ok = bool(living_pids) or bool(
            self.app_lock._protected_pids() - {os.getpid()}  # noqa: SLF001
        )
        if protected_ok:
            killed_browsers = self.app_lock.force_clear_other_browsers()
        self.app_lock.start()
        self.focus_guard.start()
        hits, killed = self.app_lock.enforce_once()
        # Retry browser clear once markers/pids settle (Edge reparent race).
        if not killed_browsers:
            time.sleep(0.35)
            living_pids = self.exam_shell.living_pids()
            if living_pids:
                allowed |= living_pids
                self.app_lock.set_allowed_pids(allowed)
                killed_browsers = self.app_lock.force_clear_other_browsers()
        killed_all = list(killed) + list(killed_browsers)
        if student_message:
            with self._lock:
                self.state.student_alert = student_message
        # Log as heartbeat only — closing apps at pairing must not look like cheating.
        self._append(
            "heartbeat",
            0.05,
            {
                "source": "app_lock_arm",
                "plain_language": (
                    "Closed blocked apps before phone pairing."
                    if killed_all
                    else "Exam lockdown started — other apps blocked."
                ),
                "gesture_label": "APP_LOCK",
                "app_hits": [{"name": h.name, "category": h.category} for h in hits],
                "killed": killed_all,
                "cheating_attempt": False,
            },
            sync_now=False,
        )
        return killed_all

    def _try_screen_capture(self) -> str | None:
        if not self._may_capture_screenshots():
            return None
        try:
            from intelliQuiz_desktop.runtime.evidence import capture_screen_data_uri

            return capture_screen_data_uri()
        except Exception:
            return None

    def list_exams(self) -> list[dict[str, Any]]:
        return self.api.list_exams()

    def start_exam(self, exam_id: str) -> dict[str, Any]:
        exam_meta = self.api.get_exam(exam_id)
        paper = self.api.get_exam_paper(exam_id)
        with self._lock:
            display_name = self.state.full_name
        session = self.api.create_session(
            exam_id,
            device_fingerprint(),
            display_name=display_name,
        )

        profile_id = exam_meta.get("proctoring_profile_id")
        if profile_id:
            try:
                profile = self.api.get_proctoring_profile(str(profile_id))
                self.monitor.apply_proctoring(
                    warn=float(profile.get("warn_threshold", 0.4)),
                    flag=float(profile.get("flag_threshold", 0.5)),
                    terminate=float(profile.get("terminate_threshold", 0.9)),
                )
                self.app_lock.apply_profile(
                    blacklist_csv=str(profile.get("blacklist_apps_csv") or ""),
                    strictness=str(profile.get("strictness") or "medium"),
                )
                require_android = bool(profile.get("require_android_camera", False))
            except Exception:
                require_android = False
        else:
            require_android = False

        # Phone is always required as a secondary camera, even when PC has a webcam.
        if self.settings.require_android_camera_always:
            require_android = True

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
            self.state.pause_reasons.clear()
            self.state.quiz_paused = False
            self.state.pause_reason = ""
            self.state.require_android_camera = require_android
            self.state.error = ""

        self.monitor.start(session["id"])
        self.sync.start(session["id"])
        pairing = self.pairing.begin_session(
            session_id=session["id"],
            pairing_token=session["pairing_token"],
            exam_code=paper.get("title"),
        )
        # Lock down immediately when entering phone pairing (not only at quiz start).
        killed = []
        try:
            killed = self._arm_app_lock(
                student_message=(
                    "Other apps closed. Scan the phone QR and keep IntelliQuiz open on your phone."
                )
            )
        except Exception:
            try:
                self.app_lock.enforce_once()
            except Exception:
                pass
        # Do not block the UI on network sync — flush in the background
        self._append("heartbeat", 0.0, {"source": "session_start"}, sync_now=False)
        return {
            "ok": True,
            "session_id": session["id"],
            "paper": paper,
            "pairing": pairing,
            "app_lock": self.app_lock.snapshot(),
            "require_android_camera": require_android,
            "apps_closed": killed,
        }

    def advance_to_pairing(self) -> dict[str, Any]:
        """Legacy alias — camera setup already includes phone QR."""
        with self._lock:
            self.state.phase = "camera_setup"
        return {"ok": True, "phase": "camera_setup", "pairing": self.pairing.status()}

    def confirm_camera(self, *, prefer_phone: bool = False) -> dict[str, Any]:
        """Hard gate: identity camera OK, and phone must stay paired as secondary camera.

        Rules:
        - PC has a working webcam → PC webcam identity is compulsory (phone alone is not enough).
        - PC has no webcam → phone camera identity is allowed.
        - Phone secondary pairing may still be required in both cases.
        """
        mon = self.monitor.status()
        pair = self.pairing.status()
        paired = bool(pair.get("paired") or self.state.android_paired)
        webcam_ok = bool(mon.get("camera_ok"))

        # Phone is mandatory even when the PC webcam is used for face identity.
        if self.settings.require_android_camera_always and not paired:
            raise RuntimeError(
                "Phone camera must be paired before starting. Scan the QR with your phone "
                "and keep the IntelliQuiz camera app open during the exam."
            )

        # Phone-only identity is allowed only when this PC has no working webcam.
        if prefer_phone or (not webcam_ok and paired):
            if webcam_ok:
                raise RuntimeError(
                    "This PC has a webcam. Center one face on the PC camera, then pair your phone."
                )
            if not paired:
                raise RuntimeError(
                    "Phone camera is not paired yet. Scan the QR with your phone and wait for the green lock."
                )
            matched, score = self._verify_identity(source="phone")
            if not matched:
                raise RuntimeError(
                    f"Face identity mismatch on phone ({score:.0%} match). "
                    "Center your enrolled face or re-enroll from the login step."
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
                {
                    "source": "confirm_camera",
                    "identity_source": "phone",
                    "android_paired": True,
                    "identity_score": score,
                },
                sync_now=False,
            )
            return {
                "ok": True,
                "identity_source": "phone",
                "face_verified": True,
                "pairing": pair,
                "monitor": mon,
            }

        if not webcam_ok:
            raise RuntimeError(
                "No webcam detected on this PC. Switch to “Use phone camera” and scan the QR code."
            )
        if int(mon.get("face_count") or 0) != 1:
            raise RuntimeError(
                "Show exactly one face, centered and well lit, then try again."
            )

        matched, score = self._verify_identity(source="webcam")
        if not matched:
            raise RuntimeError(
                f"Face identity mismatch ({score:.0%} match). Use your enrolled face or re-enroll from the login step."
            )

        with self._lock:
            self.state.face_verified = True
            self.state.identity_source = "webcam"
            self.state.android_paired = paired
            self.state.phase = "camera_setup"
            self.state.error = ""
        self._append(
            "heartbeat",
            0.0,
            {
                "source": "confirm_camera",
                "identity_source": "webcam",
                "face_count": mon.get("face_count"),
                "identity_score": score,
                "android_paired": paired,
            },
            sync_now=False,
        )
        return {
            "ok": True,
            "identity_source": "webcam",
            "face_verified": True,
            "pairing": pair,
            "monitor": mon,
        }

    def enter_exam(self, *, require_pair: bool | None = None) -> dict[str, Any]:
        if require_pair is None:
            require_pair = self.state.require_android_camera or self.settings.require_android_camera_always
        status = self.pairing.status()
        paired = bool(status.get("paired") or self.state.android_paired)

        # Auto-confirm if setup was skipped — still require a real identity match.
        if not self.state.face_verified:
            mon = self.monitor.status()
            webcam_ok = bool(mon.get("camera_ok"))
            face_ok = webcam_ok and int(mon.get("face_count") or 0) == 1
            if webcam_ok:
                if not face_ok:
                    raise RuntimeError(
                        "This PC has a webcam. Complete the PC face check before starting the quiz."
                    )
                matched, score = self._verify_identity(source="webcam")
                if not matched:
                    raise RuntimeError(
                        f"Face identity mismatch ({score:.0%} match). Complete camera setup again."
                    )
                with self._lock:
                    self.state.face_verified = True
                    self.state.identity_source = "webcam"
            elif paired:
                matched, score = self._verify_identity(source="phone")
                if not matched:
                    raise RuntimeError(
                        f"Face identity mismatch on phone ({score:.0%} match). Complete camera setup again."
                    )
                with self._lock:
                    self.state.face_verified = True
                    self.state.identity_source = self.state.identity_source or "phone"
            else:
                raise RuntimeError(
                    "Complete camera setup first: pass the webcam face check, or pair your phone camera."
                )

        if require_pair and not paired:
            raise RuntimeError("Phone camera must be paired before starting the quiz")

        # Re-arm lockdown (pairing already started it; refresh allowed PIDs / browsers).
        killed = self._arm_app_lock(
            student_message=(
                "Exam started. Keep this window open. Do not open Chrome, Edge, or helper apps."
            )
        )
        with self._lock:
            self.state.phase = "exam"
            self.state.android_paired = paired
            self.state.pause_reasons.clear()
            self.state.quiz_paused = False
            self.state.pause_reason = ""
            if not self.state.student_alert:
                self.state.student_alert = (
                    "Exam started. Keep this window open. Do not open Chrome, Edge, or helper apps."
                )
        self._start_heartbeat()
        self._append(
            "heartbeat",
            0.05,
            {
                "source": "enter_exam",
                "android_paired": self.state.android_paired,
                "identity_source": self.state.identity_source,
                "killed": killed,
            },
            sync_now=False,
        )
        return {
            "ok": True,
            "phase": "exam",
            "paper": self.state.paper,
            "identity_source": self.state.identity_source,
            "app_lock": self.app_lock.snapshot(),
            "monitor": self.monitor.status(),
            "student_alert": self.state.student_alert,
        }

    def save_answer(self, question_id: str, choice_index: int) -> dict[str, Any]:
        self._refresh_pause_state()
        if self.state.quiz_paused:
            raise RuntimeError(self.state.pause_reason or "Quiz paused — restore camera access first")
        with self._lock:
            self.state.answers[question_id] = int(choice_index)
        return {"ok": True, "answers": dict(self.state.answers)}

    def submit(self, *, force: bool = False) -> dict[str, Any]:
        self._refresh_pause_state()
        if self.state.quiz_paused and not force:
            raise RuntimeError(
                (self.state.pause_reason or "Quiz paused — restore camera access first")
                + " You can force-submit if the camera cannot be restored."
            )
        with self._lock:
            sid = self.state.session_id
            answers = dict(self.state.answers)
            risk = self.monitor.snapshot.session_risk
            paused = self.state.quiz_paused
        if not sid:
            raise RuntimeError("No active session")
        if paused:
            self._append(
                "no_face",
                0.75,
                {
                    "source": "desktop",
                    "plain_language": "Exam submitted while identity camera was unavailable.",
                    "gesture_label": "SUBMIT_WHILE_PAUSED",
                },
                sync_now=False,
            )
        sync_result = self._append(
            "submit",
            float(risk),
            {
                "answers": answers,
                "submitted_at": datetime.now(UTC).isoformat(),
                "session_risk": risk,
                "submitted_while_paused": paused,
            },
            sync_now=True,
        )
        # Extra flush until local queue is empty or we hit a hard error.
        try:
            extra = self.sync.flush(sid)
            if isinstance(sync_result, dict) and isinstance(extra, dict):
                sync_result = {
                    "accepted": int(sync_result.get("accepted", 0)) + int(extra.get("accepted", 0)),
                    "duplicates": int(sync_result.get("duplicates", 0))
                    + int(extra.get("duplicates", 0)),
                    "rejected": int(sync_result.get("rejected", 0)) + int(extra.get("rejected", 0)),
                    "flushed": int(sync_result.get("flushed", 0)) + int(extra.get("flushed", 0)),
                    "error": extra.get("error") or sync_result.get("error"),
                }
            else:
                sync_result = extra
        except Exception as exc:
            if isinstance(sync_result, dict):
                sync_result["error"] = str(exc)
        sync_ok = not (isinstance(sync_result, dict) and sync_result.get("error"))
        still_pending = bool(self.store.unsynced(sid, limit=1))
        if still_pending:
            sync_ok = False
            if isinstance(sync_result, dict):
                sync_result.setdefault(
                    "error",
                    "Submit saved locally but not fully synced — keep this window open.",
                )
        try:
            self.api.heartbeat(sid, risk_score=float(risk), android_paired=self.state.android_paired)
        except Exception:
            pass
        result = self._load_result(sid, risk=float(risk))
        with self._lock:
            self.state.phase = "submitted"
            self.state.last_result = result
        # Keep the exam Edge/Chrome window alive so the result screen can render.
        self.shutdown_runtime(keep_store=True, close_exam_shell=False)
        return {
            "ok": True,
            "sync": sync_result,
            "sync_ok": sync_ok,
            "answers": answers,
            "risk": risk,
            "forced": paused,
            "result": result,
        }

    def get_last_result(self) -> dict[str, Any]:
        with self._lock:
            if self.state.last_result:
                return dict(self.state.last_result)
            sid = self.state.session_id
        if not sid:
            raise RuntimeError("No submitted attempt yet")
        result = self._load_result(sid)
        with self._lock:
            self.state.last_result = result
        return result

    def list_my_results(self) -> list[dict[str, Any]]:
        return self.api.list_my_attempts()

    def prepare_another_exam(self, *, clear_local: bool = True) -> dict[str, Any]:
        """Keep the student signed in; clear the finished attempt so they can pick another exam."""
        with self._lock:
            if not self.state.email:
                raise RuntimeError("Sign in first")
            old_sid = self.state.session_id
            email = self.state.email
            full_name = self.state.full_name
            role = self.state.role

        cleared = False
        if clear_local and old_sid:
            cleared = self._clear_local_session_artifacts(old_sid, require_synced=True)

        # Keep the exam browser open — student picks the next exam in the same window.
        self.shutdown_runtime(keep_store=True, close_exam_shell=False)
        with self._lock:
            self.state = SessionState(
                phase="login",
                email=email,
                full_name=full_name,
                role=role,
            )
        return {
            "ok": True,
            "email": email,
            "full_name": full_name,
            "cleared_local": cleared,
            "storage_hint": self._storage_hint(),
        }

    def logout(self, *, clear_local: bool = True) -> dict[str, Any]:
        with self._lock:
            old_sid = self.state.session_id
        if clear_local and old_sid:
            self._clear_local_session_artifacts(old_sid, require_synced=True)
        # Keep window for login screen; process exit closes the shell.
        self.shutdown_runtime(keep_store=True, close_exam_shell=False)
        with self._lock:
            self.state = SessionState()
        self.api.token = None
        return {"ok": True, "storage_hint": self._storage_hint()}

    def storage_info(self) -> dict[str, Any]:
        return self._storage_hint()

    # ── status ─────────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        self._refresh_pause_state()
        identity = self.identity_status()
        monitor = self.monitor.status()
        pairing = self.pairing.status()
        app_lock = self.app_lock.snapshot()
        focus = self.focus_guard.snapshot()
        storage = self._storage_hint()
        try:
            from intelliQuiz_desktop.build_info import BUILD_SHA, BUILD_TIME
        except Exception:
            BUILD_SHA, BUILD_TIME = "dev", "local"
        with self._lock:
            st = self.state
            return {
                "build_sha": BUILD_SHA,
                "build_time": BUILD_TIME,
                "phase": st.phase,
                "email": st.email,
                "full_name": st.full_name,
                "exam_id": st.exam_id,
                "exam_title": st.exam_title,
                "session_id": st.session_id,
                "android_paired": st.android_paired or pairing.get("paired"),
                "face_verified": st.face_verified,
                "identity_source": st.identity_source,
                "quiz_paused": st.quiz_paused,
                "pause_reason": st.pause_reason,
                "student_alert": st.student_alert,
                "answers": dict(st.answers),
                "error": st.error,
                "started_at": st.started_at,
                "paper": st.paper,
                "last_result": dict(st.last_result) if st.last_result else None,
                "monitor": monitor,
                "app_lock": app_lock,
                "focus_guard": focus,
                "identity": identity,
                "pairing": pairing,
                "ai_ready": self.engine.ready,
                "storage": storage,
            }

    def resume_after_camera(self) -> dict[str, Any]:
        """Clear pause once the required camera is healthy again."""
        self._refresh_pause_state()
        # If prohibited apps are gone, drop the app pause channel.
        try:
            hits, _ = self.app_lock.enforce_once()
            if not hits:
                self._clear_pause_reason("app")
        except Exception:
            pass
        if self.state.quiz_paused:
            raise RuntimeError(self.state.pause_reason or "Camera is still unavailable")
        with self._lock:
            self.state.student_alert = ""
        return {"ok": True, "quiz_paused": False}

    def mark_phone_paired(self) -> dict[str, Any]:
        if not self.settings.allow_lab_bypasses:
            raise PermissionError("Lab pairing bypass is disabled")
        self.pairing.mark_paired_local()
        return self.pairing.status()

    def simulate_abnormal(self) -> dict[str, Any]:
        """Lab helper: force an evidence capture as if ML fired."""
        if not self.settings.allow_lab_bypasses:
            raise PermissionError("Lab simulate endpoint is disabled")
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

    def reconnect_camera(self) -> dict[str, Any]:
        """UI Retry: force-release and reopen the PC webcam."""
        with self._lock:
            sid = self.state.session_id or "camera-reconnect"
        return self.monitor.restart(sid)

    def shutdown_runtime(
        self,
        *,
        keep_store: bool = False,
        close_exam_shell: bool = True,
    ) -> None:
        self._hb_stop.set()
        self.focus_guard.stop()
        self.app_lock.stop()
        if close_exam_shell:
            self.exam_shell.close()
        self.monitor.stop()
        self.pairing.stop()
        try:
            with self._lock:
                sid = self.state.session_id
            if sid:
                self.sync.request_flush(sid)
            self.sync.stop(wait=False)
        except Exception:
            pass
        shutdown_workers(wait=False)
        if not keep_store:
            self.store.close()
            self.api.close()

    def _load_result(self, session_id: str, *, risk: float | None = None) -> dict[str, Any]:
        try:
            data = self.api.get_session_result(session_id)
            if risk is not None and not data.get("last_risk_score"):
                data["last_risk_score"] = float(risk)
            return data
        except Exception as exc:
            return {
                "session_id": session_id,
                "exam_id": self.state.exam_id,
                "exam_title": self.state.exam_title,
                "status": "submitted",
                "quiz_score": None,
                "quiz_max_score": None,
                "quiz_percent": None,
                "last_risk_score": float(risk if risk is not None else self.monitor.snapshot.session_risk),
                "error": str(exc),
            }

    def _storage_hint(self) -> dict[str, Any]:
        data_dir = Path(self.settings.data_dir)
        return {
            "local_events_db": str(data_dir / "events.db"),
            "local_evidence_dir": str(data_dir / "evidence"),
            "server_database": "Backend SQLite (intelliquiz.dev.db) — exam_sessions + integrity_events",
            "admin_review": "Admin Web → Attempts & flags / Reports",
            "note": (
                "Official scores and evidence live on the server. "
                "Taking another exam clears this PC’s local copy for the finished session; "
                "server records stay for admin review."
            ),
        }

    def _clear_local_session_artifacts(
        self,
        session_id: str,
        *,
        require_synced: bool = False,
    ) -> bool:
        """Delete local session rows. When require_synced, flush first and refuse if still pending."""
        if require_synced:
            try:
                self.sync.flush(session_id)
            except Exception:
                pass
            if self.store.unsynced(session_id, limit=1):
                raise RuntimeError(
                    "Cannot clear local exam data — answers/events are not synced to the server yet. "
                    "Check your network and try again."
                )
        try:
            self.store.delete_session(session_id)
        except Exception:
            pass
        evidence_dir = Path(self.settings.data_dir) / "evidence"
        if evidence_dir.exists():
            prefix = f"{session_id[:8]}_"
            try:
                for path in evidence_dir.iterdir():
                    if path.name.startswith(prefix):
                        try:
                            path.unlink(missing_ok=True)
                        except Exception:
                            pass
            except Exception:
                pass
        return True

    # ── internal event plumbing ────────────────────────────────────────
    def _append(
        self,
        typ: str,
        severity: float,
        payload: dict[str, Any],
        *,
        sync_now: bool = False,
    ) -> dict[str, Any]:
        """Persist locally; default is async flush so camera/WS loops never block on HTTP."""
        sid = self.state.session_id
        if not sid:
            return {"accepted": 0, "duplicates": 0, "rejected": 0, "flushed": 0}
        # Skip fake enroll-* session IDs — server would reject them forever.
        if sid.startswith("enroll-") or sid.startswith("camera-"):
            return {"accepted": 0, "duplicates": 0, "rejected": 0, "flushed": 0, "skipped": True}
        enriched = {
            **payload,
            "student_name": self.state.full_name or self.state.email,
            "student_email": self.state.email,
            "exam_title": self.state.exam_title,
            "session_id": sid,
        }
        self.store.append(session_id=sid, type=typ, severity=severity, payload=enriched)

        if not sync_now:
            self.sync.request_flush(sid)
            return {"accepted": 0, "duplicates": 0, "rejected": 0, "flushed": 0, "deferred": True}
        fut = submit_sync(self.sync.flush, sid)
        try:
            return fut.result(timeout=20)
        except Exception as exc:
            return {"accepted": 0, "duplicates": 0, "rejected": 0, "flushed": 0, "error": str(exc)}

    def _on_integrity_event(self, typ: str, severity: float, payload: dict[str, Any]) -> None:
        enriched = dict(payload)
        label = str(enriched.get("gesture_label") or "")
        plain = str(
            enriched.get("plain_language")
            or "Suspicious activity detected."
        )
        # Quiet pair snapshot — store photo only, no pause / cheating flag.
        if typ == "android_snapshot" or enriched.get("capture_reason") == "android_pair_snapshot":
            enriched.setdefault("cheating_attempt", False)
            self._append(typ, severity, enriched)
            return

        # Phone left the exam camera app — attach PC screen snapshot for admin review.
        if label in {"PHONE_APP_SWITCH", "PHONE_HELPER", "APP_SWITCH", "PHONE_MOTION"} or typ == "android_env_anomaly":
            if not enriched.get("screen_image_data_uri"):
                screen = self._try_screen_capture()
                if screen:
                    enriched["screen_image_data_uri"] = screen
            if not enriched.get("image_data_uri"):
                jpeg = self.pairing.latest_jpeg()
                if jpeg:
                    import base64

                    enriched["image_data_uri"] = (
                        "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
                    )
            enriched.setdefault(
                "plain_language",
                "Phone camera moved away or left the exam page.",
            )
            enriched.setdefault("cheating_attempt", True)
            enriched.setdefault("flag", "phone_helper_app")
            if self.state.phase == "exam" and severity >= 0.6:
                self._set_pause_reason(
                    "phone_motion",
                    "Phone camera moved or left. Keep the IntelliQuiz camera page open.",
                )
                with self._lock:
                    self.state.student_alert = (
                        "Phone camera issue — keep the page open and steady."
                    )
            elif self.state.phase == "exam" and severity >= 0.45:
                with self._lock:
                    self.state.student_alert = (
                        "Phone camera warning — photo saved for admin review."
                    )
        elif self.state.phase == "exam" and severity >= 0.45:
            with self._lock:
                self.state.student_alert = plain[:120] if plain else "Warning — photo saved for admin review."
        self._append(typ, severity, enriched)

    def _on_paired(self) -> None:
        with self._lock:
            self.state.android_paired = True
        if self.state.phase == "exam":
            self._clear_pause_reason("phone")
            self._clear_pause_reason("phone_motion")
        self._append(
            "heartbeat",
            0.0,
            {"source": "android_paired", "android_paired": True},
            sync_now=False,
        )

    def _on_unpaired(self) -> None:
        with self._lock:
            phase = self.state.phase
            require_phone = (
                self.settings.require_android_camera_always
                or self.state.require_android_camera
                or self.state.identity_source == "phone"
            )
            self.state.android_paired = False

        # Only pause / flag during the live exam — not setup, enrollment, or after submit.
        if phase != "exam" or not require_phone:
            return

        self._set_pause_reason(
            "phone",
            "Phone disconnected. Open IntelliQuiz on phone, scan QR again, keep page open.",
        )
        with self._lock:
            self.state.student_alert = "Phone camera lost — quiz paused. Re-pair to continue."

        enriched: dict[str, Any] = {
            "source": "android_camera",
            "plain_language": "Phone camera disconnected during the exam (cheating risk).",
            "gesture_label": "PHONE_LOST",
            "cheating_attempt": True,
            "flag": "phone_disconnected",
        }
        screen = self._try_screen_capture()
        if screen:
            enriched["screen_image_data_uri"] = screen
        jpeg = self.pairing.latest_jpeg() or self.monitor.latest_jpeg()
        if jpeg:
            import base64

            enriched["image_data_uri"] = (
                "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
            )
        self._append("no_face", 0.85, enriched, sync_now=False)

    def _refresh_pause_state(self) -> None:
        """Update camera/phone pause channels only — never wipe focus/app pauses."""
        with self._lock:
            if self.state.phase != "exam":
                return
            source = self.state.identity_source
            require_phone = self.settings.require_android_camera_always or self.state.require_android_camera

        pair = self.pairing.status()
        phone_ok = bool(pair.get("paired") and (pair.get("camera_live") or pair.get("android_frames", 0) > 0))
        if not pair.get("paired"):
            phone_ok = False

        if require_phone and not phone_ok:
            with self._lock:
                self.state.android_paired = False
            self._set_pause_reason(
                "phone",
                "Phone camera required. Open IntelliQuiz on phone → Allow camera → Wait for Paired.",
            )
        elif phone_ok:
            with self._lock:
                self.state.android_paired = True
            self._clear_pause_reason("phone")

        if source == "phone":
            if not phone_ok:
                self._set_pause_reason(
                    "phone",
                    "Phone camera required. Open QR link → Allow camera → Wait for Paired.",
                )
            # Phone-identity exams do not use the PC webcam pause channel.
            self._clear_pause_reason("camera")
            return

        mon = self.monitor.status()
        ok = bool(mon.get("camera_ok"))
        if not ok:
            self._set_pause_reason(
                "camera",
                "PC webcam lost. Reconnect or allow camera, then continue.",
            )
        else:
            self._clear_pause_reason("camera")

    def _flush_pending_sync(self) -> None:
        try:
            for sid in self.store.pending_session_ids():
                self.sync.request_flush(sid)
        except Exception:
            pass

    def _on_focus_away(self, process_name: str) -> None:
        with self._lock:
            if self.state.phase != "exam":
                return
        self._set_pause_reason(
            "focus",
            f"Another app took focus ({process_name}). Return to the exam.",
        )
        self._append(
            "app_violation",
            0.65,
            {
                "source": "focus_guard",
                "plain_language": f"Student switched away from exam to {process_name}.",
                "foreground_process": process_name,
            },
            sync_now=False,
        )

    def _on_focus_return(self) -> None:
        with self._lock:
            if self.state.phase != "exam":
                return
        self._clear_pause_reason("focus")

    def _on_app_violation(self, hits: list[ProcessHit], killed: list[str]) -> None:
        if not hits:
            return
        # During phone pairing we still close apps, but do not file cheating reports.
        with self._lock:
            phase = self.state.phase
        if phase != "exam":
            return
        hard = [h for h in hits if h.category == "hard"]
        browsers = [h for h in hits if h.category == "browser"]
        severity = 0.9 if hard else (0.75 if browsers else 0.55)
        names = sorted({h.name for h in hits})
        self._set_pause_reason(
            "app",
            "Prohibited app detected. Close helper apps and return here.",
        )
        with self._lock:
            self.state.student_alert = (
                "Prohibited app: " + ", ".join(names) + ". Photo saved for admin."
            )
        payload: dict[str, Any] = {
            "hits": [{"name": h.name, "pid": h.pid, "category": h.category} for h in hits],
            "killed": killed,
            "plain_language": (
                "Blocked app during exam: " + ", ".join(names) + "."
            ),
            "source": "desktop_app_lock",
            "gesture_label": "APP_VIOLATION",
            "cheating_attempt": True,
            "flag": "prohibited_app",
        }
        screen = self._try_screen_capture()
        if screen:
            payload["screen_image_data_uri"] = screen
        try:
            jpeg = self.monitor.latest_jpeg()
            if jpeg:
                import base64

                payload["image_data_uri"] = (
                    "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
                )
        except Exception:
            pass
        self._append("app_violation", severity, payload, sync_now=False)

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
                        # Slim monitor snapshot — never embed evidence images in heartbeats
                        "monitor": self.monitor.status(include_evidence=False),
                        "app_lock": self.app_lock.snapshot(),
                        "android_paired": paired,
                        "pairing_frames": self.pairing.status().get("android_frames", 0),
                    },
                )
                self.sync.request_flush(sid)

        self._hb_thread = threading.Thread(target=loop, name="heartbeat", daemon=True)
        self._hb_thread.start()
