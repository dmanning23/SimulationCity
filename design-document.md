# SimulationCity - System Architecture Design Document

## System Overview

SimulationCity is a cooperative city-building web game where players build and manage cities together in real-time, inspired by SimCity 2000. The architecture is designed for real-time collaboration, scalable simulation processing, and extensible premium features including AI-generated building assets.

All backend services are implemented in Python. The frontend is a web app combining Phaser 3 (game canvas) and React (UI overlay).

---

## Backend Architecture

### 1. Communication Layer (FastAPI + python-socketio)

**Purpose**: Handles real-time bidirectional communication between clients and server.

**Key Features**:
- WebSocket-based communication via Socket.IO with HTTP long-poll fallback
- Room-based player grouping by city
- Connection/disconnection lifecycle management
- Viewport-based data streaming

**Technical Implementation**:
- `FastAPI` for the HTTP API (auth, REST endpoints)
- `python-socketio` (AsyncServer) mounted as ASGI app alongside FastAPI
- `uvicorn` as the ASGI server
- `python-socketio` Redis adapter for multi-instance socket communication
- Sticky sessions (session affinity) at the load balancer for connection stability

**Scaling Strategy**:
- Horizontal scaling through multiple Heroku web dynos
- Auto-scaling based on active connection count
- Redis adapter ensures socket events fan out correctly across instances

**Example — player join handler**:
```python
import socketio
from beanie import PydanticObjectId

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.event
async def join_city(sid, data):
    city_id = data['city_id']
    user_id = data['user_id']

    await sio.enter_room(sid, f'city:{city_id}')
    await sio.save_session(sid, {'city_id': city_id, 'user_id': user_id})

    initial_state = await load_initial_viewport(city_id, data['viewport'])
    await sio.emit('initial_state', initial_state, to=sid)

@sio.event
async def disconnect(sid):
    session = await sio.get_session(sid)
    if session.get('city_id'):
        await handle_player_leave(session['city_id'], session['user_id'], sid)
```

---

### 2. Simulation Layer (Celery + Redis)

**Purpose**: Processes game logic, city simulation ticks, and player build actions asynchronously.

**Key Features**:
- Asynchronous task processing decoupled from the communication layer
- Independent scaling from the Socket.IO server
- Job prioritization (e.g., player-triggered actions > background ticks)
- Fault-tolerant with task retries and timeout handling

**Technical Implementation**:
- `Celery` with Redis as the message broker and result backend
- Separate Heroku worker dynos running Celery workers
- Two queues: `high_priority` (player actions) and `simulation` (background ticks)
- Simulation results written directly to MongoDB; change streams notify clients

**Scaling Strategy**:
- Worker dyno count scaled independently based on Celery queue depth
- Priority queues prevent background simulation from starving player actions

**Example — simulation tick task**:
```python
from celery import Celery
from pymongo import MongoClient
from datetime import datetime, timezone
from bson import ObjectId

celery_app = Celery('simulation', broker='redis://localhost:6379/0')

@celery_app.task(queue='simulation', time_limit=30)
def simulate_city_tick(city_id: str):
    db = MongoClient()['simulationcity']
    chunks = list(db.chunks.find({'cityId': ObjectId(city_id)}))

    for chunk in chunks:
        updated = apply_simulation_rules(chunk)
        db.chunks.update_one(
            {'_id': chunk['_id']},
            {'$set': {
                'base': updated['base'],
                'layers': updated['layers'],
                'version': chunk['version'] + 1,
                'lastUpdated': datetime.now(timezone.utc)
            }}
        )

    return {'status': 'success', 'processed_chunks': len(chunks)}
```

---

### 3. Data Persistence Layer (MongoDB + Beanie ODM)

**Purpose**: Stores all game state, player data, city information, and generated asset references.

**Key Components**:
- `cities` collection — city metadata, settings, global stats
- `chunks` collection — 16x16 tile grid sections making up the city map
- `players` collection — user accounts, roles, premium status
- `events` collection — time-based simulation events (TTL indexed)
- `generated_assets` collection — SD-generated building image references (premium)

**Technical Implementation**:
- `Beanie` async ODM (built on `Motor` + `Pydantic v2`) for the FastAPI/async layer
- Synchronous `pymongo` in Celery workers (Celery is not async-native)
- MongoDB change streams on `chunks` and `cities` collections to drive real-time Socket.IO broadcasts
- Optimistic concurrency control via `version` field on chunk documents
- TTL indexes on `events` collection for automatic expiry

