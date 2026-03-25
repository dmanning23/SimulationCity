# Phase 4: Frontend Game Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-screen isometric Phaser 3 game canvas that renders city chunks as placeholder colored diamonds, wired to the backend via Socket.IO and Zustand.

**Architecture:** Phaser owns the full-screen canvas (`position: fixed; inset: 0`); React UI will float on top as a separate layer (Phase 5). Socket events update Zustand stores (source of truth); Phaser subscribes to Zustand and re-renders changed chunks. Chunks are 16×16 isometric tiles at 128×64px each.

**Tech Stack:** Phaser 3.80, React 18, TypeScript, Zustand 4, Socket.IO client 4.7, Vitest, Vite 5

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `frontend/vite.config.ts` | Add Vitest `test` block |
| Modify | `frontend/package.json` | Add `vitest` devDep + `test` script |
| Create | `frontend/src/game/coords.ts` | Pure isometric math: `tileToWorld`, `worldToTile`, `cameraBoundsToChunkBbox` |
| Create | `frontend/src/game/coords.test.ts` | Unit tests for coordinate functions |
| Modify | `frontend/src/stores/cityStore.ts` | Add `subscribeWithSelector` middleware (required for GameScene subscriptions) |
| Modify | `frontend/src/stores/viewportStore.ts` | Add `patchBase`, `patchLayers`, `removeChunk` actions; add `subscribeWithSelector` middleware |
| Create | `frontend/src/stores/viewportStore.test.ts` | Unit tests for new store actions |
| Modify | `frontend/src/socket.ts` | Fix stale event names + payload shapes; add `viewport_seed`, `layers_update` handlers; add `emitUpdateViewport` |
| Create | `frontend/src/socket.test.ts` | Unit tests for socket event handlers |
| Modify | `backend/app/change_stream.py` | Add `base.roads.*` prefix match to `_route_chunk_event` |
| Modify | `backend/tests/test_change_stream.py` | Add test for road-change routing |
| Create | `frontend/src/game/ChunkManager.ts` | `Phaser.GameObjects.Graphics` per chunk; isometric diamond rendering |
| Create | `frontend/src/game/GameScene.ts` | Main Phaser scene: camera drag/zoom, Zustand subscriptions, throttled viewport emit |
| Create | `frontend/src/game/PhaserGame.ts` | `Phaser.Game` factory + config |
| Create | `frontend/src/components/GameCanvas.tsx` | React component: mounts/destroys Phaser via `useEffect` |
| Modify | `frontend/src/App.tsx` | Replace placeholder with `<GameCanvas />` |

---

## Task 1: Vitest setup

No tests exist in the frontend yet. This task adds Vitest so subsequent tasks can follow TDD.

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Install Vitest**

```bash
cd frontend && npm install --save-dev vitest @vitest/ui jsdom
```

- [ ] **Step 2: Add test script to `package.json`**

Add `"test": "vitest run"` and `"test:watch": "vitest"` to the `"scripts"` block:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

- [ ] **Step 3: Add `test` block to `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": "http://localhost:8000",
      "/socket.io": {
        target: "http://localhost:8000",
        ws: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
  },
});
```

- [ ] **Step 4: Verify setup works**

Create a trivial smoke test to confirm Vitest runs:

```typescript
// frontend/src/smoke.test.ts  (delete after verifying)
it("vitest works", () => {
  expect(1 + 1).toBe(2);
});
```

Run: `cd frontend && npm test`
Expected: `1 passed`

Delete `frontend/src/smoke.test.ts`.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add package.json package-lock.json vite.config.ts && git commit -m "chore: add vitest for frontend unit tests"
```

---

## Task 2: Coordinate math module

Pure functions — no Phaser, no imports. All tests run in Node.

**Files:**
- Create: `frontend/src/game/coords.ts`
- Create: `frontend/src/game/coords.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/game/coords.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import {
  tileToWorld,
  worldToTile,
  cameraBoundsToChunkBbox,
  TILE_W,
  TILE_H,
  CHUNK_SIZE,
} from "./coords";

describe("tileToWorld", () => {
  it("maps origin tile to world origin", () => {
    expect(tileToWorld(0, 0)).toEqual({ x: 0, y: 0 });
  });

  it("maps (1, 0) correctly", () => {
    // x = (1 - 0) * 64 = 64, y = (1 + 0) * 32 = 32
    expect(tileToWorld(1, 0)).toEqual({ x: TILE_W / 2, y: TILE_H / 2 });
  });

  it("maps (0, 1) correctly", () => {
    // x = (0 - 1) * 64 = -64, y = (0 + 1) * 32 = 32
    expect(tileToWorld(0, 1)).toEqual({ x: -(TILE_W / 2), y: TILE_H / 2 });
  });

  it("maps (2, 2) correctly", () => {
    expect(tileToWorld(2, 2)).toEqual({ x: 0, y: TILE_H * 2 });
  });
});

