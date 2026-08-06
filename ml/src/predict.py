"""Quick inference helper for a trained IntelliQuiz gesture model.

Usage:
  python -m src.predict --model artifacts/models/best_model.joblib --demo
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np

from .data_loader import feature_matrix, load_dataset
from .labels import display_name, risk_for_label

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run IntelliQuiz gesture inference")
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "artifacts" / "models" / "best_model.joblib",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Score a few held-out Mediapipe samples from the dataset",
    )
    parser.add_argument("--n", type=int, default=5, help="Demo sample count")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = args.model if args.model.is_absolute() else ROOT / args.model
    bundle = joblib.load(model_path)
    pipeline = bundle["pipeline"]

    if not args.demo:
        print(json.dumps({
            "model_path": str(model_path),
            "dataset": bundle.get("dataset"),
            "feature_dim": bundle.get("feature_dim"),
            "class_names": bundle.get("class_names"),
            "metrics": {
                "accuracy": bundle.get("metrics", {}).get("accuracy"),
                "macro_f1": bundle.get("metrics", {}).get("macro_f1"),
            },
        }, indent=2))
        return 0

    df = load_dataset(cache_dir=ROOT / "data" / "cache")
    x, y = feature_matrix(df)
    rng = np.random.default_rng(42)
    idx = rng.choice(len(y), size=min(args.n, len(y)), replace=False)

    print("idx | true                | pred                | risk | correct")
    for i in idx:
        pred = int(pipeline.predict(x[i : i + 1])[0])
        true = int(y[i])
        print(
            f"{i:3d} | {display_name(true):<20} | {display_name(pred):<20} | "
            f"{risk_for_label(pred):.2f} | {true == pred}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
