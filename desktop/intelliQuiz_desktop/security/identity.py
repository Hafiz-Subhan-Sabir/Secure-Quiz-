"""Face identity — landmark embedding enrollment and 1:1 verification."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Stable landmark indices (nose, eyes, mouth, jaw) for identity matching.
_IDENTITY_INDICES = (
    1,
    33,
    133,
    362,
    263,
    61,
    291,
    199,
    152,
    234,
    454,
    10,
    151,
    9,
    175,
    400,
)

DEFAULT_MATCH_THRESHOLD = 0.88


def embedding_from_features(features: np.ndarray) -> np.ndarray:
    """Reduce 1404-dim FaceGest vector to a compact identity embedding."""
    pts = features.reshape(-1, 3)
    if pts.shape[0] < max(_IDENTITY_INDICES) + 1:
        raise ValueError("Insufficient landmark features for identity")
    vec = pts[list(_IDENTITY_INDICES), :].reshape(-1).astype(np.float64)
    norm = np.linalg.norm(vec)
    if norm < 1e-9:
        raise ValueError("Degenerate identity embedding")
    return vec / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def merge_samples(samples: list[np.ndarray]) -> np.ndarray:
    if not samples:
        raise ValueError("No identity samples")
    stacked = np.stack(samples, axis=0)
    mean = stacked.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm < 1e-9:
        raise ValueError("Degenerate merged identity embedding")
    return mean / norm


def verify(
    enrolled: np.ndarray,
    sample: np.ndarray,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> tuple[bool, float]:
    score = cosine_similarity(enrolled, sample)
    return score >= threshold, score


def embedding_from_jpeg(
    jpeg_bytes: bytes,
    *,
    landmarker_path: Path,
    landmarker: object | None = None,
) -> np.ndarray | None:
    """Build an identity embedding from a phone/webcam JPEG. Returns None if no single face."""
    import cv2

    from intelliQuiz_desktop.ai.landmarks import FaceLandmarkerBundle, landmarks_to_features

    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return None

    own = landmarker is None
    bundle = landmarker if landmarker is not None else FaceLandmarkerBundle(landmarker_path)
    try:
        result = bundle.detect_bgr(frame)  # type: ignore[attr-defined]
        faces = list(result.face_landmarks or [])
        if len(faces) != 1:
            return None
        return embedding_from_features(landmarks_to_features(faces[0]))
    except Exception:
        return None
    finally:
        if own:
            try:
                bundle.close()  # type: ignore[attr-defined]
            except Exception:
                pass
