# SimulationCity

A cooperative city-building web game inspired by SimCity 2000. Multiple players share a city in real time — zone land, build infrastructure, and watch your population grow.

## Prerequisites

- Python 3.12+ with [uv](https://github.com/astral-sh/uv)
- Node.js 20+
- Docker (for Redis)
- MongoDB Atlas account (replica set required for change streams)

## First-time setup

**1. Clone and install dependencies**

```bash
# Backend
cd backend
uv sync

# Frontend
cd frontend
npm install
```

**2. Configure the backend**

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set:
- `MONGODB_URL` — your Atlas connection string (`mongodb+srv://...`)
- `SECRET_KEY` — any long random string

## Running locally

You need 3 terminals.

**Terminal 1 — Redis**

```bash
docker-compose up redis
```

**Terminal 2 — Backend**

```bash
cd backend
uvicorn app.main:socket_app --reload
```

Runs on `http://localhost:8000`.

**Terminal 3 — Frontend**

```bash
cd frontend
npm run dev
```

Runs on `http://localhost:5173`. The Vite dev server proxies `/api` and `/socket.io` to the backend automatically.

## Opening a city

Navigate to `http://localhost:5173?city=<city_id>`.

You'll need a valid city ID. Create one via the API:

```bash
# Register a player
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "dan", "email": "dan@example.com", "password": "secret"}'

# Log in and grab the token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "dan", "password": "secret"}'

# Create a city
curl -X POST http://localhost:8000/api/cities \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "My City"}'
```

Copy the `id` from the response and use it in the URL.

## What you should see

Once connected to a city:

- **Top-left** — StatsBar showing treasury (§), population, and happiness
- **Bottom-center** — Toolbar with tool palette and view mode switcher (Base / Electricity / Pollution / Water)
- **Top-right** — PlayerList showing other active players (hidden when you're alone)

## Running Celery workers (optional for local dev)

Required for simulation ticks and build actions to process:

```bash
cd backend
uv run celery -A workers.celery_app worker -Q simulation,high_priority -l info
```

## Running tests

**Backend**

```bash
# Requires the mongodb-test docker container
docker-compose up -d mongodb-test

cd backend
uv run pytest
```

**Frontend**

```bash
cd frontend
npm test
```

## Deployment

### Architecture

| Service | Platform | Notes |
|---|---|---|
| Frontend | Vercel | Static SPA, auto-deployed from `main` |
| Backend (FastAPI + Socket.IO) | Railway | Persistent process, WebSocket support |
| Celery worker + Beat | Heroku (worker dyno) | Background jobs + simulation ticks |
| Redis | Heroku Redis add-on | Shared broker between backend and Celery |
| MongoDB | Atlas | Replica set required for change streams |

Both Railway (backend) and Heroku (Celery) use the same Redis and MongoDB URLs — they don't communicate directly.

### Deploy order

Stand things up in this order to avoid connection errors on startup:

1. MongoDB Atlas (already running)
2. Heroku Redis (already running)
3. Railway — backend
4. Heroku — Celery worker
5. Vercel — frontend

### Environment variables

**Railway (backend)**

| Variable | Value |
|---|---|
| `SECRET_KEY` | Long random string — generate with `openssl rand -hex 32` |
| `ENVIRONMENT` | `production` |
| `MONGODB_URL` | Atlas connection string |
| `MONGODB_DB_NAME` | `simulationcity` |
| `REDIS_URL` | Heroku Redis URL (from Heroku add-on config) |
| `PORT` | Set automatically by Railway |

**Heroku (Celery worker)**

| Variable | Value |
|---|---|
| `SECRET_KEY` | Same value as Railway |
| `ENVIRONMENT` | `production` |
| `MONGODB_URL` | Same Atlas connection string |
| `MONGODB_DB_NAME` | `simulationcity` |
| `REDIS_URL` | Set automatically by Heroku Redis add-on |

**Vercel (frontend)**

| Variable | Value |
|---|---|
| `VITE_API_URL` | Railway backend URL (e.g. `https://simulationcity.up.railway.app`) |

### Railway setup (backend)

1. Create a new Railway project and connect the GitHub repo
2. Set the **Root directory** to `backend`
3. Set the **Start command**:
   ```
   uvicorn app.main:socket_app --host 0.0.0.0 --port $PORT
   ```
4. Add all environment variables from the table above
5. Deploy — Railway auto-detects Python via `pyproject.toml`

Railway will assign a public URL with WebSocket support enabled by default.

### Heroku setup (Celery worker)

Create a `Procfile` in the repo root (or `backend/Procfile`) with:

```
worker: cd backend && uv run celery -A workers.celery_app worker -Q simulation,high_priority -l info --beat
```

Then:

1. Connect the GitHub repo to Heroku
2. Add all environment variables from the table above
3. Ensure the Heroku Redis add-on is attached — `REDIS_URL` will be set automatically
4. In the Heroku dashboard, turn **off** the `web` dyno and turn **on** the `worker` dyno
5. Deploy from `main`

> The `--beat` flag runs the scheduler in the same process as the worker. This is fine for a single-worker deployment — if you scale workers later, run Beat as a separate dyno.

### Vercel setup (frontend)

1. Import the GitHub repo in Vercel
2. Set **Root directory** to `frontend`
3. Build command: `npm run build`
4. Output directory: `dist`
5. Add the `VITE_API_URL` environment variable pointing to your Railway backend URL
6. Deploy

> The frontend currently hardcodes `localhost` for the Socket.IO connection during local dev (via Vite proxy). Before deploying, update `frontend/src/socket.ts` to read the backend URL from `import.meta.env.VITE_API_URL` in production.

### CORS

Update `backend/app/main.py` to add your Vercel domain to `allow_origins` before deploying:

```python
allow_origins=[
    "http://localhost:3000",
    "http://localhost:5173",
    "https://your-app.vercel.app",  # add this
],
```

---

## Tech stack

See [tech-stack.md](tech-stack.md) for full dependency list.

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, python-socketio |
| Task queue | Celery + Redis |
| Database | MongoDB Atlas + Beanie ODM |
| Frontend | Phaser 3, React 18, TypeScript, Zustand, Vite |
| Tests | pytest (backend), Vitest + @testing-library/react (frontend) |

## Project docs

- [game-design.md](game-design.md) — roles, simulation systems, economy, MVP scope
- [design-document.md](design-document.md) — technical architecture
- [development-roadmap.md](development-roadmap.md) — phased build plan
- [tech-stack.md](tech-stack.md) — all deps and versions