**Scaling Strategy**:
- Sharding on `(cityId, coordinates)` for the chunks collection
- Time-based sharding for event data
- Hashed sharding on `_id` for player data

**Data Models (Beanie)**:
```python
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class CollaboratorRole(str, Enum):
    ADMIN = "admin"
    BUILDER = "builder"
    VIEWER = "viewer"

class Collaborator(BaseModel):
    user_id: PydanticObjectId
    role: CollaboratorRole

class CitySettings(BaseModel):
    simulation_speed: str = "normal"
    starting_funds: int = 10000
    difficulty: str = "medium"
    design_style: Optional[str] = None  # Premium: SD style palette

class GlobalStats(BaseModel):
    population: int = 0
    happiness: int = 50
    treasury: int = 10000

class City(Document):
    name: str
    owner_id: PydanticObjectId
    collaborators: list[Collaborator] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    size: dict = Field(default={'width': 64, 'height': 64})  # in chunks
    settings: CitySettings = Field(default_factory=CitySettings)
    global_stats: GlobalStats = Field(default_factory=GlobalStats)

    class Settings:
        name = "cities"

class Building(BaseModel):
    id: str
    type: str           # residential, commercial, industrial, etc.
    subtype: str
    position: dict      # {x, y} within chunk
    size: dict          # {width, height} in tiles
    level: int = 1
    health: int = 100
    asset_id: Optional[str] = None  # Premium: ref to generated_assets

class ChunkBase(BaseModel):
    terrain: list       # 16x16 terrain data
    buildings: list[Building] = []
    roads: list = []

class ChunkLayers(BaseModel):
    electricity: dict = Field(default_factory=dict)
    pollution: dict = Field(default_factory=dict)
    water: dict = Field(default_factory=dict)

class Chunk(Document):
    city_id: PydanticObjectId
    coordinates: dict           # {x, y} chunk position in city grid
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    version: int = 0            # Optimistic concurrency control
    base: ChunkBase = Field(default_factory=ChunkBase)
    layers: ChunkLayers = Field(default_factory=ChunkLayers)

    class Settings:
        name = "chunks"

class Player(Document):
    username: str
    email: str
    hashed_password: str
    is_premium: bool = False
    premium_expires_at: Optional[datetime] = None
    generation_credits: int = 0     # Premium: SD generation credits
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "players"
```

---

### 4. Frontend Data Delivery

**Purpose**: Efficiently streams game state to clients based on their active viewport and view mode.

**Key Features**:
- Chunk-based data delivery — only send what is visible
- View-layer subscriptions (base, electricity, pollution, water)
- Progressive chunk loading as viewport moves
- LRU cache on client for recently visited chunks

**Technical Implementation**:
- Client tracks its current viewport (chunk coordinates) and notifies server on move
- Server maintains per-connection viewport state in Socket.IO session
- MongoDB change streams filtered to chunks within each client's active viewport
- Separate Socket.IO event channels per view layer to avoid unnecessary data transfer

---

## Frontend Architecture

### Overview

The frontend is a single-page web application combining two rendering concerns:

- **Phaser 3** — WebGL/Canvas game renderer for the city map, tile engine, viewport camera, and sprite rendering
- **React** — UI overlay for all non-game surfaces: HUD, menus, city stats panels, player management, premium features

These two systems share state through **Zustand** stores. Phaser emits events to Zustand; React reads from Zustand. Neither system calls the other directly.

### Tech Stack

| Concern | Technology |
|---|---|
| Game canvas | Phaser 3 |
| UI overlay | React 18 + TypeScript |
| Shared state | Zustand |
| Real-time | Socket.IO client |
| Build tooling | Vite |
| Styling | Tailwind CSS (UI only) |

### Architecture

```
┌────────────────────────────────────────────────────┐
│                   Browser Window                    │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │           React UI Layer (DOM)               │  │
│  │   HUD / Menus / Panels / Premium Features    │  │
│  │                                              │  │
│  │   ┌────────────────────────────────────┐    │  │
│  │   │     Phaser 3 Canvas (WebGL)        │    │  │
│  │   │   Tile map / Camera / Sprites      │    │  │
│  │   └────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│         Zustand Stores (shared state bridge)        │
│         Socket.IO Client (real-time events)         │
└────────────────────────────────────────────────────┘
```

### Phaser 3 Responsibilities

