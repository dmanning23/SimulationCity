# Phase 4: Frontend Game Canvas — Design Spec

**Date:** 2026-03-25
**Scope:** Week 7–8 of the SimulationCity development roadmap
**Status:** Approved

---

## Overview

Phase 4 builds the game canvas: a Phaser 3 scene that renders the city as an isometric tile map, wired to the backend via Socket.IO and Zustand. React floats as a transparent overlay on top of the Phaser canvas. Tile graphics are colored placeholder diamonds (128×64px); real art assets are deferred until the Artwork Tool is ready.

Scope: frontend only. No new backend changes. No tile click / tool interaction (Phase 5).

---

## Architecture

```
App.tsx
  └── <GameCanvas />        ← React component, mounts/destroys Phaser
        └── Phaser.Game     ← canvas fills viewport (position: fixed, inset: 0)
              └── GameScene
                    └── ChunkManager
                          └── Map<chunkKey, Phaser.GameObjects.Graphics>

React HUD overlay           ← Phase 5 (not this phase)
```

Phaser owns the full-screen canvas. React UI panels will be absolutely-positioned divs layered on top via CSS (`pointer-events: none` on the wrapper; `pointer-events: auto` on interactive elements). This separation keeps Phaser's input system unmodified and avoids React/Phaser DOM conflicts.

### Data Flow

```
Backend
  │
  ▼
socket.ts
  │  initial_state  → viewportStore.setChunks(chunks) + cityStore.setCityId + cityStore.setGlobalStats
  │  viewport_seed  → viewportStore.updateChunk() per chunk     ← delta: newly visible chunks only
  │  chunk_update   → viewportStore.patchBase(chunk_x, chunk_y, buildings, roads)
  │  layers_update  → viewportStore.patchLayers(chunk_x, chunk_y, layers)
  │  stats_update   → cityStore.setGlobalStats(population, treasury, happiness)
  │
  ▼
Zustand stores (source of truth)
  │  viewportStore.loadedChunks: Map<"x,y", Chunk>
  │  cityStore.activeViewMode: "base" | "electricity" | "pollution" | "water"
  │
  │  subscribe()
  ▼
GameScene → ChunkManager
  │  on loadedChunks change: renderChunk() for each new/updated chunk
  │  on activeViewMode change: re-render all loaded chunks
  │  on chunk removed: destroy Graphics object
  │
  ▼
Phaser canvas (isometric diamond tiles, 128×64px)
```

Camera scroll/zoom → throttled (150ms) → `emitUpdateViewport(bbox)` → server → `viewport_seed`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `frontend/src/game/coords.ts` | Isometric ↔ world coordinate math |
| Create | `frontend/src/game/ChunkManager.ts` | Phaser Graphics per chunk; isometric rendering |
| Create | `frontend/src/game/GameScene.ts` | Main Phaser scene: camera, Zustand subscriptions |
| Create | `frontend/src/game/PhaserGame.ts` | Phaser.Game factory + config |
| Create | `frontend/src/components/GameCanvas.tsx` | React component that mounts/destroys Phaser |
| Modify | `frontend/src/socket.ts` | Fix stale event names; add viewport_seed, layers_update, emitUpdateViewport |
| Modify | `frontend/src/stores/viewportStore.ts` | Add patchBase, patchLayers, removeChunk |
| Modify | `frontend/src/App.tsx` | Mount `<GameCanvas />` |
| Create | `frontend/src/game/coords.test.ts` | Unit tests for coordinate math |
| Create | `frontend/src/stores/viewportStore.test.ts` | Unit tests for store actions |
| Create | `frontend/src/socket.test.ts` | Unit tests for socket event handlers |

---

## New Module: `frontend/src/game/coords.ts`

Pure math, no imports. All coordinate functions are pure — no Phaser dependency.

