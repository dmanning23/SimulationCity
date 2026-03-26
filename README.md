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
