"""HTTP client for IntelliQuiz central API — connection-pooled."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from intelliQuiz_desktop.core.config import get_settings


class ApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or get_settings().api_base_url).rstrip("/")
        self.token = token
        limits = httpx.Limits(max_keepalive_connections=8, max_connections=16)
        self._client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=4.0),
            limits=limits,
            headers={"Accept": "application/json"},
        )

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def login(self, email: str, password: str) -> dict[str, Any]:
        r = self._client.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password},
        )
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        return data

    def list_exams(self) -> list[dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/exams", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def get_exam_paper(self, exam_id: str) -> dict[str, Any]:
        r = self._client.get(f"{self.base_url}/exams/{exam_id}/paper", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_session(self, exam_id: str, device_fingerprint: str) -> dict[str, Any]:
        r = self._client.post(
            f"{self.base_url}/sessions",
            headers=self._headers(),
            json={"exam_id": exam_id, "device_fingerprint": device_fingerprint},
        )
        r.raise_for_status()
        return r.json()

    def heartbeat(self, session_id: str, risk_score: float, android_paired: bool) -> None:
        r = self._client.post(
            f"{self.base_url}/sessions/{session_id}/heartbeat",
            headers=self._headers(),
            json={
                "client_ts": datetime.now(UTC).isoformat(),
                "risk_score": risk_score,
                "android_paired": android_paired,
            },
        )
        r.raise_for_status()

    def sync_events(self, session_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        r = self._client.post(
            f"{self.base_url}/sync/events",
            headers=self._headers(),
            json={"session_id": session_id, "events": events},
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()