```typescript
export const TILE_W = 128;  // px
export const TILE_H = 64;   // px
export const CHUNK_SIZE = 16;  // tiles per side

/** Tile (tx, ty) → Phaser world (x, y) */
export function tileToWorld(tx: number, ty: number): { x: number; y: number } {
  return {
    x: (tx - ty) * (TILE_W / 2),
    y: (tx + ty) * (TILE_H / 2),
  };
}

/** Phaser world (x, y) → tile (tx, ty) — rounded to integer */
export function worldToTile(x: number, y: number): { tx: number; ty: number } {
  return {
    tx: Math.round((x / (TILE_W / 2) + y / (TILE_H / 2)) / 2),
    ty: Math.round((y / (TILE_H / 2) - x / (TILE_W / 2)) / 2),
  };
}

/** Camera worldView bounds → chunk bbox { min_x, min_y, max_x, max_y } */
export function cameraBoundsToChunkBbox(
  worldX: number, worldY: number, worldRight: number, worldBottom: number
): { min_x: number; min_y: number; max_x: number; max_y: number } { ... }
```

`cameraBoundsToChunkBbox` converts the four worldView corners to tile coords via `worldToTile`, takes the min/max tile indices, then divides by `CHUNK_SIZE` and floors/ceils to get chunk indices. Adds ±1 chunk padding to avoid edge popping.

---

## New Module: `frontend/src/game/ChunkManager.ts`

Manages one `Phaser.GameObjects.Graphics` object per loaded chunk. Called from `GameScene`.

```typescript
export class ChunkManager {
  private graphics = new Map<string, Phaser.GameObjects.Graphics>();

  constructor(private scene: Phaser.Scene) {}

  /** Render or re-render a chunk. Creates Graphics if needed. */
  renderChunk(chunk: Chunk, viewMode: ViewMode): void;

  /** Remove and destroy Graphics for a chunk that left the viewport. */
  removeChunk(key: string): void;

  /** Re-render all currently loaded chunks (called on viewMode change). */
  renderAll(chunks: Map<string, Chunk>, viewMode: ViewMode): void;

  /** Destroy all Graphics objects (called on scene shutdown). */
  destroy(): void;
}
```

### Tile rendering

Each tile in the 16×16 grid is drawn as an isometric diamond (4-point polygon) using `graphics.fillPoints()`. The tile's world origin comes from `tileToWorld(chunkX * 16 + tileX, chunkY * 16 + tileY)`.

Diamond points (relative to tile origin):
```
top:    (TILE_W/2,  0)
right:  (TILE_W,    TILE_H/2)
bottom: (TILE_W/2,  TILE_H)
left:   (0,         TILE_H/2)
```

Tile color is determined by `getTileColor(tileX, tileY, chunk, viewMode)` — a pure function that reads `chunk.base` and `chunk.layers` to select the appropriate fill color.

### Placeholder color palette

**base mode** (priority: road > building > terrain)
- terrain 0 (grass): `0x4a7c59`
- building present: `0x6b7280`
- road present: `0x374151`

**electricity mode**
- powered (`layers.electricity.coverage > 0`): `0xf59e0b`
- unpowered: `0x1f2937`

**pollution mode** (based on `layers.pollution.coverage`)
- ≤ 0.25: `0x22c55e` (clean)
- 0.25–0.6: `0xeab308` (moderate)
- \> 0.6: `0xef4444` (heavy)

**water mode**
- covered (`layers.water.coverage > 0`): `0x3b82f6`
- no water: `0x92400e`

All tiles get a 1px dark stroke outline using a fixed color: `graphics.lineStyle(1, 0x111111, 1)`.

---

## New Module: `frontend/src/game/GameScene.ts`

Extends `Phaser.Scene`. Owns the camera and coordinates Zustand subscriptions.

```typescript
export class GameScene extends Phaser.Scene {
  private chunkManager!: ChunkManager;
  private unsubscribeViewport!: () => void;
  private unsubscribeViewMode!: () => void;
  private viewportThrottleTimer = 0;
  private lastBbox: string | null = null;  // JSON string of last emitted bbox

  create(): void {
    this.chunkManager = new ChunkManager(this);
    this.setupCamera();
    this.subscribeToStore();
    socket.emit("join_city", { city_id: cityStore.cityId, viewport: { chunkX: 0, chunkY: 0, radius: 2 } });
  }

  update(_time: number, delta: number): void {
    this.viewportThrottleTimer += delta;
    if (this.viewportThrottleTimer >= 150) {
      this.viewportThrottleTimer = 0;
      this.maybeEmitViewport();
    }
  }

  shutdown(): void {
    this.unsubscribeViewport();
    this.unsubscribeViewMode();
    this.chunkManager.destroy();
  }
}
```

