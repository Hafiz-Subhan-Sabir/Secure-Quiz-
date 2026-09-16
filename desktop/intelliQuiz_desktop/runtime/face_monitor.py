"""Continuous webcam monitor — landmarks → ML → evidence on abnormal behavior."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from intelliQuiz_desktop.ai.engine import FrameAnalysis, OnDeviceAIEngine
from intelliQuiz_desktop.ai.landmarks import FaceLandmarkerBundle
from intelliQuiz_desktop.core.config import DesktopSettings, get_settings
from intelliQuiz_desktop.runtime.evidence import EvidenceBundle, capture_evidence, evidence_payload


@dataclass
class MonitorSnapshot:
    running: bool = False
    camera_ok: bool = False
    ai_ready: bool = False
    face_count: int = 0
    last_gesture: str = ""
    last_risk: float = 0.0
    session_risk: float = 0.0
    looking_away: bool = False
    yaw: float = 0.0
    message: str = "Idle"
    evidence_count: int = 0
    last_evidence: list[dict[str, Any]] = field(default_factory=list)


class FaceMonitor:
    """Owns the primary webcam during the exam.

    Loop:
      capture frame → MediaPipe Face Landmarker → 1404 features → RF model
      → risk score. If risk ≥ threshold (or no/multi face / gaze away),
      capture webcam JPEG + screen snapshot and emit an integrity event.
    """

    def __init__(
        self,
        engine: OnDeviceAIEngine,
        *,
        settings: DesktopSettings | None = None,
        on_event: Callable[[str, float, dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.engine = engine
        self.on_event = on_event
        self.snapshot = MonitorSnapshot(ai_ready=engine.ready)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._latest_bgr: np.ndarray | None = None
        self._landmarker: FaceLandmarkerBundle | None = None
        self._session_id: str = ""
        self._last_capture_at = 0.0
        self._last_soft_log_at = 0.0
        self._ema_risk = 0.0
        self._prev_yaw: float | None = None
        self._warn_threshold = 0.4
        self._terminate_threshold = 0.9
        self._last_terminate_at = 0.0
        self._latest_identity_features: np.ndarray | None = None

    def apply_proctoring(self, *, warn: float, flag: float, terminate: float) -> None:
        """Apply server proctoring profile thresholds."""
        self._warn_threshold = float(warn)
        self._terminate_threshold = float(terminate)
        self.settings.gesture_capture_threshold = float(flag)

    def start(self, session_id: str) -> None:
        self._session_id = session_id
        # Allow restart after a previous exam stop()
        if self._thread and self._thread.is_alive():
            return
        self._thread = None
        self._stop.clear()
        self._last_capture_at = 0.0
        self._last_soft_log_at = 0.0
        self._ema_risk = 0.0
        self._prev_yaw = None
        with self._lock:
            self.snapshot.running = True
            self.snapshot.camera_ok = False
            self.snapshot.face_count = 0
            self.snapshot.last_gesture = ""
            self.snapshot.last_risk = 0.0
            self.snapshot.session_risk = 0.0
            self.snapshot.looking_away = False
            self.snapshot.message = "Starting webcam…"
            self.snapshot.evidence_count = 0
            self.snapshot.last_evidence = []
            self._latest_jpeg = None
            self._latest_bgr = None
        self._thread = threading.Thread(target=self._loop, name="face-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if self._landmarker:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
        with self._lock:
            self.snapshot.running = False
            self.snapshot.camera_ok = False
            self.snapshot.message = "Stopped"
            self._latest_jpeg = None
            self._latest_bgr = None

    def status(self, *, include_evidence: bool = True) -> dict[str, Any]:
        with self._lock:
            s = self.snapshot
            out = {
                "running": s.running,
                "camera_ok": s.camera_ok,
                "ai_ready": s.ai_ready,
                "face_count": s.face_count,
                "last_gesture": s.last_gesture,
                "last_risk": round(s.last_risk, 3),
                "session_risk": round(s.session_risk, 3),
                "looking_away": s.looking_away,
                "yaw": round(s.yaw, 3),
                "message": s.message,
                "evidence_count": s.evidence_count,
            }
            if include_evidence:
                out["last_evidence"] = list(s.last_evidence[:6])
            else:
                out["last_evidence"] = []
            return out

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def identity_sample(self) -> np.ndarray | None:
        with self._lock:
            if self._latest_identity_features is None:
                return None
            return self._latest_identity_features.copy()

    def force_capture(
        self,
        reason: str = "manual_review",
        *,
        gesture_label: str = "MANUAL",
        plain_language: str | None = None,
        severity: float = 0.7,
        event_type: str = "gesture_risk",
    ) -> dict[str, Any]:
        with self._lock:
            frame = None if self._latest_bgr is None else self._latest_bgr.copy()
        if frame is None:
            # Lab / no-camera path: synthesize a labeled frame so evidence pipeline still works
            import cv2
            import numpy as np

            frame = np.zeros((360, 480, 3), dtype=np.uint8)
            frame[:] = (28, 42, 36)
            cv2.putText(
                frame,
                reason[:40],
                (24, 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (220, 240, 230),
                2,
                cv2.LINE_AA,
            )
        bundle = capture_evidence(
            frame,
            evidence_dir=self.settings.data_dir / "evidence",
            session_id=self._session_id or "nosession",
            reason=reason,
            include_screen=True,
        )
        payload = evidence_payload(
            bundle,
            gesture_label=gesture_label,
            plain_language=plain_language or f"Manual evidence capture: {reason}",
        )
        self._record_evidence(payload, severity=severity, event_type=event_type)
        with self._lock:
            self.snapshot.last_risk = max(self.snapshot.last_risk, severity)
            self.snapshot.session_risk = max(self.snapshot.session_risk, severity)
            self.snapshot.last_gesture = gesture_label
            self.snapshot.message = plain_language or self.snapshot.message
        return payload

    def _loop(self) -> None:
        import cv2

        try:
            self._landmarker = FaceLandmarkerBundle(self.settings.face_landmarker_path)
        except Exception as exc:
            with self._lock:
                self.snapshot.message = f"Face landmarker failed: {exc}"
                self.snapshot.camera_ok = False
            return

        cap = None
        # Open webcam with a hard timeout — Windows drivers can hang forever with no camera
        opened: list = []

        def _open_cam() -> None:
            import cv2 as _cv2

            for backend in (getattr(_cv2, "CAP_MSMF", 700), getattr(_cv2, "CAP_DSHOW", 700), 0):
                if self._stop.is_set():
                    return
                try:
                    trial = _cv2.VideoCapture(self.settings.camera_index, backend)
                    if trial.isOpened():
                        opened.append(trial)
                        return
                    trial.release()
                except Exception:
                    continue
            try:
                trial = _cv2.VideoCapture(self.settings.camera_index)
                if trial.isOpened():
                    opened.append(trial)
                else:
                    trial.release()
            except Exception:
                pass

        opener = threading.Thread(target=_open_cam, name="webcam-open", daemon=True)
        opener.start()
        opener.join(timeout=4.0)
        if opened:
            cap = opened[0]
        if cap is None or not cap.isOpened():
            with self._lock:
                self.snapshot.message = "Webcam unavailable"
                self.snapshot.camera_ok = False
                self.snapshot.running = True
            return

        # Prefer a modest resolution for stable FPS on student laptops
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        with self._lock:
            self.snapshot.camera_ok = True
            self.snapshot.message = "Monitoring"

        interval = 1.0 / max(0.5, self.settings.monitor_fps)
        fail_reads = 0
        try:
            while not self._stop.is_set():
                t0 = time.time()
                ok, frame = cap.read()
                if not ok or frame is None:
                    fail_reads += 1
                    if fail_reads >= 8:
                        with self._lock:
                            self.snapshot.camera_ok = False
                            self.snapshot.message = "Webcam lost — reconnect camera"
                    time.sleep(0.2)
                    continue

                fail_reads = 0
                with self._lock:
                    self.snapshot.camera_ok = True

                # Preview jpeg (downscale for UI bandwidth)
                preview = frame
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640 / w
                    preview = cv2.resize(frame, (640, int(h * scale)))
                ok_j, buf = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ok_j:
                    with self._lock:
                        self._latest_jpeg = buf.tobytes()
                        self._latest_bgr = frame

                try:
                    result = self._landmarker.detect_bgr(frame)
                    faces = list(result.face_landmarks or [])
                    if len(faces) == 1:
                        try:
                            from intelliQuiz_desktop.ai.landmarks import landmarks_to_features
                            from intelliQuiz_desktop.security.identity import embedding_from_features

                            feat = landmarks_to_features(faces[0])
                            with self._lock:
                                self._latest_identity_features = embedding_from_features(feat)
                        except Exception:
                            pass
                    analysis = self.engine.analyze_landmarks(faces)
                    self._handle_analysis(frame, analysis)
                except Exception as exc:
                    with self._lock:
                        self.snapshot.message = f"Analyze error: {exc}"

                elapsed = time.time() - t0
                time.sleep(max(0.0, interval - elapsed))
        finally:
            cap.release()
            with self._lock:
                self.snapshot.camera_ok = False
                self.snapshot.message = "Webcam stopped"

    def _handle_analysis(self, frame: np.ndarray, analysis: FrameAnalysis) -> None:
        pred = analysis.prediction
        risk = float(pred.risk) if pred else 0.0

        # Sudden head movement (not sitting still facing the screen)
        if self._prev_yaw is not None and abs(analysis.yaw - self._prev_yaw) > 0.18:
            if pred is None or risk < 0.75:
                from intelliQuiz_desktop.ai.engine import GesturePrediction

                pred = GesturePrediction(
                    label=-4,
                    name="HEAD_MOVE",
                    risk=0.78,
                    latency_ms=pred.latency_ms if pred else 0.0,
                    plain_language="Sudden head movement — not sitting still facing the screen.",
                    source="heuristic",
                )
                risk = pred.risk
                analysis.looking_away = True
        self._prev_yaw = analysis.yaw

        self._ema_risk = (0.65 * self._ema_risk) + (0.35 * risk)

        with self._lock:
            self.snapshot.face_count = analysis.face_count
            self.snapshot.looking_away = analysis.looking_away
            self.snapshot.yaw = analysis.yaw
            self.snapshot.last_risk = risk
            self.snapshot.session_risk = max(self.snapshot.session_risk, self._ema_risk)
            if pred:
                self.snapshot.last_gesture = pred.name
                self.snapshot.message = pred.plain_language
            self.snapshot.ai_ready = self.engine.ready
            if (
                self._ema_risk >= self._terminate_threshold
                and self.on_event
                and (now - self._last_terminate_at) >= 60.0
            ):
                self._last_terminate_at = now
                self.on_event(
                    "gesture_risk",
                    self._ema_risk,
                    {
                        "gesture_label": "TERMINATE_THRESHOLD",
                        "plain_language": "Risk exceeded exam terminate threshold — session flagged.",
                        "source": "primary_webcam",
                        "terminate_threshold": self._terminate_threshold,
                    },
                )

        if pred is None:
            return

        if pred.name == "NO_FACE":
            event_type = "no_face"
        elif pred.name == "MULTI_FACE":
            event_type = "multi_face"
        elif pred.name in ("GAZE_AWAY", "HEAD_MOVE"):
            event_type = "gaze_away"
        else:
            event_type = "gesture_risk"

        should_capture = risk >= self.settings.gesture_capture_threshold or analysis.looking_away
        now = time.time()
        cooled = (now - self._last_capture_at) >= self.settings.capture_cooldown_sec

        if should_capture and cooled:
            self._last_capture_at = now
            bundle = capture_evidence(
                frame,
                evidence_dir=self.settings.data_dir / "evidence",
                session_id=self._session_id or "nosession",
                reason=pred.name,
                include_screen=True,
            )
            payload = evidence_payload(
                bundle,
                gesture_label=pred.name,
                plain_language=pred.plain_language,
            )
            payload["yaw"] = analysis.yaw
            payload["pitch"] = analysis.pitch
            payload["source_detector"] = pred.source
            self._record_evidence(payload, severity=risk, event_type=event_type)
        elif self.on_event and risk >= self._warn_threshold and (now - self._last_soft_log_at) >= 20.0:
            # Soft integrity log without heavy images (still visible in admin timeline)
            self._last_soft_log_at = now
            self.on_event(
                event_type,
                risk,
                {
                    "gesture_label": pred.name,
                    "plain_language": pred.plain_language,
                    "source": "primary_webcam",
                    "source_detector": pred.source,
                    "yaw": analysis.yaw,
                    "pitch": analysis.pitch,
                    "soft_log": True,
                },
            )

    def _record_evidence(self, payload: dict[str, Any], *, severity: float, event_type: str) -> None:
        thumb = {
            "gesture_label": payload.get("gesture_label"),
            "plain_language": payload.get("plain_language"),
            "image_data_uri": payload.get("image_data_uri"),
            "screen_image_data_uri": payload.get("screen_image_data_uri"),
            "severity": severity,
            "type": event_type,
        }
        with self._lock:
            self.snapshot.evidence_count += 1
            self.snapshot.last_evidence.insert(0, thumb)
            self.snapshot.last_evidence = self.snapshot.last_evidence[:8]
        if self.on_event:
            self.on_event(event_type, severity, payload)
