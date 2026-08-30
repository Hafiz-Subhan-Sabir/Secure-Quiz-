"""Face identity — landmark embedding enrollment and 1:1 verification."""

from __future__ import annotations

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


def verify(enrolled: np.ndarray, sample: np.ndarray, *, threshold: float = DEFAULT_MATCH_THRESHOLD) -> tuple[bool, float]:
    score = cosine_similarity(enrolled, sample)
    return score >= threshold, score