**Camera setup:**
- Enable drag scroll via Phaser pointer input (`setDragDistance`, pointer down/move/up)
- Mouse wheel → `camera.zoom`, clamped to `[0.25, 2]`
- `camera.setBounds` set to a large world (e.g. 32768×32768) to allow free scroll

**Zustand subscriptions** (set up in `create`, torn down in `shutdown`):
```typescript
// Re-render changed chunks
this.unsubscribeViewport = useViewportStore.subscribe(
  (state) => state.loadedChunks,
  (chunks, prevChunks) => {
    // Render new/updated chunks
    chunks.forEach((chunk, key) => {
      if (chunk !== prevChunks.get(key)) {
        this.chunkManager.renderChunk(chunk, useCityStore.getState().activeViewMode);
      }
    });
    // Remove chunks that left the viewport
    prevChunks.forEach((_, key) => {
      if (!chunks.has(key)) this.chunkManager.removeChunk(key);
    });
  }
);

// Re-render all on view mode change
this.unsubscribeViewMode = useCityStore.subscribe(
  (state) => state.activeViewMode,
  (viewMode) => {
    this.chunkManager.renderAll(useViewportStore.getState().loadedChunks, viewMode);
  }
);
```

**`maybeEmitViewport`**: converts `this.cameras.main.worldView` → chunk bbox via `cameraBoundsToChunkBbox`, compares to `lastBbox`, emits `update_viewport` only if changed.

---

## New Module: `frontend/src/game/PhaserGame.ts`

```typescript
import Phaser from "phaser";
import { GameScene } from "./GameScene";

export function createPhaserGame(parent: HTMLElement): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: "100%",
    height: "100%",
    backgroundColor: "#111827",
    scene: [GameScene],
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    input: { mouse: { preventDefaultWheel: false } },
  });
}
```

---

## New Component: `frontend/src/components/GameCanvas.tsx`

```typescript
export function GameCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const game = createPhaserGame(containerRef.current);
    return () => { game.destroy(true); };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ position: "fixed", inset: 0, zIndex: 0 }}
    />
  );
}
```

The `useEffect` cleanup destroys the Phaser game on unmount. In React Strict Mode (dev), effects run twice — Phaser's `destroy(true)` is safe to call on a freshly created game, so this is fine.

---

## Changes to Existing Code

### `frontend/src/socket.ts`

**Updated/fixed handlers:**

```typescript
// RENAME: city_stats_update → stats_update; update to flat payload shape
socket.on("stats_update", ({ population, treasury, happiness }) => {
  useCityStore.getState().setGlobalStats({ population, treasury, happiness });
});

// FIX payload shape: was { chunk: Chunk }, now { city_id, chunk_x, chunk_y, buildings, roads }
socket.on("chunk_update", ({ chunk_x, chunk_y, buildings, roads }) => {
  useViewportStore.getState().patchBase(chunk_x, chunk_y, buildings, roads);
});

// initial_state: already correct event name and city/chunks structure. The payload
// also includes `settings` (city config) which is intentionally ignored in Phase 4.
socket.on("initial_state", (data) => {
  useCityStore.getState().setCityId(data.city.id, data.city.name);
  useCityStore.getState().setGlobalStats(data.city.global_stats);
  data.chunks.forEach((chunk) => useViewportStore.getState().updateChunk(chunk));
});
```

**New event handlers:**
```typescript
// viewport_seed: upsert each newly-visible chunk (delta, not full replacement)
socket.on("viewport_seed", ({ chunks }: { chunks: Chunk[] }) => {
  chunks.forEach((chunk) => useViewportStore.getState().updateChunk(chunk));
});

socket.on("layers_update", ({ chunk_x, chunk_y, layers }: LayersUpdatePayload) => {
  useViewportStore.getState().patchLayers(chunk_x, chunk_y, layers);
});
```

**Note on road updates:** The backend `change_stream.py` currently only triggers `chunk_update` for `base.buildings.*` field changes. Road-only changes (`base.roads.*`) are not routed. A follow-up fix to `change_stream.py` is needed to add `base.roads.*` prefix matching — deferred to the Phase 4 implementation task that touches `change_stream.py`.

