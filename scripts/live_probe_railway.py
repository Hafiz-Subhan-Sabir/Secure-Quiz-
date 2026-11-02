"""Probe Railway API readiness after deploy."""
from __future__ import annotations

import json
import sys

import httpx

BASE = "https://intelligence-production-62ec.up.railway.app/api/v1"


def main() -> int:
    client = httpx.Client(timeout=30.0, verify=True)
    r = client.post(f"{BASE}/auth/login", json={"email": "admin@intelliquiz.dev", "password": "Admin123!"})
    r.raise_for_status()
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    users = client.get(f"{BASE}/users", headers=h)
    print("USERS", users.status_code, users.headers.get("content-type", "").split(";")[0])
    print("USERS_BODY", users.text[:160].replace("\n", " "))
    users_ok = users.status_code == 200 and "application/json" in (users.headers.get("content-type") or "")

    exams = client.get(f"{BASE}/exams", headers=h)
    exams.raise_for_status()
    exam_list = exams.json()
    print("EXAMS", [(e["title"], e["status"]) for e in exam_list])

    published = []
    for e in exam_list:
        if e["status"] != "published":
            p = client.post(f"{BASE}/exams/{e['id']}/publish", headers=h)
            print("PUBLISH", e["title"], p.status_code, p.text[:120])
        if e["status"] == "published" or True:
            # refresh
            pass
    exams2 = client.get(f"{BASE}/exams", headers=h).json()
    published = [e for e in exams2 if e["status"] == "published"]
    print("PUBLISHED", [(e["title"], e["id"]) for e in published])

    # ensure a published exam exists for desktop test
    if not published and exam_list:
        e = exam_list[0]
        p = client.post(f"{BASE}/exams/{e['id']}/publish", headers=h)
        print("FORCE_PUBLISH", e["title"], p.status_code, p.text[:200])
        exams2 = client.get(f"{BASE}/exams", headers=h).json()
        published = [e for e in exams2 if e["status"] == "published"]
        print("PUBLISHED_AFTER", [(e["title"], e["id"]) for e in published])

    # student login
    s = client.post(
        f"{BASE}/auth/login",
        json={"email": "student@intelliquiz.dev", "password": "Student123!"},
    )
    print("STUDENT_LOGIN", s.status_code)
    if s.status_code == 200:
        sh = {"Authorization": f"Bearer {s.json()['access_token']}"}
        paper_ok = False
        if published:
            eid = published[0]["id"]
            paper = client.get(f"{BASE}/exams/{eid}/paper", headers=sh)
            print("PAPER", paper.status_code, "q=" + str(len(paper.json().get("questions", []))) if paper.status_code == 200 else paper.text[:120])
            paper_ok = paper.status_code == 200 and len(paper.json().get("questions", [])) > 0
        print(json.dumps({"users_api": users_ok, "published_exams": len(published), "paper_ok": paper_ok}))
        return 0 if (published and paper_ok) else 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
