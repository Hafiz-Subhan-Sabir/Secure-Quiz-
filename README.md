# IntelliQuiz – AI Driven Exam Security System

Distributed architecture: **Central Web Admin** + **Student Desktop App** + **Android secondary camera**, backed by a versioned API and shared contracts.

## Repository map

```text
IntelliQuiz/
├── contracts/          # OpenAPI + event/QR schemas (source of truth)
├── backend/            # FastAPI modular monolith
├── admin-web/          # React admin console (Vite)
├── desktop/            # Student exam client (Python)
├── android/            # Secondary camera app (Kotlin)
├── ml/                 # FaceGest model training (done)
├── docs/architecture.md
└── scripts/
```

## Quick start

### 1) Backend API

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload --port 8080
```

Seeded users:

| Email | Password | Role |
|-------|----------|------|
| admin@intelliquiz.dev | Admin123! | admin |
| instructor@intelliquiz.dev | Teach123! | instructor |
| student@intelliquiz.dev | Student123! | student |

Health: `GET http://127.0.0.1:8080/api/v1/health`

### 2) Admin Web

```bash
cd admin-web
npm install
npm run dev
```

Open http://localhost:5173 — login as admin.

### 3) Desktop smoke (offline log → sync)

```bash
cd desktop
pip install -e .
python -m intelliQuiz_desktop.cli smoke
```

### 4) Android

Open `android/` in Android Studio and sync Gradle.

### 5) ML (already trained)

See `ml/README.md`. Best model: `ml/artifacts/models/best_model.joblib`.

## Design principle

Admin configures/reviews · Desktop owns exam + AI + encrypted offline truth · Android is a paired sensor · Server syncs and reports.

Read `docs/architecture.md` for the full flow.
