# Deploy IntelliQuiz on Railway (Admin Web + Backend API)

This deploys **one Railway service** that serves:

- Admin UI → `https://YOUR-APP.up.railway.app/`
- API → `https://YOUR-APP.up.railway.app/api/v1`

Desktop EXE and Android APK stay on student devices. They talk to this Railway API
for login / exams / sync. Phone↔PC pairing stays **local Wi‑Fi** (not via Railway).

---

## 1) Deploy on Railway

1. Push this repo to GitHub (already done if you use `Secure-Quiz-`).
2. Open [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**.
3. Select this repository.
4. Railway will use the root `Dockerfile` + `railway.toml`.
5. Add variables (Project → Variables):

| Variable | Example | Notes |
|----------|---------|--------|
| `IQ_JWT_SECRET` | long random string | **Required** in production |
| `IQ_DEBUG` | `false` | |
| `IQ_CORS_ORIGINS` | `*` | Or your exact admin URL |
| `IQ_ADMIN_STATIC_DIR` | `/app/admin_dist` | Set by Dockerfile |
| `IQ_DATABASE_URL` | (see below) | Strongly recommended |

### Database (pick one)

**Option A — Railway Postgres (recommended)**  
1. Add plugin **PostgreSQL**  
2. Set:

```text
IQ_DATABASE_URL=${{Postgres.DATABASE_URL}}
```

(If Railway gives `postgres://`, change scheme to `postgresql+psycopg://`.)

**Option B — SQLite (simple, not durable across redeploys)**  
Leave default SQLite. Add a **Volume** mounted at `/data` and set:

```text
IQ_DATABASE_URL=sqlite:////data/intelliquiz.db
```

6. Deploy → wait until health check `/api/v1/health` is green.
7. Open the public URL → login:

- Admin: `admin@intelliquiz.dev` / `Admin123!`
- Student: `student@intelliquiz.dev` / `Student123!`

**Change these passwords after first login (seed accounts).**

---

## 2) Point Desktop at Railway

Next to `IntelliQuizDesktop.exe` create `.env`:

```env
IQ_DESKTOP_API_BASE_URL=https://YOUR-APP.up.railway.app/api/v1
IQ_DESKTOP_API_VERIFY_SSL=true
```

Rebuild/redistribute the desktop zip after changing this, or ship the `.env` with the folder.

Then run **`Launch IntelliQuiz.bat`**.

Offline behavior: if Railway is down / blocked, the exam still runs locally
(encrypted SQLite). Events sync when the API is reachable again.

---

## 3) Android

Install the APK on the phone. Android pairs to the **Desktop on the same Wi‑Fi**
via QR (not directly to Railway). Evidence reaches Admin after Desktop syncs.

---

## 4) What students vs admin do

| Who | Where | Needs internet? |
|-----|--------|-----------------|
| Admin / instructor | Railway URL in browser | Yes |
| Student Desktop | Local EXE | Needed for login + final sync; exam continues offline |
| Student Phone | APK | Same Wi‑Fi as PC for camera pair |

---

## 5) Proctoring behavior (current)

During exam the Desktop:

- Closes helper apps (Discord, TeamViewer, Cursor, ChatGPT apps, etc.)
- Detects other Chrome/Edge windows (exam Edge profile stays protected)
- Captures **webcam photo + screen snapshot** and syncs to Admin as cheating evidence
- Keeps running even if Admin/Railway is temporarily unreachable

---

## 6) Checklist

- [ ] Railway service healthy at `/api/v1/health`
- [ ] Admin UI loads at `/`
- [ ] `IQ_JWT_SECRET` set
- [ ] Postgres or volume configured
- [ ] Desktop `.env` points to `https://…/api/v1`
- [ ] Test student login from Desktop
- [ ] Test admin Attempts & flags after a short exam
