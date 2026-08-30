from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _admin_token() -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@intelliquiz.dev", "password": "Admin123!"},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "intelliquiz-api"


def test_login_and_list_exams():
    token = _admin_token()
    exams = client.get("/api/v1/exams", headers={"Authorization": f"Bearer {token}"})
    assert exams.status_code == 200
    assert isinstance(exams.json(), list)


def test_proctoring_profiles_crud():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/v1/proctoring-profiles",
        headers=headers,
        json={
            "name": "Test Profile",
            "strictness": "medium",
            "warn_threshold": 0.35,
            "flag_threshold": 0.55,
            "terminate_threshold": 0.85,
            "require_android_camera": True,
            "blacklist_apps_csv": "chrome.exe,firefox.exe",
        },
    )
    assert created.status_code == 201
    profile = created.json()
    assert profile["name"] == "Test Profile"
    assert profile["require_android_camera"] is True

    listed = client.get("/api/v1/proctoring-profiles", headers=headers)
    assert listed.status_code == 200
    assert any(p["id"] == profile["id"] for p in listed.json())

    updated = client.put(
        f"/api/v1/proctoring-profiles/{profile['id']}",
        headers=headers,
        json={
            "name": "Updated Profile",
            "strictness": "high",
            "warn_threshold": 0.3,
            "flag_threshold": 0.5,
            "terminate_threshold": 0.8,
            "require_android_camera": False,
            "blacklist_apps_csv": "",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Profile"


def test_exam_questions_and_publish():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    exam = client.post(
        "/api/v1/exams",
        headers=headers,
        json={
            "title": "API Test Quiz",
            "duration_minutes": 15,
            "instructions": "Answer all questions.",
        },
    )
    assert exam.status_code == 201
    exam_id = exam.json()["id"]

    publish_empty = client.post(f"/api/v1/exams/{exam_id}/publish", headers=headers)
    assert publish_empty.status_code == 400

    q = client.post(
        f"/api/v1/exams/{exam_id}/questions",
        headers=headers,
        json={
            "prompt": "What is 2+2?",
            "choices": ["3", "4", "5"],
            "correct_index": 1,
            "points": 1,
        },
    )
    assert q.status_code == 201
    question_id = q.json()["id"]

    listed = client.get(f"/api/v1/exams/{exam_id}/questions", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = client.delete(
        f"/api/v1/exams/{exam_id}/questions/{question_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    client.post(
        f"/api/v1/exams/{exam_id}/questions",
        headers=headers,
        json={
            "prompt": "Pick one",
            "choices": ["A", "B"],
            "correct_index": 0,
        },
    )
    published = client.post(f"/api/v1/exams/{exam_id}/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
