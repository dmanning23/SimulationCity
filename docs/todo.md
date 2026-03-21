# SimulationCity — TODO

## Current Status

**Phase 1 (Foundation) — COMPLETE**

Project scaffold is in place: structure, config, models, auth/city endpoints, Socket.IO handler skeleton, Celery app stub, Zustand stores, socket/api clients. No game logic implemented yet.

---

## Phase 2 — Simulation Engine (Weeks 3–4) ← YOU ARE HERE

### Week 3: Celery Integration
- [ ] Add Redis service to `docker-compose.yml` (referenced in config but missing from compose)
- [ ] Create `backend/workers/simulation.py` — `simulate_city_tick` task stub
- [ ] Create `backend/workers/build_actions.py` — `process_build_action` task stub
- [ ] Enable `celery_app.autodiscover_tasks(...)` in `backend/workers/celery_app.py`
- [ ] Wire Socket.IO `build_action` event in `socket_handlers.py` → enqueue to `high_priority` queue
- [ ] Test end-to-end: client → Socket.IO → Celery task → result

### Week 4: Core Simulation Logic
- [ ] Implement `simulate_city_tick`: iterate city chunks, apply simulation rules
- [ ] Simulation rules: zoning growth, population calculation, resource consumption (power/water)
- [ ] Write tick results back to MongoDB via pymongo (not Beanie — workers use pymongo directly)
- [ ] Set up Celery Beat periodic schedule for city ticks
- [ ] Unit tests for simulation rules; integration test for full tick

---

## Phase 3 — Real-Time Updates (Weeks 5–6)

### Week 5: MongoDB Change Streams
- [ ] Implement change stream listener on Socket.IO server (Motor async driver)
- [ ] Filter change events by `cityId` + active player viewport subscriptions
- [ ] Broadcast `chunk_update` / `stats_update` to Socket.IO city rooms
- [ ] Test real-time updates with multiple simultaneous connections
- [ ] Optimize payload — send diff only, not full chunk

### Week 6: Viewport-Based Data Delivery
- [ ] Client emits `viewport_update` on camera move → server manages chunk subscriptions
- [ ] Lazy load chunks entering viewport; unsubscribe on exit
- [ ] Implement view modes: base, electricity, pollution, water
- [ ] Test with varying viewport sizes and fast camera movement

---

## Phase 4 — Frontend Game Canvas (Weeks 7–8)

### Week 7: Phaser 3 Setup and Tile Rendering
- [ ] `frontend/src/game/` is empty — create `GameScene.ts` (isometric tilemap renderer)
- [ ] Create `ChunkManager.ts` — load/unload chunks from Zustand into Phaser tilemap
- [ ] Implement chunk loading/unloading on camera scroll

### Week 8: Interaction and Socket.IO Client
- [ ] Camera controls: scroll, zoom
- [ ] Tile click/hover events → Zustand actions
- [ ] Wire `chunk_update` and `stats_update` Socket.IO events to Zustand
- [ ] Building placement flow: select tool → click tile → emit action to server
- [ ] Road and zone placement

---

## Phase 5 — React UI (Week 9)

- [ ] `frontend/src/components/` is empty — all HUD components needed
- [ ] HUD: treasury, population, happiness, simulation speed controls
- [ ] Tool palette: zones (R/C/I), roads, utilities, demolish
- [ ] View mode switcher (base / electricity / pollution / water)
- [ ] Player list panel (roles: admin, builder, viewer)
- [ ] City stats overlay and time controls
- [ ] Connect all UI actions to Socket.IO emit calls

---

## Phase 6 — Scaling and Robustness (Week 10)

- [ ] Robust reconnection flow with viewport state restoration
- [ ] Socket.IO Redis adapter for horizontal web dyno scaling
- [ ] Celery worker auto-scaling based on queue depth
- [ ] MongoDB compound index on `(cityId, coordinates)` for chunks
- [ ] Resource cleanup for cities with no active players
- [ ] Load test with simulated concurrent players

---

## Phase 7 — Integration and Polish (Weeks 11–12)

### Week 11: Full System Integration
- [ ] End-to-end test: connect frontend to all backend services
- [ ] Fix cross-component issues surfaced by integration
- [ ] Client-side LRU chunk cache
- [ ] Smooth viewport movement with predictive chunk pre-loading
- [ ] Authentication flow: login, register, JWT refresh

### Week 12: Monitoring, Error Handling, Admin
- [ ] Structured logging across FastAPI and Celery workers (Sentry or similar)
- [ ] Error handling and recovery for failed simulation tasks
- [ ] Admin endpoints: city management, player bans
- [ ] Document all REST and Socket.IO API endpoints

---

## Phase 8 — Premium Features / Stable Diffusion (Weeks 13–15)

*See `premium-features.md` for full design.*

### Week 13: SD Pipeline Infrastructure
- [ ] Set up Replicate API client in dedicated `sd_generation` Celery queue
- [ ] Create `GeneratedAsset` MongoDB document model
- [ ] Set up AWS S3 bucket for generated asset storage
- [ ] Implement `generate_building_asset` Celery task (prompt → SD → S3 → DB)
- [ ] Test generation pipeline end-to-end with a hardcoded prompt

### Week 14: Style Palette System and API
- [ ] Define style palette catalog (Art Deco, Brutalist, Cyberpunk, etc.)
- [ ] Implement prompt construction: `base_prompt + style_modifier + building_type`
- [ ] REST endpoints: generate asset, list variants, select active variant
- [ ] Generation credit system (deduct on generation, enforce limits)
- [ ] Wire `design_style` city setting to all building generation prompts

### Week 15: Premium UI
- [ ] Style palette picker in React (city settings panel)
- [ ] Building generation modal (generate, preview variants, select)
- [ ] Generated asset gallery for previously created buildings
- [ ] Premium gate — check `is_premium` before showing SD features
- [ ] Credit balance display in HUD for premium users
