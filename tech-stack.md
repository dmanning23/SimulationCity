# SimulationCity - Tech Stack Reference

Quick reference for all technologies, libraries, and services used in this project. Consult `design-document.md` for architecture decisions and `premium-features.md` for the SD generation pipeline.

---

## Backend

| Layer | Technology | Version | Notes |
|---|---|---|---|
| HTTP framework | FastAPI | ≥0.111 | REST endpoints + ASGI app host |
| WebSocket | python-socketio | ≥5.11 | AsyncServer, ASGI mode |
| ASGI server | uvicorn | ≥0.29 | With `uvicorn[standard]` for production |
| Auth | python-jose + passlib | latest | JWT tokens, bcrypt password hashing |
| Task queue | Celery | ≥5.4 | `celery[redis]` — broker + result backend |
| Async DB driver | Motor | ≥3.4 | Async MongoDB driver (used by Beanie) |
| ODM (async) | Beanie | ≥1.26 | Pydantic v2-based ODM for FastAPI layer |
| DB driver (sync) | pymongo | ≥4.7 | Used directly in Celery tasks |
| Cache / broker | redis-py | ≥5.0 | `redis[hiredis]` for performance |
| Data validation | Pydantic | v2 | Used by FastAPI and Beanie |
| SD generation | replicate | ≥0.29 | Replicate API client for SD inference |
| File storage | boto3 | ≥1.34 | AWS S3 for generated asset storage |
| Scheduling | Celery Beat | (built-in) | Periodic simulation tick scheduling |
| Testing | pytest + pytest-asyncio | latest | Unit + integration tests |
| Load testing | Locust | ≥2.28 | Socket.IO load simulation |

### Python Version
- **3.12+** required

### Key `requirements.txt` groups
```
# API server
fastapi[standard]
python-socketio
uvicorn[standard]
python-jose[cryptography]
passlib[bcrypt]

# Database
beanie
motor
pymongo

# Task queue
celery[redis]
redis[hiredis]

# SD generation (premium)
replicate
boto3

# Testing
pytest
pytest-asyncio
httpx          # ASGI test client for FastAPI
locust
```

---

## Frontend

| Concern | Technology | Version | Notes |
|---|---|---|---|
| Game canvas | Phaser | 3.x | WebGL/Canvas tile rendering, camera, sprites |
| UI framework | React | 18.x | UI overlay, menus, panels, HUD |
| Language | TypeScript | 5.x | Strict mode throughout |
| Build tool | Vite | 5.x | Dev server + production bundler |
| Shared state | Zustand | 4.x | Bridge between Phaser and React |
| Real-time | socket.io-client | 4.x | Must match python-socketio major version |
| Styling | Tailwind CSS | 3.x | UI layer only, not applied to Phaser canvas |
| HTTP client | axios | 1.x | REST API calls (auth, premium endpoints) |

### Key `package.json` dependencies
```json
{
  "dependencies": {
    "phaser": "^3.80.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "socket.io-client": "^4.7.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "tailwindcss": "^3.4.0"
  }
}
```

---

## Infrastructure and Services

| Service | Provider | Purpose |
|---|---|---|
| App hosting | Heroku | Web dynos (API + socketio), Worker dynos (Celery) |
| Database | MongoDB Atlas | M10+ tier (change streams require replica set) |
| Cache / broker | Heroku Redis | Celery broker, result backend, Socket.IO adapter |
| File storage | AWS S3 | Generated building asset images |
| SD inference | Replicate | Stable Diffusion API calls (premium feature) |
| CI/CD | GitHub Actions | Test → deploy to Heroku staging pipeline |
| Monitoring | Sentry | Error tracking (backend + frontend) |

---

## Repository Structure

```
simulationcity/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + socketio ASGI mount
│   │   ├── socket_handlers.py   # python-socketio event handlers
│   │   ├── routers/             # FastAPI route modules (auth, cities, premium)
│   │   ├── models/              # Beanie document models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   └── services/            # Business logic (city, player, asset services)
│   ├── workers/
│   │   ├── celery_app.py        # Celery app config and queue definitions
│   │   ├── simulation.py        # simulate_city_tick task
│   │   ├── build_actions.py     # player action processing tasks
│   │   └── sd_generation.py     # Stable Diffusion generation tasks (premium)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── game/                # Phaser scenes, tile logic, camera
│   │   ├── components/          # React UI components
│   │   ├── stores/              # Zustand stores
│   │   ├── socket.ts            # Socket.IO client singleton + event wiring
│   │   └── api.ts               # axios REST client
│   ├── public/
│   │   └── assets/              # Tilesets, default building sprites
│   └── package.json
└── docs/
    ├── design-document.md
    ├── development-roadmap.md
    ├── tech-stack.md            # (this file)
    └── premium-features.md
```

---

## Environment Variables

### Backend (`.env`)
```
# App
SECRET_KEY=<jwt signing key>
ENVIRONMENT=development|staging|production

# MongoDB
MONGODB_URL=mongodb+srv://<user>:<pass>@cluster.mongodb.net/simulationcity

# Redis
REDIS_URL=redis://localhost:6379/0

# AWS S3 (premium)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=simulationcity-assets
AWS_REGION=us-east-1

# Replicate (premium)
REPLICATE_API_TOKEN=

# Feature flags
ENABLE_SD_GENERATION=false
```

### Frontend (`.env`)
```
VITE_API_URL=http://localhost:8000
VITE_SOCKET_URL=http://localhost:8000
```
