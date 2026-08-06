"""Face landmark → 1404-dim feature vector (FaceGest Mediapipe layout)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# FaceGest Deep-Features-Mediapipe uses classic Face Mesh topology.
FACE_MESH_LANDMARKS = 468
FEATURE_DIM = FACE_MESH_LANDMARKS * 3  # 1404


PROCTORING_RISK: dict[int, float] = {
    0: 0.15,
    1: 0.15,
    2: 0.55,
    3: 0.35,
    4: 0.20,
    5: 0.10,
    6: 0.70,
    7: 0.25,
    8: 0.20,
    9: 0.85,
    10: 0.30,
    11: 0.60,
    12: 0.90,
}

GESTURE_PLAIN: dict[str, str] = {
    "SBR": "Right-eye blink detected.",
    "SBL": "Left-eye blink detected.",
    "MO": "Mouth opened wide — possible talking.",
    "LP": "Lips pursed tightly.",
    "DB": "Double blink detected.",
    "S": "Smile detected.",
    "N": "Head nod — vertical gaze movement.",
    "RE": "Eyebrows raised.",
    "F": "Frown / brow furrow.",
    "SH": "Head shake — looking left/right away from screen.",
    "B&S": "Blink while smiling.",
    "RE&MO": "Eyebrows raised with mouth open.",
    "W&HT": "Wink + head tilt — strong gaze diversion.",
}


def ensure_face_landmarker(model_path: Path) -> Path:
    """Download MediaPipe Face Landmarker .task if missing."""
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if model_path.exists() and model_path.stat().st_size > 1_000_000:
        return model_path
    url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    )
    import urllib.request

    tmp = model_path.with_suffix(".task.download")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(model_path)
    return model_path


def landmarks_to_features(landmarks: list[Any]) -> np.ndarray:
    """Flatten first 468 landmarks to FaceGest-compatible 1404 features.

    Coordinates are recentered on the nose tip and scaled by inter-ocular
    distance so magnitude roughly matches deep-feature CSVs.
    """
    pts = np.asarray(
        [[lm.x, lm.y, getattr(lm, "z", 0.0)] for lm in landmarks[:FACE_MESH_LANDMARKS]],
        dtype=np.float64,
    )
    if pts.shape[0] < FACE_MESH_LANDMARKS:
        pad = np.zeros((FACE_MESH_LANDMARKS - pts.shape[0], 3), dtype=np.float64)
        pts = np.vstack([pts, pad])

    # Nose tip ≈ index 1 in Face Mesh topology
    center = pts[1].copy()
    pts = pts - center

    # Left / right eye outer corners (33 / 263) for scale
    left_eye = pts[33]
    right_eye = pts[263]
    scale = float(np.linalg.norm(left_eye - right_eye))
    if scale < 1e-6:
        scale = float(np.linalg.norm(pts)) + 1e-6
    pts = pts / scale
    return pts.reshape(-1)


def estimate_yaw_pitch(landmarks: list[Any]) -> tuple[float, float]:
    """Rough head pose proxy from landmark geometry (normalized coords)."""
    if len(landmarks) < 264:
        return 0.0, 0.0
    nose = landmarks[1]
    left = landmarks[33]
    right = landmarks[263]
    chin = landmarks[152] if len(landmarks) > 152 else landmarks[1]
    mid_x = (left.x + right.x) / 2.0
    eye_dist = abs(right.x - left.x) + 1e-6
    yaw = (nose.x - mid_x) / eye_dist  # + look right, - look left
    pitch = (nose.y - chin.y) / (abs(chin.y - ((left.y + right.y) / 2)) + 1e-6)
    return float(yaw), float(pitch)


class FaceLandmarkerBundle:
    """Thin wrapper around MediaPipe Tasks FaceLandmarker."""

    def __init__(self, model_path: Path) -> None:
        ensure_face_landmarker(model_path)
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core import base_options as base_options_module

        options = vision.FaceLandmarkerOptions(
            base_options=base_options_module.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=2,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._mp = mp
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._ts_ms = 0

    def detect_bgr(self, frame_bgr: np.ndarray) -> Any:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        self._ts_ms += 33
        return self._landmarker.detect_for_video(mp_image, self._ts_ms)

    def close(self) -> None:
        self._landmarker.close()
