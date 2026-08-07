"""HTTP client for IntelliQuiz central API — connection-pooled + thread-safe."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

import httpx

from intelliQuiz_desktop.core.config import get_settings


class ApiClient:
    """Thread-safe wrapper — heartbeat + UI requests share one process safely."""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or get_settings().api_base_url).rstrip("/")
        self.token = token
        self._lock = threading.RLock()
        limits = httpx.Limits(max_keepalive_connections=8, max_connections=16)
        self._client = httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0),
            limits=limits,
            headers={"Accept": "application/json"},
        )

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def login(self, email: str, password: str) -> dict[str, Any]:
        with self._lock:
            r = self._client.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
            )
            r.raise_for_status()
            data = r.json()
            self.token = data["access_token"]
            return data

    def list_exams(self) -> list[dict[str, Any]]:
        with self._lock:
            r = self._client.get(f"{self.base_url}/exams", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def get_exam_paper(self, exam_id: str) -> dict[str, Any]:
        with self._lock:
            r = self._client.get(f"{self.base_url}/exams/{exam_id}/paper", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def create_session(self, exam_id: str, device_fingerprint: str) -> dict[str, Any]:
        with self._lock:
            r = self._client.post(
                f"{self.base_url}/sessions",
                headers=self._headers(),
                json={"exam_id": exam_id, "device_fingerprint": device_fingerprint},
            )
            r.raise_for_status()
            return r.json()

    def heartbeat(self, session_id: str, risk_score: float, android_paired: bool) -> None:
        with self._lock:
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
        with self._lock:
            r = self._client.post(
                f"{self.base_url}/sync/events",
                headers=self._headers(),
                json={"session_id": session_id, "events": events},
            )
            r.raise_for_status()
            return r.json()

    def get_session_result(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            r = self._client.get(
                f"{self.base_url}/sessions/{session_id}/result",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    def list_my_attempts(self) -> list[dict[str, Any]]:
        with self._lock:
            r = self._client.get(f"{self.base_url}/sessions/mine", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def close(self) -> None:
        with self._lock:
            self._client.close()
