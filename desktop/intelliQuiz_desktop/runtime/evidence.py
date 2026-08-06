"""Evidence capture — webcam JPEG + optional full-screen snapshot."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class EvidenceBundle:
    webcam_data_uri: str | None
    screen_data_uri: str | None
    saved_webcam_path: Path | None
    saved_screen_path: Path | None
    captured_at: str


def _jpeg_data_uri(frame_bgr: np.ndarray, quality: int = 75) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("Failed to encode webcam JPEG")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def capture_screen_data_uri(max_width: int = 1280, quality: int = 60) -> str | None:
    """Grab primary monitor; shrink for sync payload size."""
    try:
        import mss
        from PIL import Image
        import io
    except Exception:
        return None

    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if img.width > max_width:
            ratio = max_width / float(img.width)
            img = img.resize((max_width, int(img.height * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


def capture_evidence(
    frame_bgr: np.ndarray | None,
    *,
    evidence_dir: Path,
    session_id: str,
    reason: str,
    include_screen: bool = True,
) -> EvidenceBundle:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:40]
    prefix = evidence_dir / f"{session_id[:8]}_{ts}_{safe_reason}"

    webcam_uri = None
    webcam_path = None
    if frame_bgr is not None:
        webcam_uri = _jpeg_data_uri(frame_bgr)
        webcam_path = Path(str(prefix) + "_webcam.jpg")
        import cv2

        cv2.imwrite(str(webcam_path), frame_bgr)

    screen_uri = capture_screen_data_uri() if include_screen else None
    screen_path = None
    if screen_uri and screen_uri.startswith("data:image/jpeg;base64,"):
        screen_path = Path(str(prefix) + "_screen.jpg")
        raw = base64.b64decode(screen_uri.split(",", 1)[1])
        screen_path.write_bytes(raw)

    return EvidenceBundle(
        webcam_data_uri=webcam_uri,
        screen_data_uri=screen_uri,
        saved_webcam_path=webcam_path,
        saved_screen_path=screen_path,
        captured_at=datetime.now(UTC).isoformat(),
    )


def evidence_payload(
    bundle: EvidenceBundle,
    *,
    gesture_label: str,
    plain_language: str,
    source: str = "primary_webcam",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "gesture_label": gesture_label,
        "plain_language": plain_language,
        "source": source,
        "model": "FaceGest-Mediapipe-RF",
        "capture_reason": "abnormal_face_gesture",
        "captured_at": bundle.captured_at,
    }
    if bundle.webcam_data_uri:
        payload["image_data_uri"] = bundle.webcam_data_uri
    if bundle.screen_data_uri:
        payload["screen_image_data_uri"] = bundle.screen_data_uri
    return payload
