"""On-device AI engine — FaceGest RF classifier + geometric heuristics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from intelliQuiz_desktop.ai.landmarks import (
    FEATURE_DIM,
    GESTURE_PLAIN,
    PROCTORING_RISK,
    estimate_yaw_pitch,
    landmarks_to_features,
)


@dataclass
class GesturePrediction:
    label: int
    name: str
    risk: float
    latency_ms: float
    plain_language: str = ""
    source: str = "classifier"


@dataclass
class FrameAnalysis:
    face_count: int
    prediction: GesturePrediction | None
    yaw: float = 0.0
    pitch: float = 0.0
    looking_away: bool = False
    features_ok: bool = False


class OnDeviceAIEngine:
    """MediaPipe landmarks → trained classifier → proctoring risk."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._bundle: dict[str, Any] | None = None

    def load(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        import joblib

        self._bundle = joblib.load(self.model_path)

    @property
    def ready(self) -> bool:
        return self._bundle is not None

    def predict_from_features(self, features: list[float] | np.ndarray) -> GesturePrediction:
        import time

        if self._bundle is None:
            raise RuntimeError("Model not loaded")
        t0 = time.perf_counter()
        pipeline = self._bundle["pipeline"]
        class_names: list[str] = list(
            self._bundle.get("class_names") or [str(i) for i in range(13)]
        )
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        if x.shape[1] != FEATURE_DIM:
            # Pad / truncate defensively
            fixed = np.zeros((1, FEATURE_DIM), dtype=np.float64)
            n = min(FEATURE_DIM, x.shape[1])
            fixed[0, :n] = x[0, :n]
            x = fixed
        label = int(pipeline.predict(x)[0])
        risk = float(PROCTORING_RISK.get(label, 0.5))
        ms = (time.perf_counter() - t0) * 1000
        name = class_names[label] if label < len(class_names) else str(label)
        return GesturePrediction(
            label=label,
            name=name,
            risk=risk,
            latency_ms=ms,
            plain_language=GESTURE_PLAIN.get(name, f"Gesture {name} detected."),
            source="classifier",
        )

    def analyze_landmarks(self, face_landmarks_list: list) -> FrameAnalysis:
        face_count = len(face_landmarks_list)
        if face_count == 0:
            return FrameAnalysis(
                face_count=0,
                prediction=GesturePrediction(
                    label=-1,
                    name="NO_FACE",
                    risk=0.75,
                    latency_ms=0.0,
                    plain_language="No face visible in webcam — student may have left the seat.",
                    source="heuristic",
                ),
            )
        if face_count >= 2:
            return FrameAnalysis(
                face_count=face_count,
                prediction=GesturePrediction(
                    label=-2,
                    name="MULTI_FACE",
                    risk=0.88,
                    latency_ms=0.0,
                    plain_language="More than one face in the webcam frame.",
                    source="heuristic",
                ),
            )

        lms = face_landmarks_list[0]
        yaw, pitch = estimate_yaw_pitch(lms)
        looking_away = abs(yaw) > 0.35 or abs(pitch) > 1.8

        pred: GesturePrediction | None = None
        features_ok = False
        if self.ready:
            try:
                feats = landmarks_to_features(lms)
                pred = self.predict_from_features(feats)
                features_ok = True
            except Exception:
                pred = None

        if looking_away:
            gaze = GesturePrediction(
                label=-3,
                name="GAZE_AWAY",
                risk=0.8,
                latency_ms=pred.latency_ms if pred else 0.0,
                plain_language="Head turned away from the screen (gaze diversion).",
                source="heuristic",
            )
            # Prefer higher of classifier vs gaze heuristic
            if pred is None or gaze.risk >= pred.risk:
                pred = gaze

        return FrameAnalysis(
            face_count=face_count,
            prediction=pred,
            yaw=yaw,
            pitch=pitch,
            looking_away=looking_away,
            features_ok=features_ok,
        )
