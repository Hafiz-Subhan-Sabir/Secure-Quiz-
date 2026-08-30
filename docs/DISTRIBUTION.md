# IntelliQuiz — Install & Distribution Guide

This guide explains how to build installable files so users **without the source code** can download, install, and run IntelliQuiz.

---

## What you distribute

| Component | Install file | Who uses it |
|-----------|--------------|-------------|
| **Backend API** | Run on a server (or local PC) | Required for all clients |
| **Admin Web** | Static website folder (`dist/`) | Instructors / admins |
| **Desktop App** | `.exe` (Windows) or folder bundle | Students taking exams |
| **Android App** | `.apk` | Student phone camera |

---

## 1. Backend API (central server)

### Option A — Run from source (developers)

```powershell
cd backend
pip install -e .
copy .env.example .env
python -m app.main
```

API: `http://127.0.0.1:8080`  
Docs: `http://127.0.0.1:8080/docs`

### Option B — Production with TLS

In `backend/.env`:

```env
IQ_SSL_ENABLED=true
IQ_JWT_SECRET=use-a-long-random-secret-here
```

Restart the backend. It auto-generates `backend/certs/api.crt` and `api.key`.

Point clients to: `https://YOUR-SERVER:8080/api/v1`

### Give users without code

1. Copy the whole `backend/` folder to the server
2. Install Python 3.11+
3. Run:

```powershell
pip install -e .
python -m app.main
```

Or use a process manager (NSSM, systemd) to keep it running.

---

## 2. Admin Web (browser panel)

### Build once

```powershell
cd admin-web
npm install
npm run build
```

Output: `admin-web/dist/` (HTML + JS + CSS)

### Give users without code

**Option A — Simple local serve**

```powershell
npx serve admin-web/dist -l 5173
```

Open: `http://localhost:5173`  
Login: `admin@intelliquiz.dev` / `Admin123!`

**Option B — Production**

Upload `dist/` to any static host (Nginx, IIS, Netlify, S3).

Set API URL in build env:

```powershell
$env:VITE_API_BASE="https://your-server:8080/api/v1"
npm run build
```

---

## 3. Desktop App (student exam client)

### Build Windows `.exe` (recommended for end users)

From repo root:

```powershell
cd desktop
pip install -e ".[dev]"
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File ..\scripts\build-desktop.ps1
```

Output: `desktop/dist/IntelliQuizDesktop/IntelliQuizDesktop.exe`

### Give users without code

1. Zip the entire `desktop/dist/IntelliQuizDesktop/` folder
2. User unzips anywhere (e.g. `C:\IntelliQuiz\`)
3. User creates `.env` next to the exe **or** sets environment variables:

```env
IQ_DESKTOP_API_BASE_URL=http://YOUR-SERVER:8080/api/v1
```

4. Double-click **`IntelliQuizDesktop.exe`**

The app will:
- Start the local exam runtime on `http://127.0.0.1:8765`
- Open a **kiosk browser window** for the exam (blocks other browsers during exam)
- Enable webcam AI + app lock + encrypted offline logs

### Run from source (developers)

```powershell
cd desktop
pip install -e .
python -m intelliQuiz_desktop.cli run
```

Smoke test:

```powershell
python -m intelliQuiz_desktop.cli smoke
```

---

## 4. Android APK (phone camera)

### Build debug APK (testing)

```powershell
cd android
.\gradlew.bat assembleDebug
```

APK path:

```
android/app/build/outputs/apk/debug/app-debug.apk
```

### Build release APK (distribution)

1. Create a signing keystore (once):

```powershell
keytool -genkey -v -keystore intelliquiz-release.keystore -alias intelliquiz -keyalg RSA -keysize 2048 -validity 10000
```

2. Add signing config to `android/app/build.gradle.kts` (release block)
3. Build:

```powershell
.\gradlew.bat assembleRelease
```

### Give users without code

1. Send them **`app-debug.apk`** or signed **`app-release.apk`**
2. On the phone: **Settings → Security → Install unknown apps** (allow Files/Chrome)
3. Open the APK file → Install
4. During exam: open app → **Scan Desktop QR** (or tap the QR link)

---

## 5. Full setup for an exam day

### Server machine (instructor IT)

1. Start **Backend** (`python -m app.main`)
2. Serve **Admin Web** (`npx serve admin-web/dist`)
3. Create exam + questions + proctoring profile in Admin
4. Publish exam

### Student PCs

1. Install **Desktop** (`IntelliQuizDesktop.exe`)
2. Set `IQ_DESKTOP_API_BASE_URL` to server address
3. Run Desktop → login → enroll face (first time) → pick exam

### Student phones

1. Install **APK**
2. Same Wi‑Fi as exam PC
3. Scan QR during camera setup step

---

## 6. Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@intelliquiz.dev | Admin123! |
| Student | student@intelliquiz.dev | Student123! |
| Instructor | instructor@intelliquiz.dev | Teach123! |

---

## 7. Troubleshooting

| Problem | Fix |
|---------|-----|
| Desktop can't connect | Check `IQ_DESKTOP_API_BASE_URL` and firewall on port 8080 |
| Phone camera won't open | PC and phone must share same router; use HTTPS phone URL from QR |
| Face enroll fails | Good lighting, one face centered, webcam allowed |
| Other apps during exam | Medium+ proctoring kills browsers/helpers; exam runs in kiosk window |
| APK won't install | Enable "Install unknown apps" for your file manager |

---

## 8. What gets installed where

| Data | Location |
|------|----------|
| Desktop encrypted logs | `%USERPROFILE%\.intelliquiz\desktop\` |
| Face identity template | `%USERPROFILE%\.intelliquiz\desktop\identity\` |
| Backend database | `backend/intelliquiz.dev.db` |
| Admin | Browser localStorage (login token) |