**New emit helper:**
```typescript
export function emitUpdateViewport(
  cityId: string,
  bbox: { min_x: number; min_y: number; max_x: number; max_y: number }
): void {
  socket?.emit("update_viewport", { city_id: cityId, ...bbox });
}
```

### `frontend/src/stores/viewportStore.ts`

**New actions:**
```typescript
// Partial update — base layer only (from chunk_update)
patchBase: (x: number, y: number, buildings: unknown[], roads: unknown[]) => void;

// Partial update — overlay layers only (from layers_update)
patchLayers: (x: number, y: number, layers: Chunk["layers"]) => void;

// Remove a chunk from the map
removeChunk: (key: string) => void;
```

`updateChunk` (existing) is used for all full-chunk upserts: `initial_state`, `viewport_seed`. It upserts by key — it does NOT replace the entire map, so chunks outside the new payload remain loaded.

**Chunk type** — add `city_id` field to match server payload:
```typescript
export interface Chunk {
  city_id: string;
  coordinates: { x: number; y: number };
  version: number;
  base: { terrain: number[][]; buildings: unknown[]; roads: unknown[] };
  layers: {
    electricity: Record<string, unknown>;
    pollution: Record<string, unknown>;
    water: Record<string, unknown>;
  };
}
```

### `frontend/src/App.tsx`

Replace the placeholder with:
```typescript
import { GameCanvas } from "./components/GameCanvas";

export default function App() {
  return <GameCanvas />;
}
```

---

## Socket Events Reference

### Client → Server

| Event | Payload |
|-------|---------|
| `join_city` | `{ city_id: string, viewport: { chunkX: 0, chunkY: 0, radius: 2 } }` |
| `update_viewport` | `{ city_id, min_x, min_y, max_x, max_y }` |

### Server → Client

| Event | Payload | Handler |
|-------|---------|---------|
| `initial_state` | `{ city: { id, name, global_stats, settings }, chunks: Chunk[] }` | cityStore + viewportStore |
| `viewport_seed` | `{ city_id, chunks: Chunk[] }` | viewportStore.updateChunk (per chunk) |
| `chunk_update` | `{ city_id, chunk_x, chunk_y, buildings, roads }` | viewportStore.patchBase |
| `layers_update` | `{ city_id, chunk_x, chunk_y, layers }` | viewportStore.patchLayers |
| `stats_update` | `{ city_id, population, treasury, happiness }` | cityStore.setGlobalStats |
| `error` | `{ message: string }` | console.error |

---

## Testing

### Unit tests (`frontend/src/game/coords.test.ts`)
- `tileToWorld` and `worldToTile` roundtrip: `worldToTile(tileToWorld(tx, ty)) ≈ (tx, ty)` for several coordinates
- `cameraBoundsToChunkBbox` returns correct chunk indices for a known worldView rect
- Edge case: negative tile coordinates (camera scrolled left of origin)

### Unit tests (`frontend/src/stores/viewportStore.test.ts`)
- `updateChunk` upserts by key `"x,y"`; existing chunks at other keys are unaffected
- `patchBase` updates only `base.buildings` and `base.roads`, leaves other fields untouched
- `patchLayers` updates only `layers`, leaves `base` untouched
- `removeChunk` removes the key; no-op if key absent
- Two chunks with different keys don't interfere

### Unit tests (`frontend/src/socket.test.ts`)
- `stats_update` event calls `cityStore.setGlobalStats` with correct shape
- `chunk_update` event calls `viewportStore.patchBase` with correct args
- `layers_update` event calls `viewportStore.patchLayers` with correct args
- `viewport_seed` event calls `viewportStore.updateChunk` for each chunk in the array
- `initial_state` event calls both `cityStore.setCityId` and `viewportStore.updateChunk` per chunk

---

## What's Not In Scope

- Tile click / hover / selection — Phase 5
- HUD, tool palette, view mode switcher UI — Phase 5
- Edge scrolling — deferred
- Playwright E2E canvas tests — Phase 7
- Phaser React Strict Mode double-init guard — `createPhaserGame` called in `useEffect` with cleanup is sufficient; no additional guard needed
