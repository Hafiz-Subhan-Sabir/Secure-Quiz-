"""QR pairing payload for Android secondary camera (pairing.qr.v1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any


def build_pairing_payload(
    *,
    session_id: str,
    pairing_token: str,
    desktop_endpoint: str,
    ttl_seconds: int = 300,
    exam_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "pairing.qr.v1",
        "session_id": session_id,
        "pairing_token": pairing_token,
        "desktop_endpoint": desktop_endpoint,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    if exam_code:
        payload["exam_code"] = exam_code
    return payload


def pairing_qr_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))
