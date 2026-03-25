# SimulationCity - Development Roadmap

## Tech Stack Summary
- **Backend**: Python, FastAPI, python-socketio, uvicorn
- **Task Queue**: Celery + Redis
- **Database**: MongoDB Atlas, Beanie ODM (async), pymongo (Celery workers)
- **Frontend**: Phaser 3, React 18, TypeScript, Zustand, Vite
- **Premium/AI**: Stable Diffusion via Replicate API
- **Deployment**: Heroku (web + worker dynos), MongoDB Atlas, AWS S3

---

## Phase 1: Foundation (Weeks 1–2)

### Week 1: Project Setup and Basic Communication
- [x] Initialize monorepo structure (`/backend`, `/frontend`, `/workers`)
- [ ] Set up Heroku project and environments (development/staging/production)
- [x] Stand up FastAPI app with python-socketio ASGI integration (uvicorn)
- [x] Connect to MongoDB Atlas; initialize Beanie with document models
- [x] Implement basic Socket.IO connection/disconnection handling
- [x] Set up basic JWT authentication (FastAPI + python-jose)

### Week 2: Core Game State Management
- [x] Implement city creation and basic CRUD REST endpoints (FastAPI)
- [x] Set up Socket.IO rooms keyed by `city:{city_id}`
- [x] Create chunk data structure and initial map generation logic
- [x] Implement city join/leave logic with viewport state tracking
- [x] Test multi-player connections to the same city room

---

## Phase 2: Simulation Engine (Weeks 3–4)

### Week 3: Celery Integration
- [x] Set up Redis on Heroku (as Celery broker + result backend)
- [x] Configure Celery app with `simulation` and `high_priority` queues
- [x] Create Celery worker dyno setup and local dev worker process
- [x] Implement job enqueueing from Socket.IO server (player build actions → high_priority queue)
- [x] Test basic job processing flow end-to-end

### Week 4: Core Simulation Logic
- [x] Implement `simulate_city_tick` Celery task (chunk-based processing)
- [x] Build simulation rules: zoning, population growth, resource consumption
- [x] Write simulation results back to MongoDB via pymongo
- [x] Implement periodic tick scheduling (Celery Beat)
- [ ] Test simulation with multiple concurrent cities

---

## Phase 3: Real-Time Updates (Weeks 5–6)

### Week 5: MongoDB Change Streams
- [x] Implement change stream listeners on the Socket.IO server (Motor async)
- [x] Filter change events by `cityId` and active player viewports
- [x] Broadcast chunk and stats updates to relevant Socket.IO city rooms
- [ ] Test real-time updates with multiple simultaneous connections
- [ ] Optimize payload size — only send diff, not full chunk

### Week 6: Viewport-Based Data Delivery
- [x] Implement viewport tracking: client sends current chunk coordinates on camera move
- [x] Server-side chunk subscription management per Socket.IO session
- [x] Lazy load chunks entering viewport; evict subscriptions for chunks leaving viewport
- [ ] Implement view mode switching (base, electricity, pollution, water) — deferred to Phase 4 frontend
- [ ] Test with varying viewport sizes and fast camera movement

---

## Phase 4: Frontend — Game Canvas (Weeks 7–8)

### Week 7: Phaser 3 Setup and Tile Rendering
- [ ] Initialize Vite + React + TypeScript project
- [ ] Integrate Phaser 3 as a React component (canvas mounted inside React tree)
- [ ] Set up Zustand stores: `CityStore`, `ViewportStore`, `PlayerStore`
- [ ] Implement isometric tile map renderer in Phaser
- [ ] Load and render chunk data from Zustand into Phaser tilemap
- [ ] Implement chunk loading/unloading on camera scroll

### Week 8: Interaction and Socket.IO Client
- [ ] Implement Phaser camera controls (scroll, zoom)
- [ ] Handle tile click/hover events — fire Zustand actions
- [ ] Connect Socket.IO client; wire `chunk_update` and `stats_update` events to Zustand
- [ ] Implement building placement flow (select tool → click tile → emit action to server)
- [ ] Implement road and zone placement

---

## Phase 5: Frontend — React UI (Week 9)

### Week 9: HUD and Game UI
- [ ] Build HUD: treasury, population, happiness, simulation speed controls
- [ ] Build tool palette: zones (R/C/I), roads, utilities, demolish
- [ ] Build view mode switcher (base / electricity / pollution / water)
- [ ] Build player list panel with roles (admin, builder, viewer)
- [ ] Build city stats overlay and time controls
- [ ] Connect all UI actions to Socket.IO emit calls

---

