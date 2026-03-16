# Asset Manager Tool — Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Scope:** Developer-only tool for generating and managing building artwork using a local Stable Diffusion (A1111) instance.

---

## Overview

A standalone web app (`tools/asset-manager/`) for browsing all building categories, viewing current artwork, and regenerating individual assets via Stable Diffusion. After generation, backgrounds are removed using `@imgly/background-removal-node` (produces transparent RGBA PNGs). Assets are saved to `frontend/public/assets/buildings/` so the Vite dev server serves them directly to the game at `/assets/buildings/{category}/{building_type}.png`.

This tool is for developer use only. A player-facing version (connected to the premium SD pipeline) will be revisited after the game is running.

---

## Prerequisites

Before running the tool, the following must be set up in A1111:

- **Base model:** SDXL 1.0 (or a compatible SDXL checkpoint)
- **LoRA:** `Stylized_Setting_SDXL` installed in A1111's `models/Lora/` directory
- **Launch flag:** A1111 must be started with `--api` to enable the REST API
- A1111 is expected at `http://localhost:7860`

---

## Architecture

### Location

```
tools/asset-manager/
  server/
    index.js          # Express entry point (port 3001)
    routes/
      generate.js     # POST /api/generate — calls A1111, runs bg removal, saves preview
      assets.js       # GET /api/assets — scans disk, returns status map
      accept.js       # POST /api/accept — promotes _preview to final
      discard.js      # POST /api/discard — deletes _preview file
  client/
    src/
      App.tsx
      components/
        Sidebar.tsx         # Category list
        BuildingGrid.tsx    # Building type cards for selected category
        BuildingCard.tsx    # Individual card (thumbnail + status indicator)
        RegenDrawer.tsx     # Side drawer: current image, prompts, generate button
      hooks/
        useAssets.ts        # Fetches /api/assets on load
        useGenerate.ts      # Manages generation request lifecycle
    index.html
    vite.config.ts          # Proxies /api/* to Express on port 3001
  package.json
  .env.example              # VITE_API_URL=http://localhost:3001 (if proxy is bypassed)
```

### npm Scripts

```json
{
  "scripts": {
    "dev": "concurrently \"npm run server\" \"npm run client\"",
    "server": "node server/index.js",
    "client": "vite --port 3002"
  }
}
```

Do **not** set `"type": "module"` or `"type": "commonjs"`. Omitting `"type"` defaults Node to CommonJS for `.js` files, which is what the server needs (`__dirname`, `require()`). Vite loads `vite.config.ts` via its own bundler (esbuild) and is unaffected by the package.json `"type"` field.

### Vite Proxy

The Vite dev server (port 3002) proxies all `/api/*` requests to Express (port 3001), avoiding CORS issues:

```ts
// client/vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3002,
    proxy: {
      '/api': 'http://localhost:3001',
      '/assets': 'http://localhost:3001',
    },
  },
})
```

### Asset Storage

Assets live in the game's Vite public directory so they are served at `/assets/buildings/...` by the frontend dev server:

```
frontend/public/assets/
  buildings/
    residential/
      apartment.png
      house.png
      mansion.png
      tenement.png
    commercial/
      shop.png
      office.png
      mall.png
      restaurant.png
    industrial/
      factory.png
      warehouse.png
      power_plant.png
      refinery.png
    civic/
      park.png
      school.png
      hospital.png
      police_station.png
      fire_station.png
      city_hall.png
```

Express serves this directory statically so the asset manager's own client can also load them:

```js
app.use('/assets', express.static(path.resolve(__dirname, '../../frontend/public/assets')))
```

**Note:** The relative path `../../frontend/public/assets` is load-bearing. If the main game frontend ever moves its public directory, this path must be updated in sync.

Preview files use the suffix `_preview.png` (e.g. `apartment_preview.png`) and live alongside the final file. They are deleted on discard or overwritten on accept.

All generated PNGs are transparent RGBA (background removed). The drawer and card thumbnails display them against the UI's dark background — no checkerboard needed.

---

## Building Taxonomy

Defined as a config object in `server/index.js`. Easy to extend.

```js
const BUILDINGS = {
  residential: ['apartment', 'house', 'mansion', 'tenement'],
  commercial:  ['shop', 'office', 'mall', 'restaurant'],
  industrial:  ['factory', 'warehouse', 'power_plant', 'refinery'],
  civic:       ['park', 'school', 'hospital', 'police_station', 'fire_station', 'city_hall'],
}
```

---

## Prompt Template

The building type is interpolated into a fixed template. Prompts are pre-filled in the drawer but fully editable before generating.

**Positive:**
```
((masterpiece, best quality)), <lora:Stylized_Setting_SDXL:0.7>, Isometric_Setting, simcity {building_type}, plain background
```

**Negative:**
```
EasyNegative, (worst quality, low quality: 1.0)
```

`{building_type}` is replaced with the type name (e.g. `power_plant`, `city_hall`, `apartment`).

---

## UI Layout

**Sidebar + Main Panel** layout:

- **Left sidebar** — fixed-width list of categories. Active category highlighted.
- **Main panel** — grid of building type cards for the selected category.
- **Right drawer** — slides in when a card is clicked. Contains current image, editable prompts, and generate controls.

### Building Card States

| State | Visual |
|---|---|
| Generated (`ready`) | Thumbnail of final PNG, green "Generated" badge |
| Preview pending (`preview`) | Thumbnail of preview PNG, amber "Preview" badge |
| Missing (`missing`) | Placeholder icon, red "Missing" badge |

### Drawer States

