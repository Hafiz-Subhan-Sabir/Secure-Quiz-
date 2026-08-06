"""Desktop CLI — smoke, preview, and full secure exam runtime."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from intelliQuiz_desktop.core.config import get_settings
from intelliQuiz_desktop.core.device import device_fingerprint
from intelliQuiz_desktop.pairing.qr import build_pairing_payload, pairing_qr_json
from intelliQuiz_desktop.storage.event_store import EncryptedEventStore
from intelliQuiz_desktop.sync.api_client import ApiClient
from intelliQuiz_desktop.sync.worker import SyncWorker


def cmd_smoke(args: argparse.Namespace) -> int:
    settings = get_settings()
    api = ApiClient()
    try:
        login = api.login(args.email, args.password)
        print("login_ok", login["role"])
        exams = api.list_exams()
        if not exams:
            print("no_exams")
            return 1
        exam = exams[0]
        session = api.create_session(exam["id"], device_fingerprint())
        print("session", session["id"])

        try:
            paper = api.get_exam_paper(exam["id"])
            print("paper_questions", len(paper.get("questions") or []))
        except Exception as exc:
            print("paper_warn", exc)

        store = EncryptedEventStore(settings.data_dir / "events.db")
        store.append(
            session_id=session["id"],
            type="heartbeat",
            severity=0.0,
            payload={"source": "smoke"},
        )
        worker = SyncWorker(store, api)
        result = worker.flush(session["id"])
        print("sync", result)

        payload = build_pairing_payload(
            session_id=session["id"],
            pairing_token=session["pairing_token"],
            desktop_endpoint=f"ws://{settings.local_ws_host}:{settings.local_ws_port}/pair",
        )
        print("qr_payload", pairing_qr_json(payload))
        store.close()
        return 0
    finally:
        api.close()


def cmd_preview(_args: argparse.Namespace) -> int:
    """Open the static student UI preview (visual only)."""
    html = Path(__file__).resolve().parent / "ui" / "exam_panel.html"
    if not html.exists():
        print("missing", html)
        return 1
    webbrowser.open(html.as_uri())
    print("opened", html)
    print("Note: preview is visual-only. Use `run` for real webcam/QR/app-lock/ML.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Start local Desktop runtime (webcam ML + app lock + QR + quiz UI)."""
    settings = get_settings()

    try:
        from intelliQuiz_desktop.ai.landmarks import ensure_face_landmarker

        path = ensure_face_landmarker(settings.face_landmarker_path)
        print("face_landmarker", path)
    except Exception as exc:
        print("face_landmarker_warn", exc)

    if not settings.model_path.exists():
        print("WARN: FaceGest model missing at", settings.model_path)
        print("Train with: cd ml && python -m src.train --config configs/train_mediapipe.yaml")

    import threading

    import uvicorn

    from intelliQuiz_desktop.core.certs import ensure_desktop_tls
    from intelliQuiz_desktop.core.device import discover_lan_ip
    from intelliQuiz_desktop.runtime.local_api import create_app
    from intelliQuiz_desktop.runtime.session_controller import SessionController

    controller = SessionController(settings)
    app = create_app(controller)

    lan = discover_lan_ip()
    cert_path, key_path = ensure_desktop_tls(settings.data_dir, lan)

    browse_host = "127.0.0.1" if settings.local_ui_host in ("0.0.0.0", "::") else settings.local_ui_host
    url = f"http://{browse_host}:{settings.local_ui_port}/"
    phone_url = f"https://{lan}:{settings.local_phone_https_port}/phone"

    print("IntelliQuiz Desktop runtime")
    print("  UI      ", url)
    print("  Phone   ", phone_url, "(HTTPS - required for mobile camera)")
    print("  Pair WSS", f"wss://{lan}:{settings.local_phone_https_port}/ws/pair")
    print("  API     ", settings.api_base_url)
    print("  AI      ", "ready" if controller.engine.ready else "NOT LOADED")
    print("  Model   ", settings.model_path)
    print("  Note    ", "Phone + PC must share the same router (Ethernet+WiFi is OK).")
    print("  Cert    ", "Phone will warn once - tap Advanced then Proceed / Continue.")

    def run_phone_https() -> None:
        uvicorn.run(
            app,
            host=settings.local_ui_host,
            port=settings.local_phone_https_port,
            ssl_certfile=str(cert_path),
            ssl_keyfile=str(key_path),
            log_level="warning",
        )

    threading.Thread(target=run_phone_https, name="phone-https", daemon=True).start()

    if not args.no_browser:
        webbrowser.open(url)

    try:
        uvicorn.run(app, host=settings.local_ui_host, port=settings.local_ui_port, log_level="info")
    finally:
        controller.shutdown_runtime()

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="intelliquiz-desktop")
    sub = parser.add_subparsers(dest="cmd", required=True)

    smoke = sub.add_parser("smoke", help="Login → session → local encrypt → sync")
    smoke.add_argument("--email", default="student@intelliquiz.dev")
    smoke.add_argument("--password", default="Student123!")
    smoke.set_defaults(func=cmd_smoke)

    preview = sub.add_parser("preview", help="Open static UI preview (no backend logic)")
    preview.set_defaults(func=cmd_preview)

    run = sub.add_parser("run", help="Full runtime: webcam ML, app lock, QR, quiz UI")
    run.add_argument("--no-browser", action="store_true", help="Do not auto-open the UI")
    run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
