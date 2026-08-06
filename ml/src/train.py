"""Train IntelliQuiz facial-gesture classifiers on FaceGest deep features.

Usage (from ml/):
  python -m src.train --config configs/train_mediapipe.yaml
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.model_selection import cross_val_score, train_test_split

from .data_loader import feature_matrix, load_dataset
from .evaluate import (
    compute_metrics,
    mean_predicted_risk,
    save_confusion_matrix,
    write_json,
)
from .labels import CLASS_NAMES
from .models import build_model

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train IntelliQuiz FaceGest models")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "train_mediapipe.yaml",
        help="Path to YAML training config",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Ignore local parquet cache and re-download CSV",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cache_dir = ROOT / cfg.get("cache_dir", "data/cache")
    artifacts_dir = ROOT / cfg.get("artifacts_dir", "artifacts")
    models_dir = artifacts_dir / "models"
    reports_dir = artifacts_dir / "reports"
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    dataset_name = cfg["dataset"]
    print(f"==> Loading {dataset_name}", flush=True)
    df = load_dataset(
        dataset_name=dataset_name,
        cache_dir=cache_dir,
        force_download=args.force_download,
    )
    x, y = feature_matrix(df)
    print(f"    samples={len(y)} features={x.shape[1]} classes={len(CLASS_NAMES)}", flush=True)
    print(f"    label counts: {dict(zip(*np.unique(y, return_counts=True)))}", flush=True)

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=float(cfg.get("test_size", 0.2)),
        random_state=int(cfg.get("random_state", 42)),
        stratify=y,
    )

    leaderboard: list[dict] = []
    best_name = None
    best_score = -1.0
    best_bundle = None

    for model_name in cfg.get("models", []):
        print(f"\n==> Training {model_name}", flush=True)
        pipeline = build_model(model_name, cfg, random_state=int(cfg.get("random_state", 42)))
        pipeline.fit(x_train, y_train)

        y_pred = pipeline.predict(x_test)
        metrics = compute_metrics(y_test, y_pred)
        # Prefer speed for SVM/MLP CV; RF already parallelizes internally.
        cv_jobs = 1 if model_name in {"svm_rbf", "mlp"} else -1
        cv_scores = cross_val_score(
            pipeline,
            x_train,
            y_train,
            cv=int(cfg.get("cv_folds", 5)),
            scoring="accuracy",
            n_jobs=cv_jobs,
        )

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        model_path = models_dir / f"{model_name}_{stamp}.joblib"
        joblib.dump(
            {
                "pipeline": pipeline,
                "dataset": dataset_name,
                "class_names": CLASS_NAMES,
                "feature_dim": int(x.shape[1]),
                "metrics": metrics,
            },
            model_path,
        )

        cm_path = reports_dir / f"cm_{model_name}_{stamp}.png"
        save_confusion_matrix(
            y_test,
            y_pred,
            cm_path,
            title=f"{model_name} | acc={metrics['accuracy']:.3f}",
        )

        entry = {
            "model": model_name,
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "weighted_f1": metrics["weighted_f1"],
            "cv_accuracy_mean": float(cv_scores.mean()),
            "cv_accuracy_std": float(cv_scores.std()),
            "mean_predicted_risk": mean_predicted_risk(y_pred),
            "model_path": str(model_path.relative_to(ROOT)),
            "confusion_matrix": str(cm_path.relative_to(ROOT)),
            "per_class": metrics["per_class"],
        }
        write_json(reports_dir / f"metrics_{model_name}_{stamp}.json", entry)
        leaderboard.append(entry)

        print(
            f"    test_acc={metrics['accuracy']:.4f} "
            f"macro_f1={metrics['macro_f1']:.4f} "
            f"cv_acc={cv_scores.mean():.4f}±{cv_scores.std():.4f}",
            flush=True,
        )

        if metrics["macro_f1"] > best_score:
            best_score = metrics["macro_f1"]
            best_name = model_name
            best_bundle = {
                "pipeline": pipeline,
                "dataset": dataset_name,
                "class_names": CLASS_NAMES,
                "feature_dim": int(x.shape[1]),
                "metrics": metrics,
                "model_name": model_name,
            }

    leaderboard.sort(key=lambda e: e["macro_f1"], reverse=True)
    summary = {
        "dataset": dataset_name,
        "n_samples": int(len(y)),
        "n_features": int(x.shape[1]),
        "best_model": best_name,
        "best_macro_f1": best_score,
        "target_accuracy": 0.90,
        "meets_target": bool(leaderboard and leaderboard[0]["accuracy"] >= 0.90),
        "leaderboard": leaderboard,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(reports_dir / "leaderboard.json", summary)

    if best_bundle is not None:
        best_path = models_dir / "best_model.joblib"
        joblib.dump(best_bundle, best_path)
        print(f"\n==> Best model: {best_name} (macro_f1={best_score:.4f})")
        print(f"    saved -> {best_path}")

    print(f"\n==> Leaderboard -> {reports_dir / 'leaderboard.json'}")
    for i, row in enumerate(leaderboard, start=1):
        print(
            f"    {i}. {row['model']:<20} "
            f"acc={row['accuracy']:.4f}  "
            f"macro_f1={row['macro_f1']:.4f}"
        )

    if not summary["meets_target"]:
        print(
            "\nNote: Deep-feature CSV has ~650 frames (subset). "
            "Full FaceGest (~15k videos) or video fine-tuning will be needed "
            "to push toward the >=90% proctoring accuracy target."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
