# IntelliQuiz Architecture

Distributed exam security system with three independent clients and a shared backend.

## Components

| Component | Path | Role |
|-----------|------|------|
| Contracts | `contracts/` | Versioned APIs & event schemas (source of truth) |
| Backend | `backend/` | Auth, exams, sessions, sync ingest, reports |
| Admin Web | `admin-web/` | Central configuration & integrity review |
| Desktop | `desktop/` | Exam panel, AI proctoring, offline store, app lock |
| Android | `android/` | Secondary camera paired to Desktop via QR |
| ML | `ml/` | Offline model training / artifact export |

## Design rules

1. **Admin configures and reviews** — never runs on-device AI.
2. **Desktop owns the exam session** — answers, AI, encrypted SQLite, sync.
3. **Android is a peripheral sensor** — paired to one Desktop session only.
4. **Server is multi-tenant truth** — idempotent sync, reports, auth.
5. **Contracts before code** — change OpenAPI/events first, then clients.

## Runtime flow

```text
Admin  --HTTPS-->  API Gateway / FastAPI
                      |     ^
Desktop --sync/TLS----+     |
   ^                        |
   | local pair (QR/WS)     |
Android ---------------------+ (optional telemetry only)
```

## Scalability path

Start as a **modular monolith** (`backend/app/modules/*`). Split modules into services when load requires:

- `sessions` + `sync` scale horizontally first
- `reports` can move to read replicas / analytics warehouse
- object storage for clips; DB keeps metadata only

## Security baseline

- TLS in transit; AES-encrypted SQLite on Desktop
- Short-lived JWTs; per-session pairing secrets
- Idempotent event ingest: `(session_id, event_id)` unique
- Prefer risk events + short evidence over continuous cloud video