## Phase 6: Scaling and Robustness (Week 10)

### Week 10: Connection Management and Performance
- [ ] Implement robust reconnection flow with viewport state restoration
- [ ] Set up Socket.IO Redis adapter for horizontal web dyno scaling
- [ ] Configure Celery worker auto-scaling based on queue depth
- [ ] Optimize MongoDB indexes: compound index on `(cityId, coordinates)` for chunks
- [ ] Implement resource cleanup for cities with no active players
- [ ] Load test with simulated concurrent players

---

## Phase 7: Integration and Polish (Weeks 11–12)

### Week 11: Full System Integration
- [ ] End-to-end test: connect frontend to all backend services
- [ ] Fix cross-component issues surfaced by integration
- [ ] Implement client-side LRU chunk cache
- [ ] Smooth viewport movement with predictive chunk pre-loading
- [ ] Authentication flow: login, register, JWT refresh

### Week 12: Monitoring, Error Handling, Admin
- [ ] Set up Heroku metrics + alerting (or Datadog/Sentry)
- [ ] Implement structured logging across FastAPI and Celery workers
- [ ] Error handling and recovery for failed simulation tasks
- [ ] Build basic admin endpoints (city management, player bans)
- [ ] Document all REST and Socket.IO API endpoints

---

## Phase 8: Premium Features — Stable Diffusion (Weeks 13–15)

*See `premium-features.md` for full design.*

### Week 13: SD Pipeline Infrastructure
- [ ] Set up Replicate API client in a dedicated `sd_generation` Celery queue
- [ ] Create `GeneratedAsset` MongoDB document model
- [ ] Set up AWS S3 bucket for generated asset storage
- [ ] Implement `generate_building_asset` Celery task (prompt → SD → S3 → DB)
- [ ] Test generation pipeline end-to-end with a hardcoded prompt

### Week 14: Style Palette System and API
- [ ] Define style palette catalog (Art Deco, Brutalist, Cyberpunk, etc.)
- [ ] Implement prompt construction: `base_prompt + style_modifier + building_type`
- [ ] Create REST endpoints: generate asset, list variants, select active variant
- [ ] Implement generation credit system (deduct on generation, enforce limits)
- [ ] Wire `design_style` city setting to all building generation prompts

### Week 15: Premium UI
- [ ] Build style palette picker in React (city settings panel)
- [ ] Build building generation modal (generate, preview variants, select)
- [ ] Build generated asset gallery for previously created buildings
- [ ] Implement premium gate — check `is_premium` before showing SD features
- [ ] Add credit balance display to HUD for premium users

---

## Future Enhancements (Post-Launch)

### Short-Term
- [ ] Enhanced player permissions and granular role controls
- [ ] In-game notifications and event log
- [ ] Disaster events (fire, earthquake, flood) with emergency management
- [ ] Time-based simulation scheduling (day/night cycle effects)

### Mid-Term
- [ ] City templates and blueprint sharing between players
- [ ] Global leaderboards and achievements
- [ ] Advanced resource trading between cities on the same server
- [ ] Additional SD style palettes and seasonal building variants

### Long-Term
- [ ] Regional connections between multiple cities (inter-city transit, trade routes)
- [ ] Seasonal and weather effects on simulation
- [ ] AI assistant mayors for cities with inactive owners
- [ ] Custom building design tooling with SD inpainting/img2img

---

## Development Notes

### Key Technical Challenges

1. **Real-Time Consistency** — All players in a city room must see a consistent simulation state. Optimistic concurrency control (chunk `version` field) prevents stale overwrites.
2. **Simulation Performance** — Celery workers process chunks independently; ensure chunk boundaries don't cause simulation artifacts.
3. **Viewport Subscription Management** — Per-session subscription state must be cleaned up reliably on disconnect to avoid ghost change stream listeners.
4. **SD Visual Consistency** — Generated building sprites must match the game's isometric perspective and scale. Use ControlNet depth conditioning and enforce consistent output dimensions.

### Testing Strategy
- Unit tests for simulation rules (pytest)
- Integration tests for FastAPI endpoints and Celery tasks (pytest + testcontainers for Mongo/Redis)
- Phaser scene tests via Playwright (render a test scene, assert tile state)
- Load testing with Locust (simulated Socket.IO connections)
- Chaos testing: drop connections mid-simulation, kill worker dynos

### Deployment Strategy
- CI/CD via GitHub Actions → Heroku staging on PR merge
- Promotion from staging → production via Heroku pipeline
- Feature flags (e.g., `ENABLE_SD_GENERATION`) for gradual rollout
- Celery Beat for scheduled simulation ticks in production
