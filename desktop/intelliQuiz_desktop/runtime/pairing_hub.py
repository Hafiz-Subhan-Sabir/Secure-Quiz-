"""QR pairing + local WebSocket hub for phone / Android secondary camera."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import quote

from intelliQuiz_desktop.core.device import discover_lan_ip
from intelliQuiz_desktop.pairing.qr import build_pairing_payload


@dataclass
class PairingState:
    active: bool = False
    paired: bool = False
    session_id: str = ""
    pairing_token: str = ""
    qr_payload: dict[str, Any] = field(default_factory=dict)
    qr_png_data_uri: str = ""
    qr_text: str = ""  # exact string encoded in the QR (must be a URL)
    desktop_endpoint: str = ""
    mobile_camera_url: str = ""
    last_android_message: str = ""
    android_frames: int = 0
    last_alive_at: float = 0.0
    camera_live: bool = False


class PairingHub:
    """Issues mobile-camera QR URLs and accepts phone / Android WS handshakes.

    The QR code ALWAYS encodes an http(s) URL so phone camera apps open the browser.
    """

    # Treat phone camera as gone if no alive/frame signal within this window.
    ALIVE_TIMEOUT_SEC = 8.0

    def __init__(
        self,
        *,
        host: str,
        port: int,
        ui_port: int = 8765,
        phone_https_port: int = 8767,
        on_paired: Callable[[], None] | None = None,
        on_unpaired: Callable[[], None] | None = None,
        on_android_event: Callable[[str, float, dict[str, Any]], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.ui_port = ui_port
        self.phone_https_port = phone_https_port
        self.on_paired = on_paired
        self.on_unpaired = on_unpaired
        self.on_android_event = on_android_event
        self.state = PairingState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Any = None
        self._last_phone_evidence_at = 0.0
        self._phone_frame_count = 0
        self._last_phone_frame_ts = ""
        self._last_desktop_frame_ts = ""
        self._latest_jpeg: bytes | None = None
        self._client_count = 0
        # WebSocket object ids that completed a valid pair handshake.
        self._authed_ws: set[int] = set()

    def begin_session(
        self,
        *,
        session_id: str,
        pairing_token: str,
        exam_code: str | None = None,
        preserve_live: bool = False,
    ) -> dict[str, Any]:
        lan = discover_lan_ip()
        # Phone browsers block camera on plain http://LAN — use HTTPS + WSS on the phone port.
        endpoint = f"wss://{lan}:{self.phone_https_port}/ws/pair"
        mobile_url = (
            f"https://{lan}:{self.phone_https_port}/phone"
            f"?session_id={quote(session_id, safe='')}"
            f"&pairing_token={quote(pairing_token, safe='')}"
            f"&ws={quote(endpoint, safe='')}"
        )
        payload = build_pairing_payload(
            session_id=session_id,
            pairing_token=pairing_token,
            desktop_endpoint=endpoint,
            exam_code=exam_code,
        )
        payload["mobile_camera_url"] = mobile_url
        png_uri = _qr_png_data_uri(mobile_url)
        if not png_uri:
            raise RuntimeError("Could not generate QR image — install the qrcode package")
        if not mobile_url.startswith("https://"):
            raise RuntimeError("Mobile camera QR must be an https:// URL for phone camera access")
        with self._lock:
            keep_paired = bool(
                preserve_live
                and self.state.paired
                and self.state.session_id == session_id
                and self.state.pairing_token == pairing_token
            )
            keep_jpeg = self._latest_jpeg if keep_paired else None
            keep_frames = self._phone_frame_count if keep_paired else 0
            keep_alive = self.state.last_alive_at if keep_paired else 0.0
            self.state = PairingState(
                active=True,
                paired=keep_paired,
                session_id=session_id,
                pairing_token=pairing_token,
                qr_payload=payload,
                qr_png_data_uri=png_uri,
                qr_text=mobile_url,
                desktop_endpoint=endpoint,
                mobile_camera_url=mobile_url,
                last_alive_at=keep_alive,
                camera_live=keep_paired,
                android_frames=keep_frames if keep_paired else 0,
                last_android_message=(
                    self.state.last_android_message
                    if keep_paired
                    else ""
                ),
            )
            self._latest_jpeg = keep_jpeg
            if not keep_paired:
                self._phone_frame_count = 0
                self._authed_ws.clear()
        # Phone pairing uses FastAPI WSS on the HTTPS phone port (8767), not this legacy WS.
        # Keep PairingHub as state + message handler only.
        return self.status()

    def latest_jpeg(self) -> bytes | None:
        """Most recent JPEG frame from the phone camera (for identity enroll)."""
        with self._lock:
            return self._latest_jpeg

    def mark_paired_local(self) -> None:
        """UI / lab override when a physical phone is unavailable."""
        with self._lock:
            self.state.paired = True
            self.state.camera_live = True
            self.state.last_alive_at = time.time()
            self.state.last_android_message = "Marked paired locally (lab mode)"
        if self.on_paired:
            self.on_paired()

    def touch_alive(self, *, ws_id: int | None = None) -> None:
        re_paired = False
        with self._lock:
            if ws_id is not None and ws_id not in self._authed_ws:
                return
            self.state.last_alive_at = time.time()
            self.state.camera_live = True
            # Re-arm pairing after soft expiry while the authenticated socket is still open.
            if self.state.active and not self.state.paired and (
                ws_id is None or ws_id in self._authed_ws
            ):
                self.state.paired = True
                self.state.last_android_message = "Phone camera re-paired (alive)"
                re_paired = True
            elif self.state.paired:
                self.state.last_android_message = "Phone camera alive"
        if re_paired and self.on_paired:
            try:
                self.on_paired()
            except Exception:
                pass

    def mark_camera_lost(self, reason: str = "Phone camera closed") -> None:
        was_paired = False
        with self._lock:
            was_paired = self.state.paired or self.state.camera_live
            self.state.camera_live = False
            self.state.paired = False
            self.state.last_android_message = reason
        if was_paired and self.on_unpaired:
            self.on_unpaired()

    def status(self) -> dict[str, Any]:
        now = time.time()
        unpaired_cb = False
        with self._lock:
            s = self.state
            lab = s.last_android_message.startswith("Marked paired")
            # Soft-expire live flag; hard-expire pairing after 2x alive window
            if s.paired and s.last_alive_at and not lab:
                age = now - s.last_alive_at
                if age > self.ALIVE_TIMEOUT_SEC:
                    s.camera_live = False
                if age > self.ALIVE_TIMEOUT_SEC * 2.5:
                    s.paired = False
                    s.camera_live = False
                    s.last_android_message = "Phone camera timed out — reopen the page"
                    unpaired_cb = True
            live = bool(
                lab
                or (
                    s.camera_live
                    and s.last_alive_at
                    and (now - s.last_alive_at) <= self.ALIVE_TIMEOUT_SEC
                )
            )
            # Recently paired with frames still counts as paired during grace window
            recently_alive = bool(
                s.last_alive_at and (now - s.last_alive_at) <= self.ALIVE_TIMEOUT_SEC * 2.5
            )
            paired = bool(s.paired and (live or lab or recently_alive))
            snapshot = {
                "active": s.active,
                "paired": paired,
                "camera_live": live or lab,
                "session_id": s.session_id,
                "desktop_endpoint": s.desktop_endpoint,
                "mobile_camera_url": s.mobile_camera_url,
                "qr_text": s.qr_text,
                "qr_payload": s.qr_payload,
                "qr_png_data_uri": s.qr_png_data_uri,
                "last_android_message": s.last_android_message,
                "android_frames": s.android_frames,
            }
        if unpaired_cb and self.on_unpaired:
            try:
                self.on_unpaired()
            except Exception:
                pass
        return snapshot

    def stop(self) -> None:
        if self._loop and self._server:
            fut = asyncio.run_coroutine_threadsafe(self._server.wait_closed(), self._loop)
            try:
                self._loop.call_soon_threadsafe(self._server.close)
                fut.result(timeout=2)
            except Exception:
                pass
        with self._lock:
            self.state.active = False

    def _ensure_server(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_server, name="pairing-ws", daemon=True)
        self._thread.start()

    def _run_server(self) -> None:
        try:
            from websockets.server import serve
        except Exception:
            return

        async def handler(websocket: Any) -> None:
            try:
                async for raw in websocket:
                    await self._handle_message(websocket, raw)
            except Exception:
                pass
            finally:
                self.client_disconnected()

        async def main() -> None:
            self._server = await serve(handler, self.host, self.port, process_request=None)
            await self._server.wait_closed()

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(main())
        except Exception:
            pass

    def client_connected(self) -> None:
        with self._lock:
            self._client_count = max(0, int(getattr(self, "_client_count", 0))) + 1

    def client_disconnected(self, *, ws_id: int | None = None) -> None:
        """Phone WebSocket dropped — only clear live when no clients remain.

        Mobile browsers / networks flap briefly. Keep `paired` until the alive
        timeout expires so confirm-camera / exam start still succeed, and so a
        quick reconnect does not wipe the handshake.
        """
        with self._lock:
            if ws_id is not None:
                self._authed_ws.discard(ws_id)
            self._client_count = max(0, int(getattr(self, "_client_count", 0)) - 1)
            if self._client_count > 0:
                self.state.last_android_message = "Secondary socket closed — primary still live"
                return
            self.state.camera_live = False
            self.state.last_android_message = (
                "Phone socket closed — reopen camera page if pairing expires"
            )
            # Keep paired flag; status() will soft-expire via ALIVE_TIMEOUT.

    async def _send(self, websocket: Any, payload: dict[str, Any]) -> None:
        text = json.dumps(payload)
        if hasattr(websocket, "send_text"):
            await websocket.send_text(text)
        else:
            await websocket.send(text)

    def _ws_authed(self, websocket: Any) -> bool:
        return id(websocket) in self._authed_ws

    async def _handle_message(self, websocket: Any, raw: Any) -> None:
        ws_id = id(websocket)
        try:
            if isinstance(raw, bytes):
                # Only accept frames from sockets that completed pair handshake.
                if not self._ws_authed(websocket):
                    return
                re_paired = False
                with self._lock:
                    self.state.android_frames += 1
                    self.state.last_alive_at = time.time()
                    self.state.camera_live = True
                    if self.state.active and not self.state.paired:
                        self.state.paired = True
                        self.state.last_android_message = "Phone camera re-paired (frame)"
                        re_paired = True
                    else:
                        self.state.last_android_message = "Phone camera frame received"
                    self._phone_frame_count += 1
                    self._latest_jpeg = raw
                    frame_n = self._phone_frame_count
                    phone_ts = self._last_phone_frame_ts
                    desktop_ts = datetime.now(UTC).isoformat()
                    self._last_desktop_frame_ts = desktop_ts
                if re_paired and self.on_paired:
                    try:
                        self.on_paired()
                    except Exception:
                        pass
                # Save at most one quiet "paired" still — not every N seconds.
                now = time.time()
                if (
                    self.on_android_event
                    and frame_n == 1
                    and (now - self._last_phone_evidence_at) >= 1.0
                ):
                    self._last_phone_evidence_at = now
                    b64 = base64.b64encode(raw).decode("ascii")
                    self.on_android_event(
                        "android_snapshot",
                        0.15,
                        {
                            "source": "android_camera",
                            "plain_language": "Phone paired — first room photo.",
                            "gesture_label": "PHONE",
                            "image_data_uri": f"data:image/jpeg;base64,{b64}",
                            "capture_reason": "android_pair_snapshot",
                            "android_frame_index": frame_n,
                            "phone_frame_ts": phone_ts,
                            "desktop_receive_ts": desktop_ts,
                            "cheating_attempt": False,
                        },
                    )
                return

            data = json.loads(raw)
        except Exception:
            return

        msg_type = data.get("type")
        with self._lock:
            expected_sid = self.state.session_id
            expected_tok = self.state.pairing_token

        if msg_type == "pair":
            if data.get("session_id") == expected_sid and data.get("pairing_token") == expected_tok:
                with self._lock:
                    self.state.paired = True
                    self.state.camera_live = True
                    self.state.last_alive_at = time.time()
                    self.state.last_android_message = "Phone camera paired successfully"
                    self._authed_ws.add(ws_id)
                await self._send(websocket, {"type": "pair_ok", "mode": "camera_lock"})
                if self.on_paired:
                    self.on_paired()
            else:
                with self._lock:
                    reload_url = self.state.mobile_camera_url
                    self._authed_ws.discard(ws_id)
                await self._send(
                    websocket,
                    {
                        "type": "pair_fail",
                        "reason": "token_mismatch",
                        "message": "QR was refreshed on the PC — open the latest link",
                        "reload_url": reload_url,
                    },
                )
            return

        if not self._ws_authed(websocket):
            return

        if msg_type == "frame_meta":
            with self._lock:
                self._last_phone_frame_ts = str(data.get("ts") or "")
            return

        if msg_type == "camera_alive":
            self.touch_alive(ws_id=ws_id)
            return

        if msg_type == "camera_lost":
            self.mark_camera_lost(str(data.get("reason") or "Phone camera turned off"))
            return

        if msg_type == "env_anomaly":
            try:
                severity = float(data.get("severity", 0.7))
            except (TypeError, ValueError):
                severity = 0.7
            label = str(data.get("gesture_label") or "ENV")
            plain = str(
                data.get("plain_language")
                or "Phone camera saw unexpected room activity."
            )
            image = data.get("image_data_uri")
            if not image and self._latest_jpeg:
                image = (
                    "data:image/jpeg;base64,"
                    + base64.b64encode(self._latest_jpeg).decode("ascii")
                )
            payload = {
                "source": "android_camera",
                "plain_language": plain,
                "gesture_label": label,
                "image_data_uri": image,
                "capture_reason": "android_env_anomaly",
                "cheating_attempt": label
                in {"PHONE_APP_SWITCH", "PHONE_HELPER", "APP_SWITCH", "PHONE_MOTION"}
                or severity >= 0.8,
            }
            with self._lock:
                self.state.last_android_message = payload["plain_language"]
                self.state.last_alive_at = time.time()
                self.state.camera_live = True
            if self.on_android_event:
                self.on_android_event("android_env_anomaly", severity, payload)


def _qr_png_data_uri(text: str) -> str:
    """Encode `text` (must be a URL) into a phone-scannable QR PNG data URI."""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except Exception:
        return ""
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
