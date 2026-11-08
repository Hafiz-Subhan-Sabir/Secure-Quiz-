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
from intelliQuiz_desktop.runtime.evidence import capture_evidence, evidence_payload
from intelliQuiz_desktop.runtime.workers import submit_io


@dataclass
class MonitorSnapshot:
    running: bool = False
    camera_ok: bool = False
    camera_phase: str = "idle"  # idle|opening|ready|busy|failed|stopped
    ai_ready: bool = False
    face_count: int = 0
    last_gesture: str = ""
    last_risk: float = 0.0
    session_risk: float = 0.0
    looking_away: bool = False
    yaw: float = 0.0
    message: str = "Idle"
    evidence_count: int = 0
    camera_index_used: int = -1
    frame_generation: int = 0
    last_frame_at: float = 0.0
    last_evidence: list[dict[str, Any]] = field(default_factory=list)


class FaceMonitor:
    """Owns the primary webcam during the exam.

    Design rules:
    - Exactly one monitor generation runs at a time (generation token).
    - Camera open is synchronous in the monitor thread (no overlapping openers).
    - Face/identity state is cleared whenever the capture is lost or reopened.
    - Camera preview can work even if face AI fails to load.
    """

    # Prefer real RGB webcams; skip common virtual/IR names when ranking.
    _VIRTUAL_HINTS = (
        "obs",
        "virtual",
        "manycam",
        "snap camera",
        "nvidia broadcast",
        "iriun",
        "epoccam",
        "droidcam",
        "iphone",
        "continuity",
        "ndisource",
    )
    _IR_HINTS = ("infrared", " ir ", "ir camera", "tof", "depth")

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
        self._generation = 0
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
        self._identity_generation = 0

    def apply_proctoring(self, *, warn: float, flag: float, terminate: float) -> None:
        self._warn_threshold = float(warn)
        self._terminate_threshold = float(terminate)
        self.settings.gesture_capture_threshold = float(flag)

    def _clear_frame_state(self, *, message: str | None = None, phase: str | None = None) -> None:
        with self._lock:
            self.snapshot.camera_ok = False
            self.snapshot.face_count = 0
            self.snapshot.looking_away = False
            self.snapshot.yaw = 0.0
            self.snapshot.last_gesture = ""
            self._latest_jpeg = None
            self._latest_bgr = None
            self._latest_identity_features = None
            self._identity_generation = 0
            self.snapshot.last_frame_at = 0.0
            if message is not None:
                self.snapshot.message = message
            if phase is not None:
                self.snapshot.camera_phase = phase

    def start(self, session_id: str) -> None:
        self._session_id = session_id
        if self._thread and self._thread.is_alive():
            return
        # Ensure previous worker is fully stopped before clearing stop flag.
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=8)
            self._thread = None

        self._generation += 1
        gen = self._generation
        self._stop = threading.Event()
        self._last_capture_at = 0.0
        self._last_soft_log_at = 0.0
        self._ema_risk = 0.0
        self._prev_yaw = None
        with self._lock:
            self.snapshot.running = True
            self.snapshot.camera_ok = False
            self.snapshot.camera_phase = "opening"
            self.snapshot.face_count = 0
            self.snapshot.last_gesture = ""
            self.snapshot.last_risk = 0.0
            self.snapshot.session_risk = 0.0
            self.snapshot.looking_away = False
            self.snapshot.message = "Starting webcam…"
            self.snapshot.evidence_count = 0
            self.snapshot.last_evidence = []
            self.snapshot.camera_index_used = -1
            self.snapshot.frame_generation = gen
            self.snapshot.last_frame_at = 0.0
            self._latest_jpeg = None
            self._latest_bgr = None
            self._latest_identity_features = None
            self._identity_generation = 0
        self._thread = threading.Thread(
            target=self._loop,
            name=f"face-monitor-{gen}",
            args=(gen,),
            daemon=True,
        )
        self._thread.start()

    def restart(self, session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or self._session_id or "camera-reconnect"
        self.stop()
        time.sleep(0.45)
        self.start(sid)
        return {"ok": True, "message": "Reopening webcam…", "session_id": sid}

    def stop(self) -> None:
        self._stop.set()
        self._generation += 1  # invalidate any late opener / loop
        thr = self._thread
        if thr and thr.is_alive():
            thr.join(timeout=8)
        self._thread = None
        if self._landmarker:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
        self._clear_frame_state(message="Stopped", phase="stopped")
        with self._lock:
            self.snapshot.running = False

    def status(self, *, include_evidence: bool = True) -> dict[str, Any]:
        with self._lock:
            s = self.snapshot
            fresh = bool(s.last_frame_at and (time.time() - s.last_frame_at) < 2.5)
            out = {
                "running": s.running,
                "camera_ok": bool(s.camera_ok and fresh),
                "camera_phase": s.camera_phase,
                "ai_ready": s.ai_ready,
                "face_count": s.face_count if (s.camera_ok and fresh) else 0,
                "last_gesture": s.last_gesture,
                "last_risk": round(s.last_risk, 3),
                "session_risk": round(s.session_risk, 3),
                "looking_away": s.looking_away,
                "yaw": round(s.yaw, 3),
                "message": s.message,
                "evidence_count": s.evidence_count,
                "camera_index_used": s.camera_index_used,
                "frame_generation": s.frame_generation,
                "frame_fresh": fresh,
            }
            if include_evidence:
                out["last_evidence"] = list(s.last_evidence[:6])
            else:
                out["last_evidence"] = []
            return out

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            if not self.snapshot.last_frame_at or (time.time() - self.snapshot.last_frame_at) > 3.0:
                return None
            return self._latest_jpeg

    def identity_sample(self) -> np.ndarray | None:
        with self._lock:
            if self._latest_identity_features is None:
                return None
            # Reject stale embeddings from a previous camera generation.
            if self._identity_generation != self.snapshot.frame_generation:
                return None
            if not self.snapshot.last_frame_at or (time.time() - self.snapshot.last_frame_at) > 2.5:
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
            import cv2

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

    def _score_candidate(self, frm: np.ndarray, idx: int, name: str) -> float:
        mean = float(frm.mean()) if hasattr(frm, "mean") else 0.0
        std = float(frm.std()) if hasattr(frm, "std") else 0.0
        h, w = frm.shape[:2]
        score = mean * 0.35 + std * 2.0 + min(w, 1280) * 0.01
        low = (name or "").lower()
        if any(hnt in low for hnt in self._VIRTUAL_HINTS):
            score -= 80.0
        if any(hnt in low for hnt in self._IR_HINTS):
            score -= 60.0
        if idx == int(self.settings.camera_index):
            score += 12.0
        # Prefer typical RGB resolutions over tiny IR sensors.
        if w >= 640 and h >= 480:
            score += 15.0
        return score

    def _init_com_for_camera(self) -> None:
        """DirectShow needs COM on this thread (common PyInstaller + webcam issue)."""
        try:
            import ctypes

            # COINIT_MULTITHREADED = 0x0 — safe for background capture threads
            ctypes.windll.ole32.CoInitializeEx(None, 0x0)
        except Exception:
            pass

    def _try_open_camera(self, gen: int) -> tuple[Any, int] | tuple[None, int]:
        """Open webcam the same way early working builds did.

        Accept ``isOpened()`` first (old commits), then warm up frames.
        Sequential backends only — never open DSHOW+MSMF in parallel.
        """
        import cv2 as _cv2

        preferred = int(self.settings.camera_index)
        # DSHOW first — more reliable for laptop webcams inside frozen EXEs.
        backends = (
            ("DSHOW", getattr(_cv2, "CAP_DSHOW", 700)),
            ("MSMF", getattr(_cv2, "CAP_MSMF", 1400)),
            ("ANY", 0),
        )
        indices = [preferred] + [i for i in range(0, 4) if i != preferred]

        for idx in indices:
            if self._stop.is_set() or gen != self._generation:
                return None, preferred
            for be_name, backend in backends:
                if self._stop.is_set() or gen != self._generation:
                    return None, preferred
                trial = None
                try:
                    trial = _cv2.VideoCapture(idx, backend)
                    if not trial.isOpened():
                        print(f"  Webcam   fail idx={idx} {be_name}: not opened", flush=True)
                        trial.release()
                        continue
                    # Old working path: trust isOpened, then configure + warm up.
                    try:
                        trial.set(_cv2.CAP_PROP_FRAME_WIDTH, 640)
                        trial.set(_cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        trial.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                    warm_ok = False
                    last_mean = None
                    for i in range(20):
                        if self._stop.is_set() or gen != self._generation:
                            break
                        ok_f, frm = trial.read()
                        if ok_f and frm is not None and getattr(frm, "size", 0) > 0:
                            last_mean = float(frm.mean()) if hasattr(frm, "mean") else 0.0
                            # Accept any readable frame (dim rooms / IR can be dark).
                            if last_mean > 0.1 or i >= 5:
                                warm_ok = True
                                break
                        time.sleep(0.05)
                    if not warm_ok:
                        print(
                            f"  Webcam   fail idx={idx} {be_name}: opened but no frame mean={last_mean}",
                            flush=True,
                        )
                        trial.release()
                        continue
                    print(
                        f"  Webcam   opened idx={idx} {be_name} mean={last_mean:.1f}",
                        flush=True,
                    )
                    return trial, idx
                except Exception as exc:
                    print(f"  Webcam   fail idx={idx} {be_name}: {exc}", flush=True)
                    if trial is not None:
                        try:
                            trial.release()
                        except Exception:
                            pass

        print("  Webcam   open failed on all indices/backends", flush=True)
        return None, preferred

    def _loop(self, gen: int) -> None:
        import cv2

        self._init_com_for_camera()

        ai_error = ""
        try:
            self._landmarker = FaceLandmarkerBundle(self.settings.face_landmarker_path)
        except Exception as exc:
            ai_error = str(exc)
            self._landmarker = None
            with self._lock:
                self.snapshot.ai_ready = False
                self.snapshot.message = f"Face AI offline ({exc}); camera preview still attempted"

        interval = 1.0 / max(0.5, self.settings.monitor_fps)
        while not self._stop.is_set() and gen == self._generation:
            self._clear_frame_state(message="Opening webcam…", phase="opening")
            with self._lock:
                self.snapshot.frame_generation = gen

            cap, used_index = self._try_open_camera(gen)
            if self._stop.is_set() or gen != self._generation:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                return

            if cap is None:
                with self._lock:
                    self.snapshot.camera_phase = "busy"
                    self.snapshot.message = (
                        "Webcam locked — close Windows Camera, Zoom, Teams, or browser "
                        "tabs using the camera, then tap Retry webcam"
                    )
                    self.snapshot.camera_ok = False
                for _ in range(16):
                    if self._stop.is_set() or gen != self._generation:
                        return
                    time.sleep(0.25)
                continue

            with self._lock:
                self.snapshot.camera_ok = True
                self.snapshot.camera_phase = "ready"
                self.snapshot.camera_index_used = used_index
                self.snapshot.message = (
                    f"Monitoring (cam {used_index})"
                    + (f" · AI offline: {ai_error[:40]}" if ai_error else "")
                )

            fail_reads = 0
            try:
                while not self._stop.is_set() and gen == self._generation:
                    t0 = time.time()
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        fail_reads += 1
                        if fail_reads >= 8:
                            self._clear_frame_state(
                                message="Webcam lost — reopening…",
                                phase="opening",
                            )
                            break
                        time.sleep(0.2)
                        continue

                    fail_reads = 0
                    preview = frame
                    h, w = frame.shape[:2]
                    if w > 640:
                        scale = 640 / w
                        preview = cv2.resize(frame, (640, int(h * scale)))
                    ok_j, buf = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    now = time.time()
                    with self._lock:
                        self.snapshot.camera_ok = True
                        self.snapshot.camera_phase = "ready"
                        self.snapshot.last_frame_at = now
                        self.snapshot.frame_generation = gen
                        if ok_j:
                            self._latest_jpeg = buf.tobytes()
                            self._latest_bgr = frame

                    if self._landmarker is None:
                        time.sleep(max(0.0, interval - (time.time() - t0)))
                        continue

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
                                    self._identity_generation = gen
                            except Exception:
                                pass
                        elif len(faces) != 1:
                            with self._lock:
                                self._latest_identity_features = None
                                self._identity_generation = 0
                        analysis = self.engine.analyze_landmarks(faces)
                        self._handle_analysis(frame, analysis)
                    except Exception as exc:
                        with self._lock:
                            self.snapshot.message = f"Analyze error: {exc}"

                    elapsed = time.time() - t0
                    time.sleep(max(0.0, interval - elapsed))
            finally:
                try:
                    cap.release()
                except Exception:
                    pass
                self._clear_frame_state(
                    message="Webcam stopped" if self._stop.is_set() else "Webcam stopped — reopening…",
                    phase="stopped" if self._stop.is_set() else "opening",
                )

            if self._stop.is_set() or gen != self._generation:
                return
            time.sleep(0.4)

        with self._lock:
            self.snapshot.running = False
            if self.snapshot.camera_phase not in {"failed", "busy"}:
                self.snapshot.camera_phase = "stopped"

    def _handle_analysis(self, frame: np.ndarray, analysis: FrameAnalysis) -> None:
        pred = analysis.prediction
        risk = float(pred.risk) if pred else 0.0

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

        now = time.time()
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
        cooled = (now - self._last_capture_at) >= self.settings.capture_cooldown_sec

        if should_capture and cooled:
            self._last_capture_at = now
            # Offload disk/JPEG/screen capture so the webcam loop stays real-time.
            frame_copy = frame.copy()
            yaw = analysis.yaw
            pitch = analysis.pitch
            pred_name = pred.name
            plain = pred.plain_language
            src = pred.source
            sid = self._session_id or "nosession"
            evid_dir = self.settings.data_dir / "evidence"

            def _capture_job() -> None:
                bundle = capture_evidence(
                    frame_copy,
                    evidence_dir=evid_dir,
                    session_id=sid,
                    reason=pred_name,
                    include_screen=True,
                )
                payload = evidence_payload(
                    bundle,
                    gesture_label=pred_name,
                    plain_language=plain,
                )
                payload["yaw"] = yaw
                payload["pitch"] = pitch
                payload["source_detector"] = src
                self._record_evidence(payload, severity=risk, event_type=event_type)

            submit_io(_capture_job)
        elif self.on_event and risk >= self._warn_threshold and (now - self._last_soft_log_at) >= 20.0:
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
