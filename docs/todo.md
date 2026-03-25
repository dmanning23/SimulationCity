# SimulationCity — TODO

## Current Status

**Phase 1 (Foundation) — COMPLETE**
**Phase 2 (Simulation Engine) — COMPLETE**
**Phase 3a (Change Streams) — COMPLETE**
**Phase 3b (Viewport Subscriptions) — COMPLETE**
**Phase 4 (Frontend Game Canvas) — COMPLETE**

---

## Phase 5 — React UI (Week 9) ← YOU ARE HERE

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
- [ ] Socket.IO Redis adapter for horizontal web dyno scaling (viewport_store is currently in-process only)
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
