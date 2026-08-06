"""Load and cache FaceGest deep-feature CSVs for IntelliQuiz training."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from face_gest_loader import load_face_gest

from .labels import CLASS_NAMES, risk_for_label

SUPPORTED_DATASETS = {
    "Deep-Features-Mediapipe": "mediapipe",
    "Deep-Features-Inception": "inception",
    # Note: face-gest-loader v0.1 does not implement SqueezeNet yet.
}


def _normalize_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    """CSV was exported without a header row; first value is the class label."""
    df = raw.copy()
    df.columns = ["label"] + [f"f{i}" for i in range(df.shape[1] - 1)]
    df["label"] = df["label"].astype(int)
    return df


def load_dataset(
    dataset_name: str = "Deep-Features-Mediapipe",
    cache_dir: str | Path | None = None,
    force_download: bool = False,
) -> pd.DataFrame:
    if dataset_name not in SUPPORTED_DATASETS:
        supported = ", ".join(SUPPORTED_DATASETS)
        raise ValueError(
            f"Unsupported dataset '{dataset_name}'. "
            f"Supported by face-gest-loader: {supported}. "
            "Deep-Features-SqueezeNet is documented upstream but not wired in loader v0.1."
        )

    cache_path = None
    if cache_dir is not None:
        cache_root = Path(cache_dir)
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_path = cache_root / f"{SUPPORTED_DATASETS[dataset_name]}.parquet"

    if cache_path is not None and cache_path.exists() and not force_download:
        return pd.read_parquet(cache_path)

    raw = load_face_gest(dataset_name)
    if raw is None or raw.empty:
        raise RuntimeError(f"Failed to load FaceGest dataset: {dataset_name}")

    df = _normalize_dataframe(raw)
    df["risk"] = df["label"].map(risk_for_label)
    df["gesture"] = df["label"].map(lambda i: CLASS_NAMES[i])

    if cache_path is not None:
        try:
            df.to_parquet(cache_path, index=False)
        except Exception:
            csv_fallback = cache_path.with_suffix(".csv")
            df.to_csv(csv_fallback, index=False)
            cache_path = csv_fallback

    return df


def feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    feature_cols = [c for c in df.columns if c.startswith("f")]
    x = df[feature_cols].to_numpy(dtype=np.float64)
    y = df["label"].to_numpy(dtype=np.int64)
    return x, y
