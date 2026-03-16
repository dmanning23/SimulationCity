# Asset Manager Tool — Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Scope:** Developer-only tool for generating and managing building artwork using a local Stable Diffusion (A1111) instance.

---

## Overview

A standalone web app (`tools/asset-manager/`) for browsing all building categories, viewing current artwork, and regenerating individual assets via Stable Diffusion. After generation, backgrounds are removed using `@imgly/background-removal-node`. Assets are saved to a shared `assets/buildings/` directory at the repo root, which the game will reference directly.

This tool is for developer use only. A player-facing version (connected to the premium SD pipeline) will be revisited after the game is running.

---

## Architecture

### Location

```
tools/asset-manager/
  server/
    index.js          # Express server entry point
    routes/
      generate.js     # POST /api/generate — calls A1111, runs bg removal, saves file
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
        RegenDrawer.tsx     # Side drawer with current image, prompts, generate button
      hooks/
        useAssets.ts        # Fetches /api/assets on load
        useGenerate.ts      # Manages generation request lifecycle
    index.html
    vite.config.ts
  package.json              # Dependencies for both server and client
```

### Asset Storage

Assets live at the repo root so both the tool and the game can reference them:

```
assets/
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

Preview files (during generation) use the suffix `_preview.png` alongside the final file and are deleted on discard or overwritten on accept.

---

## Building Taxonomy

Defined as a config object in the server. Easy to extend.

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

The building type is interpolated into a fixed template. Prompts are pre-filled but fully editable in the drawer before generating.

**Positive:**
```
((masterpiece, best quality)), <lora:Stylized_Setting_SDXL:0.7>, Isometric_Setting, simcity {building_type}, plain background
```

**Negative:**
```
EasyNegative, (worst quality, low quality: 1.0)
```

`{building_type}` is replaced with the building's type name (e.g. `power_plant`, `city_hall`).

---

## UI Layout

**Sidebar + Main Panel** layout. Two persistent regions:

- **Left sidebar** — fixed-width list of categories. Active category highlighted.
- **Main panel** — grid of building type cards for the selected category.
- **Right drawer** — slides in when a card is clicked. Contains current image, editable prompts, and generate controls.

### Building Card States

| State | Visual |
|---|---|
| Generated | Thumbnail of PNG, green "Generated" badge |
| Missing | Placeholder graphic, red "Missing" badge, "Generate" CTA |

### Drawer States

| State | Behaviour |
|---|---|
| Idle | Shows current image (or placeholder if missing). Prompt fields pre-filled. Generate button active. |
| Generating | Generate button replaced with spinner/progress indicator. Prompts locked. |
| Preview ready | New image shown alongside current. Accept and Discard buttons shown. |
| Accepted | Drawer shows new image as current. Returns to Idle state. |
| Discarded | New image removed. Returns to Idle state with original. |

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
  { prompt, negative_prompt, width: 512, height: 512,
    steps: 30, cfg_scale: 7.5 }
        │
        ▼
A1111 returns base64 PNG
        │
        ▼
Express: decode base64 → run @imgly/background-removal-node
        │
        ▼
Save to assets/buildings/{category}/{building_type}_preview.png
        │
        ▼
Return { previewUrl: '/assets/buildings/{category}/{building_type}_preview.png' }
        │
        ▼
Frontend shows Accept / Discard

Accept → POST /api/accept → rename _preview.png → {building_type}.png
Discard → POST /api/discard → delete _preview.png
```

---

## API Endpoints

```
GET  /api/assets
     Returns status map: { residential: { apartment: 'ready' | 'missing' }, ... }

POST /api/generate
     Body: { building_type, category, prompt, negative_prompt }
     Response: { previewUrl }

POST /api/accept
     Body: { building_type, category }
     Response: { finalUrl }

POST /api/discard
     Body: { building_type, category }
     Response: 204
```

Static assets served by Express from the repo-root `assets/` directory.

---

## Running the Tool

```bash
cd tools/asset-manager
npm install
npm run dev       # starts both Express (port 3001) and Vite (port 3002) concurrently
```

Requires A1111 running locally with `--api` flag on `http://localhost:7860`.

---

## Dependencies

| Package | Purpose |
|---|---|
| `express` | HTTP server |
| `@imgly/background-removal-node` | Background removal after generation |
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
- Style palette integration (art deco, brutalist, cyberpunk modifiers)
- Batch generation of all missing assets in one click
- Generation history / rollback to previous versions
- Auth / access control (developer-only tool, runs locally)
