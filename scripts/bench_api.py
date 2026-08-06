import time
import uuid
from datetime import UTC, datetime

import httpx

base = "http://127.0.0.1:8080/api/v1"
t0 = time.perf_counter()
h = httpx.get(f"{base}/health", timeout=5)
print("health", h.status_code, h.json(), "hdr", h.headers.get("x-response-time-ms"))

r = httpx.post(
    f"{base}/auth/login",
    json={"email": "student@intelliquiz.dev", "password": "Student123!"},
)
print("login", r.status_code, r.json().get("role"))
token = r.json()["access_token"]
hdr = {"Authorization": f"Bearer {token}"}
exams = httpx.get(f"{base}/exams", headers=hdr).json()
session = httpx.post(
    f"{base}/sessions",
    headers=hdr,
    json={"exam_id": exams[0]["id"], "device_fingerprint": "opt-test-1234"},
).json()

events = [
    {
        "event_id": str(uuid.uuid4()),
        "type": "gesture_risk",
        "ts": datetime.now(UTC).isoformat(),
        "severity": 0.72,
        "payload": {"g": "SH"},
    }
    for _ in range(20)
]
events.append(
    {
        "event_id": str(uuid.uuid4()),
        "type": "heartbeat",
        "ts": datetime.now(UTC).isoformat(),
        "severity": 0.1,
        "payload": {},
    }
)

t1 = time.perf_counter()
sync = httpx.post(
    f"{base}/sync/events",
    headers=hdr,
    json={"session_id": session["id"], "events": events},
)
t2 = time.perf_counter()
print("sync", sync.status_code, sync.json(), f"batch_ms={(t2 - t1) * 1000:.1f}")

admin = httpx.post(
    f"{base}/auth/login",
    json={"email": "admin@intelliquiz.dev", "password": "Admin123!"},
).json()["access_token"]
rep = httpx.get(
    f"{base}/reports/sessions/{session['id']}",
    headers={"Authorization": f"Bearer {admin}"},
)
body = rep.json()
print("report", rep.status_code, "prob", body["cheating_probability"], "events", body["event_count"])
print(f"total_ms={(time.perf_counter() - t0) * 1000:.1f}")