- Tile map rendering (isometric grid)
- Camera / viewport management (scroll, zoom)
- Chunk loading and unloading as camera moves
- Building sprite placement and animation
- Tile interaction (click/hover to select, place, demolish)
- Firing Zustand actions on player interactions

### React Responsibilities

- Main menu, lobby, city browser
- HUD: city stats, treasury, population, time controls
- Tool palette (zone, road, utility placement)
- Player list and permissions panel
- View mode switcher (base, electricity, pollution, water)
- Premium UI: style palette picker, building generation modal, asset gallery
- Notifications and alerts

### Zustand Stores

```typescript
// Key stores — see /frontend/src/stores/

interface CityStore {
  cityId: string | null
  globalStats: GlobalStats
  activeViewMode: 'base' | 'electricity' | 'pollution' | 'water'
  setViewMode: (mode: ViewMode) => void
}

interface ViewportStore {
  chunkX: number
  chunkY: number
  zoom: number
  loadedChunks: Map<string, Chunk>
  setViewport: (x: number, y: number) => void
}

interface PlayerStore {
  playerId: string | null
  isPremium: boolean
  generationCredits: number
  collaborators: Collaborator[]
}
```

### Socket.IO Client Integration

The Socket.IO client is initialized once and stored in a module singleton. Zustand actions are called directly from socket event handlers.

```typescript
// /frontend/src/socket.ts
import { io } from 'socket.io-client'
import { useViewportStore } from './stores/viewportStore'

export const socket = io(import.meta.env.VITE_API_URL)

socket.on('chunk_update', (data: ChunkUpdate) => {
  useViewportStore.getState().updateChunk(data.chunk)
})

socket.on('city_stats_update', (data: StatsUpdate) => {
  useCityStore.getState().updateStats(data.stats)
})
```

---

## System Data Flow

```
┌─────────────────────┐      WebSocket      ┌─────────────────────┐
│                     │◄────────────────────┤                     │
│  Frontend           │                     │  FastAPI +          │
│  Phaser 3 + React   │───────────────────► │  python-socketio    │
│                     │      Actions        │  (uvicorn/ASGI)     │
└─────────────────────┘                     └──────────┬──────────┘
                                                       │
                                                       │ Enqueues task
                                                       ▼
┌─────────────────────┐      Writes        ┌──────────────────────┐
│                     │◄────────────────────┤                      │
│  MongoDB Atlas      │                     │  Celery Workers      │
│  (Beanie / pymongo) │                     │  (simulation,        │
│                     │                     │   build actions,     │
└──────────┬──────────┘                     │   SD generation)     │
           │                                └──────────▲───────────┘
           │ Change                                    │
           │ Streams                                   │ Dequeues
           ▼                                           │
┌─────────────────────┐               ┌───────────────────────────┐
│                     │               │                           │
│  python-socketio    │               │  Redis                    │
│  (broadcasts to     │               │  (Celery broker +         │
│   city rooms)       │               │   Socket.IO adapter)      │
└─────────────────────┘               └───────────────────────────┘
```

---

## Deployment Architecture

### Heroku Components

| Dyno Type | Purpose | Scaling Trigger |
|---|---|---|
| Web dynos | FastAPI + python-socketio (uvicorn) | Active connections |
| Worker dynos | Celery simulation workers | Queue depth |
| Worker dynos | Celery SD generation workers | SD job queue depth |
| Redis add-on | Celery broker + Socket.IO adapter | Fixed (HA plan) |

### External Services

- **MongoDB Atlas** — M10+ tier required for change streams
- **Stable Diffusion** — Replicate API or self-hosted (premium feature only, see `premium-features.md`)
- **AWS S3** (or compatible) — Storage for SD-generated building assets

### Configuration

- Session affinity (sticky sessions) enabled for Socket.IO web dynos
- Redis configured for high availability (sentinel or cluster mode)
- MongoDB Atlas multi-region for read latency reduction
- Celery worker concurrency tuned per dyno size

---

## Conclusion

This architecture provides a cohesive, all-Python backend with a clear separation of concerns:

- **FastAPI + python-socketio** handles real-time communication and REST endpoints
- **Celery + Redis** decouples simulation processing from the communication layer
- **MongoDB + Beanie** provides flexible, change-stream-capable persistence
- **Phaser 3 + React** gives the frontend both performant game rendering and rich UI

The modular design supports future expansion including new simulation systems, additional view layers, inter-city connections, and the premium Stable Diffusion asset generation pipeline described in `premium-features.md`.
