# IntelliQuiz Admin Web

Central console in a fixed **92vw × 92vh** app shell.

```bash
cd admin-web
npm install
npm run dev
```

Open http://127.0.0.1:5173

Proxies `/api` → `http://127.0.0.1:8080` (change in `vite.config.ts` if your API port differs).

Demo: `admin@intelliquiz.dev` / `Admin123!`

## Screens
- Login — brand-first split composition
- Overview — system readiness + inventory
- Exams — create / list
- Proctoring — strictness presets + blacklist policy
- Reports — cheating probability + timeline
