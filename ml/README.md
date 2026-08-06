# IntelliQuiz – Model Training (Phase 1)

First milestone for **IntelliQuiz**: train on-device facial gesture / head-pose signals using FaceGest **Deep Features** (no full video download required).

## Why this dataset

FaceGest (CVPRW 2025) provides 13 dynamic facial gestures (eye / mouth / head / combined). MediaPipe landmark features (468 pts × xyz = **1404 dims**) are a strong starting point for:

- gaze / blink behavior
- head nod & shake
- mouth open (talking proxy)

These map into IntelliQuiz’s **Cheating Probability Score**.

## Setup

```bash
cd ml
pip install -r requirements.txt
# optional parquet cache speedup
pip install pyarrow
```

## Train

```bash
cd ml
python -m src.train --config configs/train_mediapipe.yaml
```

This will:

1. Download `Deep-Features-Mediapipe` via `face-gest-loader`
2. Cache a cleaned dataframe under `data/cache/`
3. Train RF / GBM / Logistic / SVM / MLP baselines
4. Write metrics, confusion matrices, and `artifacts/models/best_model.joblib`

## Demo inference

```bash
python -m src.predict --demo
```

## Datasets available in loader v0.1

| Name | Status |
|------|--------|
| `Deep-Features-Mediapipe` | Supported (start here) |
| `Deep-Features-Inception` | Supported |
| `Deep-Features-SqueezeNet` | Documented upstream, **not implemented** in loader v0.1 |

Change `dataset:` in the YAML to `Deep-Features-Inception` to compare.

## Gesture → proctoring risk (initial heuristics)

| Class | Meaning | Risk weight |
|-------|---------|-------------|
| SBR / SBL / DB | Blinks | 0.15–0.20 |
| S / F / RE | Smile / frown / brows | 0.10–0.25 |
| MO / LP | Mouth open / pursed | 0.35–0.55 |
| N / SH | Nod / head shake | 0.70–0.85 |
| W&HT | Wink + head tilt | 0.90 |

Tune later with admin “proctoring strictness” settings.

## Accuracy target

Product target is **≥90%** for gaze/head tracking with low false positives. The public deep-feature CSV is a **small subset (~650 frames)**. Expect solid offline baselines here; full RGB/video FaceGest (request form on the FaceGest site) or live MediaPipe streaming data will be needed for production-grade accuracy.

## Next phases (after this)

1. Live MediaPipe Face Mesh extraction from webcam
2. Desktop exam panel + blacklisted-app control
3. Android secondary camera + QR handshake
4. Central admin integrity reports