| State | Behaviour |
|---|---|
| Idle | Current image shown (or placeholder). Prompts pre-filled. Generate button active. |
| Generating | Generate button replaced with spinner. Prompts locked. No second generation possible (button disabled). |
| Preview ready | New image shown alongside current (side by side). Accept and Discard buttons shown. |
| Accepted | Preview becomes the current image. Drawer returns to Idle. |
| Discarded | Preview removed. Drawer returns to Idle with original image. |
| Failed | Inline error message shown (e.g. "Generation failed — A1111 may be offline"). Generate button re-enabled. |

The Generate button is disabled for the duration of a generation request, preventing concurrent generation conflicts on the same building.

---

## Generation Flow

```
User clicks Generate in drawer
        │
        ▼
Frontend POST /api/generate
  { building_type, category, prompt, negative_prompt }
        │
        ▼
Express → A1111 POST http://localhost:7860/sdapi/v1/txt2img
  {
    prompt,
    negative_prompt,
    width: 512,
    height: 512,
    steps: 30,
    cfg_scale: 7.5,
    sampler_name: "DPM++ 2M Karras",
    seed: -1
  }
        │
        ▼
A1111 returns { images: [base64String] }
        │
        ▼
Express: decode base64 → Buffer
  → @imgly/background-removal-node: removeBackground(buffer.buffer)
  → Blob → ArrayBuffer → Buffer (transparent RGBA PNG)
        │
        ▼
Save to frontend/public/assets/buildings/{category}/{building_type}_preview.png
        │
        ▼
Return { previewUrl: '/assets/buildings/{category}/{building_type}_preview.png' }
        │
        ▼
Frontend shows new image + Accept / Discard

  Accept  → POST /api/accept  → rename _preview.png to {building_type}.png
  Discard → POST /api/discard → delete _preview.png
```

### Background Removal Usage

```js
import { removeBackground } from '@imgly/background-removal-node'

// inputBuffer is a Buffer decoded from A1111's base64 output
// removeBackground does NOT accept a Node Buffer — pass the underlying ArrayBuffer
const blob = await removeBackground(inputBuffer.buffer)
const arrayBuffer = await blob.arrayBuffer()
const outputBuffer = Buffer.from(arrayBuffer)
// outputBuffer is a transparent RGBA PNG — write directly to disk
await fs.promises.writeFile(previewPath, outputBuffer)
```

`removeBackground` accepts a `string` (URL/path), `ArrayBuffer`, `Blob`, or `ImageData` — **not** a Node.js `Buffer`. Pass `inputBuffer.buffer` (the underlying `ArrayBuffer`). It returns a `Blob` containing a transparent PNG.

### Background Removal Notes

`@imgly/background-removal-node` downloads ONNX model weights on first run (cached at `~/.imgly/models/`). First-run download takes 30–60 seconds depending on connection. Subsequent runs use the cache. No pre-download step is needed — the library handles it automatically. On first run the server logs a download progress indicator to stdout so the developer knows the hang is expected.

Generation is handled synchronously (the HTTP response is held open until the image is ready). A1111 inference at 30 steps on a mid-range GPU takes approximately 5–15 seconds. Background removal adds approximately 3–8 seconds. Total expected latency: 10–25 seconds per generation. The drawer spinner covers this wait.

---

## API Endpoints

```
GET  /api/assets
     Scans frontend/public/assets/buildings/ on each request.
     Status values per building:
       'ready'    — final file ({building_type}.png) exists
       'preview'  — only _preview.png exists (pending accept/discard)
       'missing'  — neither file exists
     Returns: { residential: { apartment: 'ready' | 'preview' | 'missing' }, ... }

POST /api/generate
     Body: { building_type, category, prompt, negative_prompt }
     Response 200: { previewUrl: '/assets/buildings/{category}/{building_type}_preview.png' }
     Response 409: { error: 'Generation already in progress for this building' }
             — returned if an in-flight request for this building_type+category already exists
               (tracked in an in-process Set on the server; cleared on completion or error)
     Response 502: { error: 'A1111 unreachable' }
     Response 500: { error: 'Generation failed', detail: string }

POST /api/accept
     Body: { building_type, category }
     Response 200: { finalUrl: '/assets/buildings/{category}/{building_type}.png' }
     Response 404: { error: 'No preview found' } — if _preview.png does not exist

POST /api/discard
     Body: { building_type, category }
     Response 204
     Response 404: { error: 'No preview found' } — if _preview.png does not exist
```

**Concurrent generation guard (server-side):** The server maintains an in-process `Set` of `"{category}/{building_type}"` keys for in-flight requests. Before calling A1111, the key is added to the set. On completion or error it is removed. Any duplicate POST to `/api/generate` for the same key returns 409 immediately. This prevents race conditions from multiple tabs or direct API calls.

Static assets served by Express from `frontend/public/assets/` at `/assets/*`.

---

## Running the Tool

```bash
cd tools/asset-manager
npm install
npm run dev
# Express: http://localhost:3001
# Vite:    http://localhost:3002  ← open this in browser
```

Requires A1111 running locally with `--api` flag on `http://localhost:7860`.

---

## Dependencies

| Package | Purpose |
|---|---|
| `express` | HTTP server |
| `@imgly/background-removal-node` | Background removal post-generation |
| `axios` | A1111 API calls from server |
| `concurrently` | Run server + Vite dev server together |
| `vite` | Frontend build tooling |
| `react` + `react-dom` | Frontend framework |
| `typescript` | Type safety |
| `@vitejs/plugin-react` | Vite React plugin |
| `tailwindcss` | Styling |

---

## Out of Scope (for now)

- Player-facing asset management (revisit after game is running)
- Style palette integration (art deco, brutalist, cyberpunk prompt modifiers)
- Batch generation of all missing assets in one click
- Generation history / rollback to previous versions
- Auth / access control (developer-only tool, runs locally)
