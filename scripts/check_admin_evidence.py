import httpx

base = "http://127.0.0.1:8080/api/v1"
admin = httpx.post(
    f"{base}/auth/login",
    json={"email": "admin@intelliquiz.dev", "password": "Admin123!"},
).json()["access_token"]
hdr = {"Authorization": f"Bearer {admin}"}
attempts = httpx.get(f"{base}/sessions/attempts", headers=hdr)
print("attempts", attempts.status_code, len(attempts.json()))
if attempts.json():
    sid = attempts.json()[0]["session_id"]
    print("first", attempts.json()[0]["student_name"], "evidence", attempts.json()[0]["evidence_count"])
    rep = httpx.get(f"{base}/reports/sessions/{sid}", headers=hdr).json()
    print("report", rep["student_name"], "prob", rep["cheating_probability"], "photos", len(rep["evidence"]))
    print("summary", rep["summary_plain"][:120], "...")
print("admin_ui", httpx.get("http://127.0.0.1:5173/", timeout=5).status_code)
