"""Full IntelliQuiz E2E retest: API + Desktop + phone WSS + admin report."""

from __future__ import annotations

import io
import json
import ssl
import subprocess
import sys
import time
import urllib.parse

import httpx

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

from PIL import Image

API = "http://127.0.0.1:8080/api/v1"
DESK = "http://127.0.0.1:8765"
errors: list[str] = []


def ok(msg: str) -> None:
    print("OK ", msg)


def fail(msg: str) -> None:
    print("FAIL", msg)
    errors.append(msg)


def main() -> int:
    api = httpx.Client(base_url=API, timeout=60)
    d = httpx.Client(base_url=DESK, timeout=90)

    # 1) Health
    try:
        h = api.get("/health").json()
        assert h.get("status") == "ok"
        ok(f"API health {h}")
    except Exception as e:
        fail(f"API health: {e}")
        return 1

    try:
        dh = d.get("/api/health").json()
        assert dh.get("ok")
        ok(f"Desktop health ai_ready={dh.get('ai_ready')}")
    except Exception as e:
        fail(f"Desktop health: {e}")
        return 1

    # 2) Login + exams
    try:
        login = d.post(
            "/api/login",
            json={"email": "student@intelliquiz.dev", "password": "Student123!"},
        ).json()
        assert login.get("role") == "student"
        assert login.get("full_name")
        ok(f"Student login name={login.get('full_name')}")
    except Exception as e:
        fail(f"Login: {e}")
        return 1

    exams = d.get("/api/exams").json()
    exam = next((e for e in exams if "Sample" in e.get("title", "")), exams[0] if exams else None)
    if not exam:
        fail("No exams")
        return 1
    ok(f"Exam selected: {exam['title']}")

    # 3) Start session
    st = d.post("/api/start", json={"exam_id": exam["id"]})
    if st.status_code != 200:
        fail(f"start {st.status_code} {st.text[:300]}")
        return 1
    sj = st.json()
    sid = sj["session_id"]
    paper = sj.get("paper") or {}
    qs = paper.get("questions") or []
    pair = sj.get("pairing") or {}
    ok(f"Session {sid[:8]}… questions={len(qs)}")
    mobile_url = pair.get("mobile_camera_url") or ""
    if not mobile_url.startswith("https://"):
        fail(f"QR URL not https: {mobile_url}")
    else:
        ok(f"QR URL https OK host={urllib.parse.urlparse(mobile_url).hostname}")
    if not pair.get("qr_png_data_uri", "").startswith("data:image/png"):
        fail("QR PNG missing")
    else:
        ok("QR PNG present")

    # 4) Phone page
    try:
        phone2 = httpx.get(mobile_url, verify=False, timeout=15)
        if phone2.status_code != 200:
            fail(f"phone page status {phone2.status_code}")
        elif "Allow camera" not in phone2.text and "pair" not in phone2.text.lower():
            fail("phone page content unexpected")
        else:
            ok("Phone camera page loads over HTTPS")
    except Exception as e:
        fail(f"Phone HTTPS page: {e}")

    # 5) Real WebSocket pair + binary JPEG (simulates phone) — keep socket open
    ws = None
    session_id = sid
    pairing_token = ""
    ws_ep = pair.get("desktop_endpoint") or ""
    sslopt = {"cert_reqs": ssl.CERT_NONE}
    try:
        parsed = urllib.parse.urlparse(mobile_url)
        q = urllib.parse.parse_qs(parsed.query)
        session_id = q.get("session_id", [sid])[0]
        pairing_token = q.get("pairing_token", [""])[0]
        ws_ep = q.get("ws", [ws_ep])[0]
        ws = websocket.create_connection(ws_ep, sslopt=sslopt, timeout=20)
        ws.send(json.dumps({"type": "pair", "session_id": session_id, "pairing_token": pairing_token}))
        reply = json.loads(ws.recv())
        if reply.get("type") != "pair_ok":
            fail(f"pair reply {reply}")
        else:
            ok("Phone WSS pair_ok")
        img = Image.new("RGB", (160, 120), (20, 80, 60))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        jpeg = buf.getvalue()
        ws.send(jpeg, opcode=websocket.ABNF.OPCODE_BINARY)
        ws.send(json.dumps({"type": "camera_alive"}))
        time.sleep(1.0)
        status = d.get("/api/status").json()
        pairing = status.get("pairing") or {}
        if not pairing.get("paired"):
            fail(f"Desktop not paired after WS: {pairing}")
        else:
            ok(f"Desktop paired frames={pairing.get('android_frames')}")
    except Exception as e:
        fail(f"Phone WSS handshake: {e}")

    # 6) Confirm + enter exam while phone still connected
    r = d.post("/api/phase/confirm-camera", json={"prefer_phone": True})
    if r.status_code != 200:
        fail(f"confirm-camera {r.status_code} {r.text[:200]}")
    else:
        ok(f"confirm-camera identity={r.json().get('identity_source')}")

    ent = d.post("/api/phase/exam")
    if ent.status_code != 200:
        fail(f"enter exam {ent.status_code} {ent.text[:200]}")
    else:
        ok(f"enter exam phase={ent.json().get('phase')}")

    # Grace-period check: close phone socket, confirm still paired briefly
    if ws is not None:
        try:
            ws.close()
            time.sleep(0.5)
            st_grace = d.get("/api/status").json()
            if (st_grace.get("pairing") or {}).get("paired"):
                ok("pairing survives brief phone disconnect (grace period)")
            else:
                fail("pairing cleared immediately after phone disconnect")
            # Reconnect phone for the rest of the exam (real phones keep page open)
            ws = websocket.create_connection(ws_ep, sslopt=sslopt, timeout=20)
            ws.send(
                json.dumps(
                    {"type": "pair", "session_id": session_id, "pairing_token": pairing_token}
                )
            )
            again = json.loads(ws.recv())
            if again.get("type") == "pair_ok":
                ws.send(json.dumps({"type": "camera_alive"}))
                ok("phone reconnected for exam")
            else:
                fail(f"phone re-pair failed {again}")
        except Exception as e:
            fail(f"grace check: {e}")

    # 7) Abnormal capture
    sim = d.post("/api/simulate-abnormal")
    if sim.status_code != 200:
        fail(f"simulate {sim.status_code} {sim.text[:200]}")
    else:
        sj2 = sim.json()
        ok(
            f"simulate gesture={sj2.get('gesture')} cam={sj2.get('has_webcam')} "
            f"screen={sj2.get('has_screen')}"
        )

    st2 = d.get("/api/status").json()
    ok(
        f"local evidence_count={(st2.get('monitor') or {}).get('evidence_count')} "
        f"risk={(st2.get('monitor') or {}).get('session_risk')}"
    )

    # 8) Answers + submit
    for i, qitem in enumerate(qs):
        ar = d.post("/api/answer", json={"question_id": qitem["id"], "choice_index": 1})
        if ar.status_code != 200:
            fail(f"answer q{i} {ar.status_code} {ar.text[:120]}")
    ok(f"answered {len(qs)} questions")

    sub = d.post("/api/submit")
    if sub.status_code != 200:
        fail(f"submit {sub.status_code} {sub.text[:300]}")
    else:
        ok(f"submit sync={sub.json().get('sync')}")

    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass

    time.sleep(0.8)

    # 9) Admin report
    admin = api.post(
        "/auth/login", json={"email": "admin@intelliquiz.dev", "password": "Admin123!"}
    ).json()
    ah = {"Authorization": f"Bearer {admin['access_token']}"}
    rep = api.get(f"/reports/sessions/{sid}", headers=ah)
    if rep.status_code != 200:
        fail(f"report {rep.status_code} {rep.text[:200]}")
    else:
        j = rep.json()
        ok(
            f"report student={j.get('student_name')} "
            f"quiz={j.get('quiz_score')}/{j.get('quiz_max_score')} ({j.get('quiz_percent')}%)"
        )
        ok(
            f"report evidence={len(j.get('evidence') or [])} "
            f"flags={j.get('flags')} events={j.get('event_count')}"
        )
        if not j.get("student_name"):
            fail("missing student_name")
        if not j.get("evidence"):
            fail("no evidence photos in admin report")
        if (j.get("quiz_max_score") or 0) <= 0:
            fail("quiz not graded")
        sources = {e.get("source") for e in (j.get("evidence") or [])}
        ok(f"evidence sources={sources}")
        if "android_camera" not in sources and "primary_webcam" not in sources and "screen" not in sources:
            fail("unexpected empty evidence sources")

    att = api.get("/sessions/attempts", headers=ah).json()
    mine = next((a for a in att if a["session_id"] == sid), None)
    if not mine:
        fail("attempt missing from list")
    else:
        ok(
            f"attempt flagged={mine.get('flagged')} photos={mine.get('evidence_count')} "
            f"score={mine.get('quiz_percent')} risk={mine.get('last_risk_score')}"
        )
        if mine.get("evidence_count", 0) < 1:
            fail("attempt evidence_count < 1")
        if float(mine.get("last_risk_score") or 0) <= 0 and mine.get("flagged"):
            # still ok if flagged via evidence; warn only
            ok("note: risk score low but flagged via photos")

    print("\n==== SUMMARY ====")
    if errors:
        print(f"{len(errors)} FAILURES:")
        for e in errors:
            print(" -", e)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
