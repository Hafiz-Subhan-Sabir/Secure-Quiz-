from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "intelliquiz-api"


def test_login_and_list_exams():
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@intelliquiz.dev", "password": "Admin123!"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    exams = client.get("/api/v1/exams", headers={"Authorization": f"Bearer {token}"})
    assert exams.status_code == 200
    assert isinstance(exams.json(), list)
