# IntelliQuiz Desktop

Student exam client with **real** proctoring logic: webcam ML, QR phone pairing, app lock, encrypted logs, sync.

## Full runtime (recommended)

Backend must be on `:8080`. Then:

```powershell
cd "D:\subhan\Intelligence Quiz\desktop"
python -m intelliQuiz_desktop.cli run
```

Opens `http://127.0.0.1:8765/` — student flow:

1. **Sign in** — `student@intelliquiz.dev` / `Student123!` (not Admin website)
2. **Start secure session** — creates backend session + loads exam paper
3. **Face check** — OpenCV webcam + MediaPipe Face Landmarker + FaceGest RF model
4. **Phone QR** — `pairing.qr.v1` handshake on `ws://127.0.0.1:8766/pair`
5. **Quiz** — app lock engages (kills Discord/TeamViewer/AnyDesk/etc.); continuous ML monitoring
6. Abnormal gesture / looking away → **webcam JPEG + screen snapshot** → encrypted SQLite → sync → Admin photo reports

### App lock

| Category | Apps | Behavior |
|----------|------|----------|
| Hard | Discord, TeamViewer, AnyDesk, Zoom, Slack, Telegram, RustDesk, … | Detect + terminate during exam |
| Browser | Chrome, Edge, Firefox, … | Flagged; not killed while UI runs in a browser (`IQ_DESKTOP_APP_LOCK_KILL_BROWSERS=true` for kiosk) |

### Static preview only

```powershell
python -m intelliQuiz_desktop.cli preview
```

Visual mock without backend/webcam ML.

## API smoke

```powershell
python -m intelliQuiz_desktop.cli smoke
```

## Modules

| Package | Purpose |
|---------|---------|
| `runtime` | Session controller, face monitor, app lock, pairing hub, local API |
| `ai` | FaceGest model + MediaPipe landmarks → 1404 features |
| `storage` | Encrypted SQLite event log |
| `sync` | Central API client + idempotent flush |
| `pairing` | QR payload (`pairing.qr.v1`) |
| `security` | Blacklisted process helpers |
| `ui` | `exam_runtime.html` (live) + `exam_panel.html` (preview) |
