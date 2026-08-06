# IntelliQuiz Contracts

Versioned API and event schemas shared by Admin, Desktop, Android, and Backend.

| Path | Purpose |
|------|---------|
| `openapi/intelliQuiz.v1.yaml` | REST API contract |
| `events/integrity.event.v1.json` | Offline/sync integrity event |
| `schemas/pairing.qr.v1.json` | Desktop↔Android QR handshake |
| `schemas/proctoring.profile.v1.json` | Exam proctoring strictness profile |

**Rule:** bump the version suffix (`v1` → `v2`) for breaking changes; never silently change existing schemas.