describe("worldToTile", () => {
  it("roundtrips with tileToWorld for origin", () => {
    const world = tileToWorld(0, 0);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: 0, ty: 0 });
  });

  it("roundtrips with tileToWorld for (3, 5)", () => {
    const world = tileToWorld(3, 5);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: 3, ty: 5 });
  });

  it("roundtrips with tileToWorld for negative tile (camera left of origin)", () => {
    const world = tileToWorld(-2, 0);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: -2, ty: 0 });
  });

  it("roundtrips with tileToWorld for (0, -3)", () => {
    const world = tileToWorld(0, -3);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: 0, ty: -3 });
  });
});

describe("cameraBoundsToChunkBbox", () => {
  it("returns chunk 0,0 for world origin area", () => {
    // Small rect around origin — well within chunk (0,0)
    const bbox = cameraBoundsToChunkBbox(-100, -50, 100, 50);
    expect(bbox.min_x).toBeLessThanOrEqual(0);
    expect(bbox.min_y).toBeLessThanOrEqual(0);
    expect(bbox.max_x).toBeGreaterThanOrEqual(0);
    expect(bbox.max_y).toBeGreaterThanOrEqual(0);
  });

  it("min_x <= max_x and min_y <= max_y always", () => {
    const bbox = cameraBoundsToChunkBbox(0, 0, 1920, 1080);
    expect(bbox.min_x).toBeLessThanOrEqual(bbox.max_x);
    expect(bbox.min_y).toBeLessThanOrEqual(bbox.max_y);
  });

  it("larger viewport covers more chunks", () => {
    const small = cameraBoundsToChunkBbox(-100, -50, 100, 50);
    const large = cameraBoundsToChunkBbox(-2000, -1000, 2000, 1000);
    const smallSpan = (small.max_x - small.min_x) * (small.max_y - small.min_y);
    const largeSpan = (large.max_x - large.min_x) * (large.max_y - large.min_y);
    expect(largeSpan).toBeGreaterThan(smallSpan);
  });

  it("constants are correct values", () => {
    expect(TILE_W).toBe(128);
    expect(TILE_H).toBe(64);
    expect(CHUNK_SIZE).toBe(16);
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test -- coords
```
Expected: FAIL — `Cannot find module './coords'`

- [ ] **Step 3: Implement `frontend/src/game/coords.ts`**

```typescript
export const TILE_W = 128;  // px — isometric tile width
export const TILE_H = 64;   // px — isometric tile height (TILE_W / 2)
export const CHUNK_SIZE = 16;  // tiles per chunk side

/** Convert tile grid coordinates to Phaser world (px) coordinates. */
export function tileToWorld(tx: number, ty: number): { x: number; y: number } {
  return {
    x: (tx - ty) * (TILE_W / 2),
    y: (tx + ty) * (TILE_H / 2),
  };
}

/**
 * Convert Phaser world (px) coordinates back to tile grid coordinates.
 * Rounds to the nearest integer tile.
 */
export function worldToTile(x: number, y: number): { tx: number; ty: number } {
  return {
    tx: Math.round((x / (TILE_W / 2) + y / (TILE_H / 2)) / 2),
    ty: Math.round((y / (TILE_H / 2) - x / (TILE_W / 2)) / 2),
  };
}

/**
 * Convert a Phaser camera worldView bounding box to a chunk-coordinate bbox.
 * Adds ±1 chunk padding to avoid edge popping on fast scrolls.
 * min values are NOT clamped — the server decides which chunks exist.
 */
export function cameraBoundsToChunkBbox(
  worldX: number,
  worldY: number,
  worldRight: number,
  worldBottom: number
): { min_x: number; min_y: number; max_x: number; max_y: number } {
  // Convert all four corners to tile coords
  const corners = [
    worldToTile(worldX, worldY),
    worldToTile(worldRight, worldY),
    worldToTile(worldX, worldBottom),
    worldToTile(worldRight, worldBottom),
  ];

  const minTx = Math.min(...corners.map((c) => c.tx));
  const maxTx = Math.max(...corners.map((c) => c.tx));
  const minTy = Math.min(...corners.map((c) => c.ty));
  const maxTy = Math.max(...corners.map((c) => c.ty));

  // No clamp to zero — the server handles chunk existence; the client requests whatever
  // the camera sees, including negative indices for worlds that extend left/above origin.
  return {
    min_x: Math.floor(minTx / CHUNK_SIZE) - 1,
    min_y: Math.floor(minTy / CHUNK_SIZE) - 1,
    max_x: Math.ceil(maxTx / CHUNK_SIZE) + 1,
    max_y: Math.ceil(maxTy / CHUNK_SIZE) + 1,
  };
}
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd frontend && npm test -- coords
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/game/coords.ts frontend/src/game/coords.test.ts && git commit -m "feat: add isometric coordinate math module with unit tests"
```

---

## Task 3: ViewportStore new actions

Add `patchBase`, `patchLayers`, `removeChunk` to the existing store. Also update the `Chunk` type to add `city_id` (already present in server payloads).

**Files:**
- Modify: `frontend/src/stores/viewportStore.ts`
- Create: `frontend/src/stores/viewportStore.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/stores/viewportStore.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useViewportStore } from "./viewportStore";
import type { Chunk } from "./viewportStore";

const makeChunk = (x: number, y: number): Chunk => ({
  city_id: "city1",
  coordinates: { x, y },
  version: 1,
  base: {
    terrain: [[0]],
    buildings: [],
    roads: [],
  },
  layers: {
    electricity: {},
    pollution: {},
    water: {},
  },
});

beforeEach(() => {
  useViewportStore.setState({ loadedChunks: new Map() });
});

describe("updateChunk", () => {
  it("inserts a chunk by 'x,y' key", () => {
    const chunk = makeChunk(3, 7);
    useViewportStore.getState().updateChunk(chunk);
    expect(useViewportStore.getState().loadedChunks.get("3,7")).toEqual(chunk);
  });

  it("upserts without affecting other chunks", () => {
    useViewportStore.getState().updateChunk(makeChunk(0, 0));
    useViewportStore.getState().updateChunk(makeChunk(1, 1));
    expect(useViewportStore.getState().loadedChunks.size).toBe(2);
  });
});

describe("patchBase", () => {
  it("updates buildings and roads on an existing chunk", () => {
    useViewportStore.getState().updateChunk(makeChunk(2, 2));
    const buildings = [{ type: "residential" }];
    const roads = [{ direction: "NS" }];
    useViewportStore.getState().patchBase(2, 2, buildings, roads);

    const chunk = useViewportStore.getState().loadedChunks.get("2,2")!;
    expect(chunk.base.buildings).toEqual(buildings);
    expect(chunk.base.roads).toEqual(roads);
  });

  it("leaves layers and other fields untouched", () => {
    const original = makeChunk(2, 2);
    original.layers.electricity = { coverage: 1 };
    useViewportStore.getState().updateChunk(original);
    useViewportStore.getState().patchBase(2, 2, [], []);

    const chunk = useViewportStore.getState().loadedChunks.get("2,2")!;
    expect(chunk.layers.electricity).toEqual({ coverage: 1 });
    expect(chunk.version).toBe(1);
  });

  it("is a no-op if the chunk is not loaded", () => {
    useViewportStore.getState().patchBase(99, 99, [], []);  // must not throw
    expect(useViewportStore.getState().loadedChunks.size).toBe(0);
  });
});

describe("patchLayers", () => {
  it("updates layers on an existing chunk", () => {
    useViewportStore.getState().updateChunk(makeChunk(1, 0));
    const layers = {
      electricity: { coverage: 0.8 },
      pollution: { coverage: 0.1 },
      water: { coverage: 1 },
    };
    useViewportStore.getState().patchLayers(1, 0, layers);

    const chunk = useViewportStore.getState().loadedChunks.get("1,0")!;
    expect(chunk.layers).toEqual(layers);
  });

  it("leaves base untouched", () => {
    const original = makeChunk(1, 0);
    original.base.buildings = [{ type: "commercial" }];
    useViewportStore.getState().updateChunk(original);
    useViewportStore.getState().patchLayers(1, 0, {
      electricity: {},
      pollution: {},
      water: {},
    });

    const chunk = useViewportStore.getState().loadedChunks.get("1,0")!;
    expect(chunk.base.buildings).toEqual([{ type: "commercial" }]);
  });

  it("is a no-op if the chunk is not loaded", () => {
    useViewportStore.getState().patchLayers(99, 99, {
      electricity: {},
      pollution: {},
      water: {},
    });  // must not throw
    expect(useViewportStore.getState().loadedChunks.size).toBe(0);
  });
});

describe("removeChunk", () => {
  it("removes a loaded chunk by key", () => {
    useViewportStore.getState().updateChunk(makeChunk(5, 5));
    useViewportStore.getState().removeChunk("5,5");
    expect(useViewportStore.getState().loadedChunks.has("5,5")).toBe(false);
  });

  it("is a no-op for an unknown key", () => {
    useViewportStore.getState().removeChunk("99,99");  // must not throw
    expect(useViewportStore.getState().loadedChunks.size).toBe(0);
  });

  it("does not affect other chunks", () => {
    useViewportStore.getState().updateChunk(makeChunk(0, 0));
    useViewportStore.getState().updateChunk(makeChunk(1, 1));
    useViewportStore.getState().removeChunk("0,0");
    expect(useViewportStore.getState().loadedChunks.has("1,1")).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test -- viewportStore
```
Expected: FAIL — `patchBase is not a function` (new actions not yet added)

- [ ] **Step 3: Update `frontend/src/stores/viewportStore.ts`**

Replace the entire file. Note: `subscribeWithSelector` middleware is required so that `GameScene` can subscribe to individual slices of the store (e.g., `loadedChunks` only) — without it, all subscriptions fire on every state change. `ViewMode` is NOT re-exported here; import it from `cityStore`.

```typescript
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export interface Chunk {
  city_id: string;
  coordinates: { x: number; y: number };
  version: number;
  base: {
    terrain: number[][];
    buildings: unknown[];
    roads: unknown[];
  };
  layers: {
    electricity: Record<string, unknown>;
    pollution: Record<string, unknown>;
    water: Record<string, unknown>;
  };
}

interface ViewportStore {
  chunkX: number;
  chunkY: number;
  zoom: number;
  loadedChunks: Map<string, Chunk>;
  setViewport: (x: number, y: number) => void;
  setZoom: (zoom: number) => void;
  updateChunk: (chunk: Chunk) => void;
  patchBase: (x: number, y: number, buildings: unknown[], roads: unknown[]) => void;
  patchLayers: (x: number, y: number, layers: Chunk["layers"]) => void;
  removeChunk: (key: string) => void;
  clearChunks: () => void;
}

export const useViewportStore = create<ViewportStore>()(
  subscribeWithSelector((set) => ({
  chunkX: 0,
  chunkY: 0,
  zoom: 1,
  loadedChunks: new Map(),

  setViewport: (chunkX, chunkY) => set({ chunkX, chunkY }),
  setZoom: (zoom) => set({ zoom }),

  updateChunk: (chunk) =>
    set((state) => {
      const key = `${chunk.coordinates.x},${chunk.coordinates.y}`;
      const updated = new Map(state.loadedChunks);
      updated.set(key, chunk);
      return { loadedChunks: updated };
    }),

  patchBase: (x, y, buildings, roads) =>
    set((state) => {
      const key = `${x},${y}`;
      const chunk = state.loadedChunks.get(key);
      if (!chunk) return state;
      const updated = new Map(state.loadedChunks);
      updated.set(key, { ...chunk, base: { ...chunk.base, buildings, roads } });
      return { loadedChunks: updated };
    }),

  patchLayers: (x, y, layers) =>
    set((state) => {
      const key = `${x},${y}`;
      const chunk = state.loadedChunks.get(key);
      if (!chunk) return state;
      const updated = new Map(state.loadedChunks);
      updated.set(key, { ...chunk, layers });
      return { loadedChunks: updated };
    }),

  removeChunk: (key) =>
    set((state) => {
      if (!state.loadedChunks.has(key)) return state;
      const updated = new Map(state.loadedChunks);
      updated.delete(key);
      return { loadedChunks: updated };
    }),

  clearChunks: () => set({ loadedChunks: new Map() }),
}))
);
```

Also update `frontend/src/stores/cityStore.ts` to add `subscribeWithSelector` (required for `activeViewMode` subscription in GameScene):

```typescript
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

// ... GlobalStats interface and ViewMode type unchanged ...

export const useCityStore = create<CityStore>()(
  subscribeWithSelector((set) => ({
    cityId: null,
    cityName: null,
    globalStats: { population: 0, happiness: 50, treasury: 10000 },
    activeViewMode: "base",

    setCityId: (cityId, cityName = null) => set({ cityId, cityName }),
    setGlobalStats: (stats) =>
      set((state) => ({ globalStats: { ...state.globalStats, ...stats } })),
    setViewMode: (activeViewMode) => set({ activeViewMode }),
    clearCity: () =>
      set({
        cityId: null,
        cityName: null,
        globalStats: { population: 0, happiness: 50, treasury: 10000 },
        activeViewMode: "base",
      }),
  }))
);
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd frontend && npm test -- viewportStore
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/viewportStore.ts frontend/src/stores/viewportStore.test.ts frontend/src/stores/cityStore.ts && git commit -m "feat: add patchBase, patchLayers, removeChunk to viewportStore; add subscribeWithSelector to both stores"
```

---

## Task 4: Socket.ts — fix event handlers

Fix the two stale event handlers and add three new ones. Also add the `emitUpdateViewport` helper used by `GameScene`.

**Files:**
- Modify: `frontend/src/socket.ts`
- Create: `frontend/src/socket.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/socket.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { io } from "socket.io-client";
import { useCityStore } from "./stores/cityStore";
import { useViewportStore } from "./stores/viewportStore";
import type { Chunk } from "./stores/viewportStore";

vi.mock("socket.io-client");

// Capture registered event handlers so tests can fire them
const handlers: Record<string, (...args: unknown[]) => void> = {};
const mockSocket = {
  on: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
    handlers[event] = handler;
  }),
  emit: vi.fn(),
  disconnect: vi.fn(),
};
vi.mocked(io).mockReturnValue(mockSocket as ReturnType<typeof io>);

const makeChunk = (x: number, y: number): Chunk => ({
  city_id: "city1",
  coordinates: { x, y },
  version: 1,
  base: { terrain: [[0]], buildings: [], roads: [] },
  layers: { electricity: {}, pollution: {}, water: {} },
});

beforeEach(async () => {
  vi.clearAllMocks();
  // Re-apply mockReturnValue AFTER clearAllMocks (clearAllMocks resets it)
  vi.mocked(io).mockReturnValue(mockSocket as ReturnType<typeof io>);
  Object.keys(handlers).forEach((k) => delete handlers[k]);
  useViewportStore.setState({ loadedChunks: new Map() });
  useCityStore.setState({
    cityId: null,
    cityName: null,
    globalStats: { population: 0, happiness: 50, treasury: 10000 },
    activeViewMode: "base",
  });
  const { initSocket } = await import("./socket");
  initSocket("test-token");
});

describe("initial_state", () => {
  it("sets cityId and cityName in cityStore", () => {
    handlers["initial_state"]({
      city: {
        id: "abc123",
        name: "Testville",
        global_stats: { population: 100, treasury: 5000, happiness: 60 },
        settings: {},
      },
      chunks: [],
    });
    expect(useCityStore.getState().cityId).toBe("abc123");
    expect(useCityStore.getState().cityName).toBe("Testville");
  });

  it("sets globalStats in cityStore", () => {
    handlers["initial_state"]({
      city: {
        id: "abc123",
        name: "Testville",
        global_stats: { population: 200, treasury: 8000, happiness: 75 },
        settings: {},
      },
      chunks: [],
    });
    expect(useCityStore.getState().globalStats).toEqual({
      population: 200,
      treasury: 8000,
      happiness: 75,
    });
  });

  it("loads each chunk into viewportStore", () => {
    const chunks = [makeChunk(0, 0), makeChunk(1, 0)];
    handlers["initial_state"]({
      city: { id: "abc123", name: "Test", global_stats: { population: 0, treasury: 0, happiness: 50 }, settings: {} },
      chunks,
    });
    expect(useViewportStore.getState().loadedChunks.size).toBe(2);
    expect(useViewportStore.getState().loadedChunks.get("0,0")).toBeTruthy();
  });
});

describe("stats_update", () => {
  it("calls setGlobalStats with flat payload", () => {
    handlers["stats_update"]({
      city_id: "abc",
      population: 1500,
      treasury: 12000.5,
      happiness: 72,
    });
    expect(useCityStore.getState().globalStats).toEqual({
      population: 1500,
      treasury: 12000.5,
      happiness: 72,
    });
  });
});

describe("chunk_update", () => {
  it("calls patchBase with correct args", () => {
    useViewportStore.getState().updateChunk(makeChunk(3, 4));
    const buildings = [{ type: "industrial" }];
    const roads = [{ dir: "EW" }];
    handlers["chunk_update"]({
      city_id: "abc",
      chunk_x: 3,
      chunk_y: 4,
      buildings,
      roads,
    });
    const chunk = useViewportStore.getState().loadedChunks.get("3,4")!;
    expect(chunk.base.buildings).toEqual(buildings);
    expect(chunk.base.roads).toEqual(roads);
  });
});

describe("layers_update", () => {
  it("calls patchLayers with correct args", () => {
    useViewportStore.getState().updateChunk(makeChunk(2, 5));
    const layers = {
      electricity: { coverage: 0.9 },
      pollution: { coverage: 0.05 },
      water: { coverage: 1 },
    };
    handlers["layers_update"]({ city_id: "abc", chunk_x: 2, chunk_y: 5, layers });
    const chunk = useViewportStore.getState().loadedChunks.get("2,5")!;
    expect(chunk.layers).toEqual(layers);
  });
});

describe("viewport_seed", () => {
  it("upserts each chunk into viewportStore without clearing others", () => {
    useViewportStore.getState().updateChunk(makeChunk(0, 0));  // pre-existing
    handlers["viewport_seed"]({ city_id: "abc", chunks: [makeChunk(5, 5)] });
    expect(useViewportStore.getState().loadedChunks.size).toBe(2);
    expect(useViewportStore.getState().loadedChunks.get("5,5")).toBeTruthy();
    expect(useViewportStore.getState().loadedChunks.get("0,0")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test -- socket
```
Expected: FAIL — handlers for `stats_update`, `chunk_update`, `viewport_seed`, `layers_update` are wrong or missing

- [ ] **Step 3: Rewrite `frontend/src/socket.ts`**

```typescript
import { io, Socket } from "socket.io-client";

import { useCityStore } from "./stores/cityStore";
import type { GlobalStats } from "./stores/cityStore";
import { useViewportStore } from "./stores/viewportStore";
import type { Chunk } from "./stores/viewportStore";

let socket: Socket | null = null;

export function initSocket(token: string): Socket {
  if (socket) socket.disconnect();

  socket = io(import.meta.env.VITE_SOCKET_URL ?? "", {
    auth: { token },
    transports: ["websocket", "polling"],
  });

  socket.on("connect", () => console.log("[socket] connected"));
  socket.on("disconnect", () => console.log("[socket] disconnected"));
  socket.on("connect_error", (err) =>
    console.error("[socket] connection error:", err.message)
  );

  socket.on(
    "initial_state",
    (data: {
      city: { id: string; name: string; global_stats: GlobalStats; settings: unknown };
      chunks: Chunk[];
    }) => {
      useCityStore.getState().setCityId(data.city.id, data.city.name);
      useCityStore.getState().setGlobalStats(data.city.global_stats);
      data.chunks.forEach((chunk) => useViewportStore.getState().updateChunk(chunk));
    }
  );

  // viewport_seed: delta of newly-visible chunks — upsert, do not replace the whole map
  socket.on("viewport_seed", ({ chunks }: { chunks: Chunk[] }) => {
    chunks.forEach((chunk) => useViewportStore.getState().updateChunk(chunk));
  });

  // chunk_update: base layer changed (buildings pushed or roads updated)
  socket.on(
    "chunk_update",
    ({
      chunk_x,
      chunk_y,
      buildings,
      roads,
    }: {
      city_id: string;
      chunk_x: number;
      chunk_y: number;
      buildings: unknown[];
      roads: unknown[];
    }) => {
      useViewportStore.getState().patchBase(chunk_x, chunk_y, buildings, roads);
    }
  );

  // layers_update: overlay layer changed (electricity / pollution / water)
  socket.on(
    "layers_update",
    ({
      chunk_x,
      chunk_y,
      layers,
    }: {
      city_id: string;
      chunk_x: number;
      chunk_y: number;
      layers: Chunk["layers"];
    }) => {
      useViewportStore.getState().patchLayers(chunk_x, chunk_y, layers);
    }
  );

  // stats_update: city-wide stats (flat payload — no nested 'stats' key)
  socket.on(
    "stats_update",
    ({
      population,
      treasury,
      happiness,
    }: {
      city_id: string;
      population: number;
      treasury: number;
      happiness: number;
    }) => {
      useCityStore.getState().setGlobalStats({ population, treasury, happiness });
    }
  );

  socket.on("error", ({ message }: { message: string }) => {
    console.error("[socket] server error:", message);
  });

  return socket;
}

/** Emit update_viewport to tell the server which chunks this session is watching. */
export function emitUpdateViewport(
  cityId: string,
  bbox: { min_x: number; min_y: number; max_x: number; max_y: number }
): void {
  socket?.emit("update_viewport", { city_id: cityId, ...bbox });
}

export const getSocket = (): Socket | null => socket;

export function disconnectSocket(): void {
  socket?.disconnect();
  socket = null;
}
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd frontend && npm test -- socket
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/socket.ts frontend/src/socket.test.ts && git commit -m "feat: fix socket event handlers and add viewport_seed/layers_update/emitUpdateViewport"
```

---

## Task 5: Backend — road change routing fix

`_route_chunk_event` in `change_stream.py` only triggers `chunk_update` for `base.buildings.*` changes. Road-only updates are silently dropped. Fix: add `base.roads.*` to the condition.

**Files:**
- Modify: `backend/app/change_stream.py:44`
- Modify: `backend/tests/test_change_stream.py`

- [ ] **Step 1: Write failing test**

In `backend/tests/test_change_stream.py`, add after `test_route_chunk_push_buildings_returns_chunk_update`:

```python
def test_route_chunk_push_roads_returns_chunk_update():
    """$push to base.roads generates keys like base.roads.0 — must also trigger chunk_update."""
    doc = _make_full_document()
    event = {
        "updateDescription": {
            "updatedFields": {
                "base.roads.0": {"direction": "NS"},
                "last_updated": "...",
            }
        },
        "fullDocument": doc,
    }
    result = _route_chunk_event(event)
    assert result is not None
    event_name, payload = result
    assert event_name == "chunk_update"
    assert payload["buildings"] == doc["base"]["buildings"]
    assert payload["roads"] == doc["base"]["roads"]
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd backend && uv run pytest tests/test_change_stream.py::test_route_chunk_push_roads_returns_chunk_update -v
```
Expected: FAIL — returns `None` instead of `chunk_update`

- [ ] **Step 3: Fix `backend/app/change_stream.py`**

Change line 44 from:

```python
    if any(k.startswith("base.buildings.") for k in keys):
```

to:

```python
    if any(k.startswith("base.buildings.") or k.startswith("base.roads.") for k in keys):
```

- [ ] **Step 4: Run test — expect pass, then run full backend suite**

```bash
cd backend && uv run pytest tests/test_change_stream.py::test_route_chunk_push_roads_returns_chunk_update -v
```
Expected: PASS

```bash
cd backend && uv run pytest -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/change_stream.py backend/tests/test_change_stream.py && git commit -m "fix: route base.roads.* change stream events as chunk_update"
```

---

## Task 6: ChunkManager — isometric chunk renderer

Manages one `Phaser.GameObjects.Graphics` per loaded chunk. No unit tests — Phaser can't run in Node. Verified visually in Task 8.

**Files:**
- Create: `frontend/src/game/ChunkManager.ts`

- [ ] **Step 1: Create `frontend/src/game/ChunkManager.ts`**

```typescript
import Phaser from "phaser";
import type { Chunk } from "../stores/viewportStore";
import type { ViewMode } from "../stores/cityStore";
import { tileToWorld, TILE_W, TILE_H, CHUNK_SIZE } from "./coords";

/** Derive a fill color for one tile based on the active view mode. */
function getTileColor(
  tx: number,
  ty: number,
  chunk: Chunk,
  viewMode: ViewMode
): number {
  const layers = chunk.layers;

  if (viewMode === "electricity") {
    const cov = (layers.electricity as Record<string, number>).coverage ?? 0;
    return cov > 0 ? 0xf59e0b : 0x1f2937;
  }

  if (viewMode === "pollution") {
    const cov = (layers.pollution as Record<string, number>).coverage ?? 0;
    if (cov > 0.6) return 0xef4444;
    if (cov > 0.25) return 0xeab308;
    return 0x22c55e;
  }

  if (viewMode === "water") {
    const cov = (layers.water as Record<string, number>).coverage ?? 0;
    return cov > 0 ? 0x3b82f6 : 0x92400e;
  }

  // base mode: placeholder — use terrain color for all tiles.
  // Per-tile building/road highlighting requires knowing the building data model
  // (likely {x, y, type} objects). This will be wired up once the model is confirmed.
  // For now: any chunk with buildings shows a building-tinted color, roads show road color.
  void tx; void ty;  // suppress unused warnings until per-tile logic is added
  if (chunk.base.roads.length > 0) return 0x374151;
  if (chunk.base.buildings.length > 0) return 0x6b7280;
  return 0x4a7c59;
}

export class ChunkManager {
  private graphics = new Map<string, Phaser.GameObjects.Graphics>();

  constructor(private scene: Phaser.Scene) {}

  /** Render or re-render a chunk. Creates a new Graphics object if one doesn't exist. */
  renderChunk(chunk: Chunk, viewMode: ViewMode): void {
    const { x: cx, y: cy } = chunk.coordinates;
    const key = `${cx},${cy}`;

    let g = this.graphics.get(key);
    if (!g) {
      g = this.scene.add.graphics();
      this.graphics.set(key, g);
    } else {
      g.clear();
    }

    for (let ty = 0; ty < CHUNK_SIZE; ty++) {
      for (let tx = 0; tx < CHUNK_SIZE; tx++) {
        const worldTx = cx * CHUNK_SIZE + tx;
        const worldTy = cy * CHUNK_SIZE + ty;
        const { x, y } = tileToWorld(worldTx, worldTy);

        const color = getTileColor(tx, ty, chunk, viewMode);
        g.fillStyle(color, 1);
        g.lineStyle(1, 0x111111, 1);

        // Isometric diamond: top → right → bottom → left
        g.fillPoints(
          [
            { x: x + TILE_W / 2, y },
            { x: x + TILE_W, y: y + TILE_H / 2 },
            { x: x + TILE_W / 2, y: y + TILE_H },
            { x, y: y + TILE_H / 2 },
          ],
          true
        );
        g.strokePoints(
          [
            { x: x + TILE_W / 2, y },
            { x: x + TILE_W, y: y + TILE_H / 2 },
            { x: x + TILE_W / 2, y: y + TILE_H },
            { x, y: y + TILE_H / 2 },
          ],
          true
        );
      }
    }
  }

  /** Remove the Graphics object for a chunk that left the viewport. */
  removeChunk(key: string): void {
    const g = this.graphics.get(key);
    if (g) {
      g.destroy();
      this.graphics.delete(key);
    }
  }

  /** Re-render all currently loaded chunks (e.g. on view mode change). */
  renderAll(chunks: Map<string, Chunk>, viewMode: ViewMode): void {
    chunks.forEach((chunk, key) => {
      // Only re-render chunks we already have Graphics for
      if (this.graphics.has(key)) {
        this.renderChunk(chunk, viewMode);
      }
    });
  }

  /** Destroy all Graphics objects. Called from GameScene.shutdown(). */
  destroy(): void {
    this.graphics.forEach((g) => g.destroy());
    this.graphics.clear();
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/game/ChunkManager.ts && git commit -m "feat: add isometric ChunkManager with placeholder colored diamonds"
```

---

## Task 7: GameScene — camera + Zustand subscriptions

The main Phaser scene: sets up the camera, subscribes to Zustand for chunk changes and view mode changes, throttles `update_viewport` emission.

**Files:**
- Create: `frontend/src/game/GameScene.ts`

- [ ] **Step 1: Create `frontend/src/game/GameScene.ts`**

```typescript
import Phaser from "phaser";
import { useCityStore } from "../stores/cityStore";
import { useViewportStore } from "../stores/viewportStore";
import { ChunkManager } from "./ChunkManager";
import { cameraBoundsToChunkBbox } from "./coords";
import { emitUpdateViewport, getSocket } from "../socket";

export class GameScene extends Phaser.Scene {
  private chunkManager!: ChunkManager;
  private unsubscribeViewport!: () => void;
  private unsubscribeViewMode!: () => void;
  private viewportThrottleTimer = 0;
  private lastBboxJson: string | null = null;

  constructor() {
    super({ key: "GameScene" });
  }

  create(): void {
    this.chunkManager = new ChunkManager(this);
    this.setupCamera();
    this.subscribeToStore();

    // Emit join_city if already joined (city selection happens outside the scene)
    const cityId = useCityStore.getState().cityId;
    if (cityId) {
      getSocket()?.emit("join_city", {
        city_id: cityId,
        viewport: { chunkX: 0, chunkY: 0, radius: 2 },
      });
    }
  }

  update(_time: number, delta: number): void {
    this.viewportThrottleTimer += delta;
    if (this.viewportThrottleTimer >= 150) {
      this.viewportThrottleTimer = 0;
      this.maybeEmitViewport();
    }
  }

  shutdown(): void {
    this.unsubscribeViewport?.();
    this.unsubscribeViewMode?.();
    this.chunkManager?.destroy();
  }

  private setupCamera(): void {
    const cam = this.cameras.main;
    // Large world bounds — effectively infinite scroll
    cam.setBounds(-16384, -16384, 32768, 32768);

    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let camStartX = 0;
    let camStartY = 0;

    this.input.on("pointerdown", (p: Phaser.Input.Pointer) => {
      isDragging = true;
      dragStartX = p.x;
      dragStartY = p.y;
      camStartX = cam.scrollX;
      camStartY = cam.scrollY;
    });

    this.input.on("pointermove", (p: Phaser.Input.Pointer) => {
      if (!isDragging) return;
      cam.scrollX = camStartX - (p.x - dragStartX);
      cam.scrollY = camStartY - (p.y - dragStartY);
    });

    this.input.on("pointerup", () => {
      isDragging = false;
    });

    this.input.on(
      "wheel",
      (
        _p: Phaser.Input.Pointer,
        _go: unknown,
        _dx: number,
        dy: number
      ) => {
        const newZoom = Phaser.Math.Clamp(cam.zoom - dy * 0.001, 0.25, 2);
        cam.setZoom(newZoom);
      }
    );
  }

  private subscribeToStore(): void {
    const initialChunks = useViewportStore.getState().loadedChunks;
    const initialViewMode = useCityStore.getState().activeViewMode;

    // Render any chunks already in the store on scene start
    initialChunks.forEach((chunk) =>
      this.chunkManager.renderChunk(chunk, initialViewMode)
    );

    // Re-render on chunk changes
    this.unsubscribeViewport = useViewportStore.subscribe(
      (state) => state.loadedChunks,
      (chunks, prevChunks) => {
        const viewMode = useCityStore.getState().activeViewMode;
        // Render new or updated chunks
        chunks.forEach((chunk, key) => {
          if (chunk !== prevChunks.get(key)) {
            this.chunkManager.renderChunk(chunk, viewMode);
          }
        });
        // Remove chunks that left the viewport
        prevChunks.forEach((_, key) => {
          if (!chunks.has(key)) this.chunkManager.removeChunk(key);
        });
      }
    );

    // Re-render all chunks on view mode change
    this.unsubscribeViewMode = useCityStore.subscribe(
      (state) => state.activeViewMode,
      (viewMode) => {
        this.chunkManager.renderAll(
          useViewportStore.getState().loadedChunks,
          viewMode
        );
      }
    );
  }

  private maybeEmitViewport(): void {
    const cityId = useCityStore.getState().cityId;
    if (!cityId) return;

    const cam = this.cameras.main;
    const bbox = cameraBoundsToChunkBbox(
      cam.worldView.x,
      cam.worldView.y,
      cam.worldView.right,
      cam.worldView.bottom
    );

    const bboxJson = JSON.stringify(bbox);
    if (bboxJson !== this.lastBboxJson) {
      this.lastBboxJson = bboxJson;
      emitUpdateViewport(cityId, bbox);
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/game/GameScene.ts && git commit -m "feat: add GameScene with isometric camera and Zustand subscriptions"
```

---

## Task 8: PhaserGame, GameCanvas, App — final wiring

Wire everything together: Phaser.Game factory, React mount component, App root.

**Files:**
- Create: `frontend/src/game/PhaserGame.ts`
- Create: `frontend/src/components/GameCanvas.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/game/PhaserGame.ts`**

```typescript
import Phaser from "phaser";
import { GameScene } from "./GameScene";

export function createPhaserGame(parent: HTMLElement): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    // No width/height — Phaser.Scale.RESIZE handles sizing automatically
    backgroundColor: "#111827",
    scene: [GameScene],
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    input: {
      mouse: { preventDefaultWheel: false },
    },
  });
}
```

- [ ] **Step 2: Create `frontend/src/components/GameCanvas.tsx`**

```typescript
import { useEffect, useRef } from "react";
import { createPhaserGame } from "../game/PhaserGame";

export function GameCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const game = createPhaserGame(containerRef.current);
    return () => {
      game.destroy(true);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ position: "fixed", inset: 0, zIndex: 0 }}
    />
  );
}
```

- [ ] **Step 3: Update `frontend/src/App.tsx`**

```typescript
import { GameCanvas } from "./components/GameCanvas";

export default function App() {
  return <GameCanvas />;
}
```

- [ ] **Step 4: Run the full frontend test suite**

```bash
cd frontend && npm test
```
Expected: all tests PASS (coords, viewportStore, socket — 20+ tests)

- [ ] **Step 5: Run the dev server and verify visually**

Start the backend and dev server:
```bash
# Terminal 1
cd backend && uvicorn app.main:socket_app --reload

# Terminal 2
cd frontend && npm run dev
```

Open http://localhost:3000. Expected: dark gray canvas fills the screen (`#111827` background). No errors in browser console. Phaser logo briefly appears in top-left corner (normal Phaser boot behavior).

To verify chunk rendering, open the browser console and seed a test chunk:
```javascript
// Paste in browser console to test rendering directly
import('/src/stores/viewportStore.js').then(m => {
  m.useViewportStore.getState().updateChunk({
    city_id: 'test', coordinates: { x: 0, y: 0 }, version: 1,
    base: { terrain: [[0]], buildings: [], roads: [] },
    layers: { electricity: {}, pollution: {}, water: {} }
  })
})
```
Expected: green isometric diamond tiles appear in the center of the canvas.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/game/PhaserGame.ts frontend/src/components/GameCanvas.tsx frontend/src/App.tsx && git commit -m "feat: wire up PhaserGame factory, GameCanvas component, and App root"
```

---

## Done

All eight tasks complete. The game canvas renders isometric placeholder tiles wired to the backend change stream. Test coverage: 20+ unit tests across coords, viewportStore, and socket modules. Visual verification via dev server.

Final check:
```bash
cd frontend && npm test && cd ../backend && uv run pytest -v
```
Expected: all frontend and backend tests pass.
