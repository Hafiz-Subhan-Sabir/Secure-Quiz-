"""Local Desktop FastAPI — bridges exam UI to real runtime backends."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from intelliQuiz_desktop.runtime.session_controller import SessionController

UI_DIR = Path(__file__).resolve().parents[1] / "ui"


class LoginBody(BaseModel):
    email: str
    password: str


class StartExamBody(BaseModel):
    exam_id: str


class AnswerBody(BaseModel):
    question_id: str
    choice_index: int = Field(ge=0)


class ConfirmCameraBody(BaseModel):
    prefer_phone: bool = False


class EnrollBody(BaseModel):
    source: str = "auto"  # auto | webcam | phone


def create_app(controller: SessionController | None = None) -> FastAPI:
    ctrl = controller or SessionController()
    app = FastAPI(title="IntelliQuiz Desktop Runtime", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.controller = ctrl

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "intelliquiz-desktop", "ai_ready": ctrl.engine.ready}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return ctrl.status()

    @app.post("/api/login")
    def login(body: LoginBody) -> dict[str, Any]:
        try:
            return ctrl.login(body.email, body.password)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/api/exams")
    def exams() -> list[dict[str, Any]]:
        try:
            return ctrl.list_exams()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/start")
    def start(body: StartExamBody) -> dict[str, Any]:
        try:
            return ctrl.start_exam(body.exam_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/phase/pairing")
    def phase_pairing() -> dict[str, Any]:
        return ctrl.advance_to_pairing()

    @app.post("/api/phase/confirm-camera")
    def confirm_camera(body: ConfirmCameraBody = ConfirmCameraBody()) -> dict[str, Any]:
        try:
            return ctrl.confirm_camera(prefer_phone=body.prefer_phone)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/identity/status")
    def identity_status() -> dict[str, Any]:
        return ctrl.identity_status()

    @app.post("/api/identity/enroll")
    def identity_enroll(body: EnrollBody | None = None) -> dict[str, Any]:
        try:
            source = (body.source if body else "auto") or "auto"
            return ctrl.enroll_identity(source=source)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/identity/enroll/begin-phone")
    def identity_enroll_begin_phone() -> dict[str, Any]:
        try:
            return ctrl.begin_enrollment_pairing()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/identity/enroll/defer-phone")
    def identity_enroll_defer_phone() -> dict[str, Any]:
        try:
            return ctrl.defer_enrollment_to_phone()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/phase/exam")
    def phase_exam(require_pair: bool = False) -> dict[str, Any]:
        try:
            return ctrl.enter_exam(require_pair=require_pair)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/pairing/mark")
    def mark_paired() -> dict[str, Any]:
        return ctrl.mark_phone_paired()

    @app.post("/api/phase/resume")
    def resume_exam() -> dict[str, Any]:
        try:
            return ctrl.resume_after_camera()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/answer")
    def answer(body: AnswerBody) -> dict[str, Any]:
        try:
            return ctrl.save_answer(body.question_id, body.choice_index)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/submit")
    def submit(force: bool = False) -> dict[str, Any]:
        try:
            return ctrl.submit(force=force)
        except Exception as exc:
            # Auto-retry once as forced submit when camera pause blocks the student
            detail = str(exc)
            if "paused" in detail.lower() or "camera" in detail.lower():
                try:
                    return ctrl.submit(force=True)
                except Exception as exc2:
                    raise HTTPException(status_code=400, detail=str(exc2)) from exc2
            raise HTTPException(status_code=400, detail=detail) from exc

    @app.get("/api/result")
    def last_result() -> dict[str, Any]:
        try:
            return ctrl.get_last_result()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/my-results")
    def my_results() -> list[dict[str, Any]]:
        try:
            return ctrl.list_my_results()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/another-exam")
    def another_exam(clear_local: bool = True) -> dict[str, Any]:
        try:
            return ctrl.prepare_another_exam(clear_local=clear_local)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/logout")
    def logout(clear_local: bool = True) -> dict[str, Any]:
        return ctrl.logout(clear_local=clear_local)

    @app.get("/api/storage")
    def storage() -> dict[str, Any]:
        return ctrl.storage_info()

    @app.post("/api/simulate-abnormal")
    def simulate() -> dict[str, Any]:
        return ctrl.simulate_abnormal()

    @app.get("/api/camera.jpg")
    def camera_jpeg() -> Response:
        data = ctrl.monitor.latest_jpeg()
        if not data:
            raise HTTPException(status_code=404, detail="No camera frame yet")
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.websocket("/ws/pair")
    async def ws_pair(websocket: WebSocket) -> None:
        """Phone pairing over WSS (same HTTPS server phones use for camera)."""
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await ctrl.pairing._handle_message(websocket, message["bytes"])
                elif message.get("text") is not None:
                    await ctrl.pairing._handle_message(websocket, message["text"])
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            ctrl.pairing.client_disconnected()

    @app.get("/")
    def index() -> FileResponse:
        path = UI_DIR / "exam_runtime.html"
        if not path.exists():
            path = UI_DIR / "exam_panel.html"
        return FileResponse(path)

    @app.get("/phone")
    def phone_camera() -> FileResponse:
        path = UI_DIR / "phone_camera.html"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Phone camera page missing")
        return FileResponse(path)

    if UI_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    return app
