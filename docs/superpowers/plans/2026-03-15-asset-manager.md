# Asset Manager Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a developer-only web app for browsing, generating, and managing building artwork for SimulationCity using a local Stable Diffusion (A1111) instance.

**Architecture:** Express server (port 3001) handles A1111 API calls, background removal, and asset file management. Vite + React client (port 3002) provides the UI with a sidebar, building card grid, and slide-in drawer for generation. Assets are saved to `frontend/public/assets/buildings/` so the game's Vite dev server can serve them directly.

**Tech Stack:** Node.js, Express, axios, @imgly/background-removal-node, Jest, supertest, React 18, TypeScript, Vite, Vitest, React Testing Library, Tailwind CSS

---

## Chunk 1: Project Scaffold + Server Foundation + /api/assets

### Task 1: Scaffold the project

**Files:**
- Create: `tools/asset-manager/package.json`
- Create: `tools/asset-manager/.env.example`
- Create: `tools/asset-manager/server/config.js`
- Create: `tools/asset-manager/server/buildings.js`
- Create: `tools/asset-manager/server/index.js`

- [ ] **Step 1: Create `tools/asset-manager/package.json`**

```json
{
  "name": "simulationcity-asset-manager",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "concurrently \"npm run server\" \"npm run client\"",
    "server": "node server/index.js",
    "client": "vite client --port 3002",
    "test:server": "jest --testMatch='**/tests/server/**/*.test.js'",
    "test:client": "vitest run client/src"
  },
  "dependencies": {
    "@imgly/background-removal-node": "^1.4.0",
    "axios": "^1.7.0",
    "express": "^4.19.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.0",
    "concurrently": "^8.2.0",
    "jest": "^29.7.0",
    "jsdom": "^24.0.0",
    "postcss": "^8.4.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "supertest": "^7.0.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vitest": "^1.5.0"
  },
  "jest": {
    "testEnvironment": "node",
    "testMatch": ["**/tests/server/**/*.test.js"]
  }
}
```

Note: `"client": "vite client --port 3002"` intentionally passes `client` as the Vite root argument so Vite uses `client/` as its project root. This differs from the spec's `vite --port 3002` which would run from `tools/asset-manager/` — the plan's version is correct for this directory layout.

- [ ] **Step 2: Create `tools/asset-manager/.env.example`**

```
A1111_URL=http://localhost:7860
PORT=3001
```

- [ ] **Step 3: Create `tools/asset-manager/server/buildings.js`**

```js
const BUILDINGS = {
  residential: ['apartment', 'house', 'mansion', 'tenement'],
  commercial:  ['shop', 'office', 'mall', 'restaurant'],
  industrial:  ['factory', 'warehouse', 'power_plant', 'refinery'],
  civic:       ['park', 'school', 'hospital', 'police_station', 'fire_station', 'city_hall'],
}

const PROMPT_TEMPLATE = '((masterpiece, best quality)), <lora:Stylized_Setting_SDXL:0.7>, Isometric_Setting, simcity {building_type}, plain background'
const NEGATIVE_PROMPT = 'EasyNegative, (worst quality, low quality: 1.0)'

module.exports = { BUILDINGS, PROMPT_TEMPLATE, NEGATIVE_PROMPT }
```

- [ ] **Step 4: Create `tools/asset-manager/server/config.js`**

```js
const path = require('path')

const ASSETS_DIR = path.resolve(__dirname, '../../frontend/public/assets/buildings')
const A1111_URL = process.env.A1111_URL || 'http://localhost:7860'

module.exports = { ASSETS_DIR, A1111_URL }
```

Note: `ASSETS_DIR` points two levels up into the game's Vite public directory. If `frontend/public/` ever moves, update this path.

- [ ] **Step 5: Create `tools/asset-manager/server/index.js`**

This version mounts only the assets route (the only one implemented in this chunk). Remaining routes are added incrementally in later tasks — each route file will add itself to the app when it's created.

```js
const express = require('express')
const path = require('path')
const { ASSETS_DIR } = require('./config')

const app = express()
app.use(express.json())

// Serve game assets statically (one level up from buildings/)
app.use('/assets', express.static(path.resolve(__dirname, '../../frontend/public/assets')))

// Routes are mounted here as they are created in later tasks:
app.use('/api', require('./routes/assets'))
// app.use('/api', require('./routes/generate'))  <- Task 3
// app.use('/api', require('./routes/accept'))    <- Task 4
// app.use('/api', require('./routes/discard'))   <- Task 5

if (require.main === module) {
  const PORT = process.env.PORT || 3001
  app.listen(PORT, () => console.log(`Asset manager server on http://localhost:${PORT}`))
}

module.exports = app
```

**Important:** Uncomment each route line in `server/index.js` as you implement it in subsequent tasks.

- [ ] **Step 6: Install dependencies**

```bash
cd tools/asset-manager
npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 7: Commit scaffold**

```bash
cd tools/asset-manager
git add -A
git commit -m "feat: scaffold asset-manager tool (Express + Vite + React)"
```

---

### Task 2: /api/assets route (TDD)

**Files:**
- Create: `tools/asset-manager/tests/server/assets.test.js`
- Create: `tools/asset-manager/server/routes/assets.js`

- [ ] **Step 1: Create test file `tools/asset-manager/tests/server/assets.test.js`**

```js
const request = require('supertest')
const fs = require('fs')
const app = require('../../server/index')

jest.mock('fs')

describe('GET /api/assets', () => {
  beforeEach(() => {
    fs.existsSync.mockReset()
  })

  test('returns ready when final PNG exists', async () => {
    fs.existsSync.mockImplementation((p) => p.endsWith('apartment.png') && !p.includes('preview'))
    const res = await request(app).get('/api/assets')
    expect(res.status).toBe(200)
    expect(res.body.residential.apartment).toBe('ready')
  })

  test('returns preview when only preview PNG exists', async () => {
    fs.existsSync.mockImplementation((p) => p.endsWith('apartment_preview.png'))
    const res = await request(app).get('/api/assets')
    expect(res.status).toBe(200)
    expect(res.body.residential.apartment).toBe('preview')
  })

  test('returns missing when neither PNG exists', async () => {
    fs.existsSync.mockReturnValue(false)
    const res = await request(app).get('/api/assets')
    expect(res.status).toBe(200)
    expect(res.body.residential.apartment).toBe('missing')
  })

  test('returns all categories in the taxonomy', async () => {
    fs.existsSync.mockReturnValue(false)
    const res = await request(app).get('/api/assets')
    expect(res.status).toBe(200)
    expect(Object.keys(res.body)).toEqual(['residential', 'commercial', 'industrial', 'civic'])
  })

  test('final PNG takes priority over preview PNG', async () => {
    // Both files exist — should return 'ready', not 'preview'
    fs.existsSync.mockReturnValue(true)
    const res = await request(app).get('/api/assets')
    expect(res.body.residential.apartment).toBe('ready')
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd tools/asset-manager
npx jest tests/server/assets.test.js --no-coverage
```

Expected: FAIL — `Cannot find module '../../server/routes/assets'`

- [ ] **Step 3: Create `tools/asset-manager/server/routes/assets.js`**

```js
const express = require('express')
const fs = require('fs')
const path = require('path')
const { BUILDINGS } = require('../buildings')
const { ASSETS_DIR } = require('../config')

const router = express.Router()

router.get('/assets', (req, res) => {
  const result = {}
  for (const [category, types] of Object.entries(BUILDINGS)) {
    result[category] = {}
    for (const type of types) {
      const finalPath = path.join(ASSETS_DIR, category, `${type}.png`)
      const previewPath = path.join(ASSETS_DIR, category, `${type}_preview.png`)
      if (fs.existsSync(finalPath)) {
        result[category][type] = 'ready'
      } else if (fs.existsSync(previewPath)) {
        result[category][type] = 'preview'
      } else {
        result[category][type] = 'missing'
      }
    }
  }
  res.json(result)
})

module.exports = router
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd tools/asset-manager
npx jest tests/server/assets.test.js --no-coverage
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/asset-manager/
git commit -m "feat: implement /api/assets route with ready/preview/missing status"
```

---

## Chunk 2: Generation Pipeline (Server)

### Task 3: /api/generate route (TDD)

**Files:**
- Create: `tools/asset-manager/tests/server/generate.test.js`
- Create: `tools/asset-manager/server/routes/generate.js`

- [ ] **Step 1: Create `tools/asset-manager/tests/server/generate.test.js`**

```js
const request = require('supertest')
const app = require('../../server/index')

// Mock all external dependencies
jest.mock('axios')
jest.mock('@imgly/background-removal-node')
jest.mock('fs/promises')

const axios = require('axios')
const { removeBackground } = require('@imgly/background-removal-node')
const fs = require('fs/promises')

const validBody = {
  building_type: 'apartment',
  category: 'residential',
  prompt: '((masterpiece)), simcity apartment, plain background',
  negative_prompt: 'EasyNegative',
}

describe('POST /api/generate', () => {
  beforeEach(() => {
    jest.clearAllMocks()

    // A1111 returns a base64 image
    axios.post.mockResolvedValue({
      data: { images: [Buffer.from('fake-image').toString('base64')] },
    })

    // Background removal returns a Blob-like object
    const fakeArrayBuffer = new ArrayBuffer(8)
    const fakeBlob = { arrayBuffer: () => Promise.resolve(fakeArrayBuffer) }
    removeBackground.mockResolvedValue(fakeBlob)

    fs.mkdir.mockResolvedValue(undefined)
    fs.writeFile.mockResolvedValue(undefined)
  })

  test('returns 200 with previewUrl on success', async () => {
    const res = await request(app).post('/api/generate').send(validBody)
    expect(res.status).toBe(200)
    expect(res.body.previewUrl).toBe('/assets/buildings/residential/apartment_preview.png')
  })

  test('calls A1111 with correct payload', async () => {
    await request(app).post('/api/generate').send(validBody)
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/sdapi/v1/txt2img'),
      expect.objectContaining({
        prompt: validBody.prompt,
        negative_prompt: validBody.negative_prompt,
        width: 512,
        height: 512,
        steps: 30,
        cfg_scale: 7.5,
        sampler_name: 'DPM++ 2M Karras',
        seed: -1,
      })
    )
  })

  test('passes buffer.buffer (ArrayBuffer) to removeBackground', async () => {
    await request(app).post('/api/generate').send(validBody)
    const arg = removeBackground.mock.calls[0][0]
    expect(arg).toBeInstanceOf(ArrayBuffer)
  })

  test('returns 409 if the same building is already generating', async () => {
    // First request hangs; second should 409 immediately
    let resolveFirst
    axios.post.mockReturnValueOnce(new Promise((res) => { resolveFirst = res }))

    const first = request(app).post('/api/generate').send(validBody)
    // Give event loop a tick for first request to register
    await new Promise((r) => setTimeout(r, 10))

    const second = await request(app).post('/api/generate').send(validBody)
    expect(second.status).toBe(409)
    expect(second.body.error).toMatch(/in progress/)

    // Clean up hanging request
    resolveFirst({ data: { images: [Buffer.from('').toString('base64')] } })
    await first
  })

  test('returns 502 when A1111 is unreachable (ECONNREFUSED)', async () => {
    const err = new Error('connect ECONNREFUSED')
    err.code = 'ECONNREFUSED'
    axios.post.mockRejectedValue(err)
    const res = await request(app).post('/api/generate').send(validBody)
    expect(res.status).toBe(502)
    expect(res.body.error).toBe('A1111 unreachable')
  })

  test('returns 500 on unexpected error', async () => {
    axios.post.mockRejectedValue(new Error('unexpected'))
    const res = await request(app).post('/api/generate').send(validBody)
    expect(res.status).toBe(500)
    expect(res.body.error).toBe('Generation failed')
  })

  test('removes building from in-flight set after completion', async () => {
    await request(app).post('/api/generate').send(validBody)
    // Second request should succeed (not 409)
    const res = await request(app).post('/api/generate').send(validBody)
    expect(res.status).toBe(200)
  })

  test('removes building from in-flight set after error', async () => {
    axios.post.mockRejectedValueOnce(new Error('fail'))
    await request(app).post('/api/generate').send(validBody)
    // Second request should not 409
    axios.post.mockResolvedValueOnce({
      data: { images: [Buffer.from('img').toString('base64')] },
    })
    const res = await request(app).post('/api/generate').send(validBody)
    expect(res.status).toBe(200)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/asset-manager
npx jest tests/server/generate.test.js --no-coverage
```

Expected: FAIL — `Cannot find module '../../server/routes/generate'`

- [ ] **Step 3: Create `tools/asset-manager/server/routes/generate.js`**

```js
const express = require('express')
const axios = require('axios')
const fs = require('fs/promises')
const path = require('path')
const { removeBackground } = require('@imgly/background-removal-node')
const { ASSETS_DIR, A1111_URL } = require('../config')

const router = express.Router()
const inFlight = new Set()

router.post('/generate', async (req, res) => {
  const { building_type, category, prompt, negative_prompt } = req.body
  const key = `${category}/${building_type}`

  if (inFlight.has(key)) {
    return res.status(409).json({ error: 'Generation already in progress for this building' })
  }

  inFlight.add(key)

  try {
    const response = await axios.post(`${A1111_URL}/sdapi/v1/txt2img`, {
      prompt,
      negative_prompt,
      width: 512,
      height: 512,
      steps: 30,
      cfg_scale: 7.5,
      sampler_name: 'DPM++ 2M Karras',
      seed: -1,
    })

    const base64 = response.data.images[0]
    const inputBuffer = Buffer.from(base64, 'base64')

    const blob = await removeBackground(inputBuffer.buffer)
    const arrayBuffer = await blob.arrayBuffer()
    const outputBuffer = Buffer.from(arrayBuffer)

    const dir = path.join(ASSETS_DIR, category)
    await fs.mkdir(dir, { recursive: true })
    await fs.writeFile(path.join(dir, `${building_type}_preview.png`), outputBuffer)

    res.json({ previewUrl: `/assets/buildings/${category}/${building_type}_preview.png` })
  } catch (err) {
    if (err.code === 'ECONNREFUSED' || (err.response && err.response.status >= 500)) {
      res.status(502).json({ error: 'A1111 unreachable' })
    } else {
      res.status(500).json({ error: 'Generation failed', detail: err.message })
    }
  } finally {
    inFlight.delete(key)
  }
})

module.exports = router
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd tools/asset-manager
npx jest tests/server/generate.test.js --no-coverage
```

Expected: 8 tests PASS

- [ ] **Step 5: Uncomment the generate route in `server/index.js`**

Remove the comment from: `// app.use('/api', require('./routes/generate'))  <- Task 3`

- [ ] **Step 6: Commit**

```bash
git add tools/asset-manager/
git commit -m "feat: implement /api/generate route with A1111 + background removal"
```

---

### Task 4: /api/accept route (TDD)

**Files:**
- Create: `tools/asset-manager/tests/server/accept.test.js`
- Create: `tools/asset-manager/server/routes/accept.js`

- [ ] **Step 1: Create `tools/asset-manager/tests/server/accept.test.js`**

```js
const request = require('supertest')
const app = require('../../server/index')

jest.mock('fs/promises')
const fs = require('fs/promises')

describe('POST /api/accept', () => {
  const body = { building_type: 'apartment', category: 'residential' }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('returns 200 with finalUrl when preview exists', async () => {
    fs.access.mockResolvedValue(undefined)
    fs.rename.mockResolvedValue(undefined)
    const res = await request(app).post('/api/accept').send(body)
    expect(res.status).toBe(200)
    expect(res.body.finalUrl).toBe('/assets/buildings/residential/apartment.png')
  })

  test('renames _preview.png to the final filename', async () => {
    fs.access.mockResolvedValue(undefined)
    fs.rename.mockResolvedValue(undefined)
    await request(app).post('/api/accept').send(body)
    expect(fs.rename).toHaveBeenCalledWith(
      expect.stringContaining('apartment_preview.png'),
      expect.stringContaining('apartment.png')
    )
    // Confirm the final path does NOT contain "preview"
    const [, finalArg] = fs.rename.mock.calls[0]
    expect(finalArg).not.toContain('preview')
  })

  test('returns 404 when no preview file exists', async () => {
    fs.access.mockRejectedValue(new Error('ENOENT'))
    const res = await request(app).post('/api/accept').send(body)
    expect(res.status).toBe(404)
    expect(res.body.error).toBe('No preview found')
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx jest tests/server/accept.test.js --no-coverage
```

Expected: FAIL — `Cannot find module '../../server/routes/accept'`

- [ ] **Step 3: Create `tools/asset-manager/server/routes/accept.js`**

```js
const express = require('express')
const fs = require('fs/promises')
const path = require('path')
const { ASSETS_DIR } = require('../config')

const router = express.Router()

router.post('/accept', async (req, res) => {
  const { building_type, category } = req.body
  const dir = path.join(ASSETS_DIR, category)
  const previewPath = path.join(dir, `${building_type}_preview.png`)
  const finalPath = path.join(dir, `${building_type}.png`)

  try {
    await fs.access(previewPath)
  } catch {
    return res.status(404).json({ error: 'No preview found' })
  }

  await fs.rename(previewPath, finalPath)
  res.json({ finalUrl: `/assets/buildings/${category}/${building_type}.png` })
})

module.exports = router
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
npx jest tests/server/accept.test.js --no-coverage
```

Expected: 3 tests PASS

- [ ] **Step 5: Uncomment the accept route in `server/index.js`**

Remove the comment from: `// app.use('/api', require('./routes/accept'))    <- Task 4`

- [ ] **Step 6: Commit**

```bash
git add tools/asset-manager/
git commit -m "feat: implement /api/accept route"
```

---

### Task 5: /api/discard route (TDD)

**Files:**
- Create: `tools/asset-manager/tests/server/discard.test.js`
- Create: `tools/asset-manager/server/routes/discard.js`

- [ ] **Step 1: Create `tools/asset-manager/tests/server/discard.test.js`**

```js
const request = require('supertest')
const app = require('../../server/index')

jest.mock('fs/promises')
const fs = require('fs/promises')

describe('POST /api/discard', () => {
  const body = { building_type: 'apartment', category: 'residential' }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('returns 204 when preview is deleted', async () => {
    fs.access.mockResolvedValue(undefined)
    fs.unlink.mockResolvedValue(undefined)
    const res = await request(app).post('/api/discard').send(body)
    expect(res.status).toBe(204)
  })

  test('deletes the preview file', async () => {
    fs.access.mockResolvedValue(undefined)
    fs.unlink.mockResolvedValue(undefined)
    await request(app).post('/api/discard').send(body)
    expect(fs.unlink).toHaveBeenCalledWith(
      expect.stringContaining('apartment_preview.png')
    )
  })

  test('returns 404 when no preview exists', async () => {
    fs.access.mockRejectedValue(new Error('ENOENT'))
    const res = await request(app).post('/api/discard').send(body)
    expect(res.status).toBe(404)
    expect(res.body.error).toBe('No preview found')
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx jest tests/server/discard.test.js --no-coverage
```

Expected: FAIL

- [ ] **Step 3: Create `tools/asset-manager/server/routes/discard.js`**

```js
const express = require('express')
const fs = require('fs/promises')
const path = require('path')
const { ASSETS_DIR } = require('../config')

const router = express.Router()

router.post('/discard', async (req, res) => {
  const { building_type, category } = req.body
  const previewPath = path.join(ASSETS_DIR, category, `${building_type}_preview.png`)

  try {
    await fs.access(previewPath)
  } catch {
    return res.status(404).json({ error: 'No preview found' })
  }

  await fs.unlink(previewPath)
  res.sendStatus(204)
})

module.exports = router
```

- [ ] **Step 4: Uncomment the discard route in `server/index.js`**

Remove the comment from: `// app.use('/api', require('./routes/discard'))   <- Task 5`

- [ ] **Step 5: Run all server tests**

```bash
npx jest tests/server/ --no-coverage
```

Expected: All tests PASS (assets, generate, accept, discard)

- [ ] **Step 6: Commit**

```bash
git add tools/asset-manager/
git commit -m "feat: implement /api/discard route — complete server API"
```

---

## Chunk 3: Client Scaffold + useAssets + Sidebar

### Task 6: Client scaffold

**Files:**
- Create: `tools/asset-manager/client/index.html`
- Create: `tools/asset-manager/client/vite.config.ts`
- Create: `tools/asset-manager/client/tsconfig.json`
- Create: `tools/asset-manager/client/src/types.ts`
- Create: `tools/asset-manager/client/src/App.tsx`
- Create: `tools/asset-manager/client/src/main.tsx`
- Create: `tools/asset-manager/client/src/index.css`
- Create: `tools/asset-manager/client/tailwind.config.js`
- Create: `tools/asset-manager/client/postcss.config.js`

- [ ] **Step 1: Create `tools/asset-manager/client/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SimulationCity Asset Manager</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Create `tools/asset-manager/client/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  root: 'client',
  server: {
    port: 3002,
    proxy: {
      '/api': 'http://localhost:3001',
      '/assets': 'http://localhost:3001',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

- [ ] **Step 3: Create `tools/asset-manager/client/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `tools/asset-manager/client/src/types.ts`**

```ts
export type AssetStatus = 'ready' | 'preview' | 'missing'

export interface AssetMap {
  [category: string]: {
    [buildingType: string]: AssetStatus
  }
}

export type DrawerState = 'idle' | 'generating' | 'preview' | 'accepted' | 'discarded' | 'failed'

export interface SelectedBuilding {
  category: string
  buildingType: string
}
```

- [ ] **Step 5: Create `tools/asset-manager/client/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #0f0f1a;
  color: #e2e2e2;
}
```

- [ ] **Step 6: Create `tools/asset-manager/client/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 7: Create `tools/asset-manager/client/postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 8: Create `tools/asset-manager/client/src/test-setup.ts`**

```ts
import '@testing-library/jest-dom'
```

- [ ] **Step 9: Create `tools/asset-manager/client/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

- [ ] **Step 10: Create skeleton `tools/asset-manager/client/src/App.tsx`**

```tsx
import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import BuildingGrid from './components/BuildingGrid'
import RegenDrawer from './components/RegenDrawer'
import { useAssets } from './hooks/useAssets'
import { SelectedBuilding } from './types'

export default function App() {
  const [activeCategory, setActiveCategory] = useState('residential')
  const [selected, setSelected] = useState<SelectedBuilding | null>(null)
  const { assets, reload } = useAssets()

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar activeCategory={activeCategory} onSelect={setActiveCategory} />
      <BuildingGrid
        category={activeCategory}
        assets={assets}
        onSelectBuilding={(buildingType) =>
          setSelected({ category: activeCategory, buildingType })
        }
      />
      {selected && (
        <RegenDrawer
          selected={selected}
          assets={assets}
          onClose={() => setSelected(null)}
          onAccepted={reload}
          onDiscarded={reload}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 11: Commit scaffold**

```bash
git add tools/asset-manager/client/
git commit -m "feat: scaffold React client (Vite, TypeScript, Tailwind)"
```

---

### Task 7: useAssets hook (TDD)

**Files:**
- Create: `tools/asset-manager/client/src/hooks/useAssets.ts`
- Create: `tools/asset-manager/client/src/hooks/useAssets.test.ts`

- [ ] **Step 1: Create `tools/asset-manager/client/src/hooks/useAssets.test.ts`**

```ts
import { renderHook, waitFor } from '@testing-library/react'
import { vi, describe, test, expect, beforeEach } from 'vitest'
import { useAssets } from './useAssets'

describe('useAssets', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('fetches /api/assets and returns the asset map', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ residential: { apartment: 'ready' } }),
    } as Response)

    const { result } = renderHook(() => useAssets())

    await waitFor(() => {
      expect(result.current.assets).toEqual({ residential: { apartment: 'ready' } })
    })
  })

  test('starts with empty assets', () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {})) // never resolves
    const { result } = renderHook(() => useAssets())
    expect(result.current.assets).toEqual({})
  })

  test('reload re-fetches the asset map', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ residential: { apartment: 'missing' } }),
    } as Response)

    const { result } = renderHook(() => useAssets())
    await waitFor(() => expect(result.current.assets).not.toEqual({}))

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ residential: { apartment: 'ready' } }),
    } as Response)

    result.current.reload()
    await waitFor(() => {
      expect(result.current.assets.residential?.apartment).toBe('ready')
    })
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd tools/asset-manager
npx vitest run client/src/hooks/useAssets.test.ts
```

Expected: FAIL — `Cannot find module './useAssets'`

- [ ] **Step 3: Create `tools/asset-manager/client/src/hooks/useAssets.ts`**

```ts
import { useState, useEffect, useCallback } from 'react'
import { AssetMap } from '../types'

export function useAssets() {
  const [assets, setAssets] = useState<AssetMap>({})

  const fetchAssets = useCallback(async () => {
    const res = await fetch('/api/assets')
    const data = await res.json()
    setAssets(data)
  }, [])

  useEffect(() => {
    fetchAssets()
  }, [fetchAssets])

  return { assets, reload: fetchAssets }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
npx vitest run client/src/hooks/useAssets.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/asset-manager/client/src/hooks/
git commit -m "feat: implement useAssets hook"
```

---

### Task 8: Sidebar component (TDD)

**Files:**
- Create: `tools/asset-manager/client/src/components/Sidebar.tsx`
- Create: `tools/asset-manager/client/src/components/Sidebar.test.tsx`

- [ ] **Step 1: Create `tools/asset-manager/client/src/components/Sidebar.test.tsx`**

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'
import Sidebar from './Sidebar'

describe('Sidebar', () => {
  const categories = ['residential', 'commercial', 'industrial', 'civic']

  test('renders all four categories', () => {
    render(<Sidebar activeCategory="residential" onSelect={vi.fn()} />)
    categories.forEach((cat) => {
      expect(screen.getByText(new RegExp(cat, 'i'))).toBeInTheDocument()
    })
  })

  test('highlights the active category', () => {
    render(<Sidebar activeCategory="industrial" onSelect={vi.fn()} />)
    const active = screen.getByRole('button', { name: /industrial/i })
    expect(active).toHaveClass('bg-indigo-600')
  })

  test('calls onSelect with the category name when clicked', () => {
    const onSelect = vi.fn()
    render(<Sidebar activeCategory="residential" onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /commercial/i }))
    expect(onSelect).toHaveBeenCalledWith('commercial')
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx vitest run client/src/components/Sidebar.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Create `tools/asset-manager/client/src/components/Sidebar.tsx`**

```tsx
import React from 'react'

const CATEGORIES = [
  { id: 'residential', label: '🏠 Residential' },
  { id: 'commercial',  label: '🏪 Commercial'  },
  { id: 'industrial',  label: '🏭 Industrial'  },
  { id: 'civic',       label: '🏛️ Civic'       },
]

interface Props {
  activeCategory: string
  onSelect: (category: string) => void
}

export default function Sidebar({ activeCategory, onSelect }: Props) {
  return (
    <aside className="w-44 flex-shrink-0 bg-gray-900 border-r border-gray-700 p-3">
      <p className="text-xs text-gray-500 uppercase tracking-widest mb-3">Categories</p>
      {CATEGORIES.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onSelect(id)}
          className={`w-full text-left px-3 py-2 rounded text-sm mb-1 transition-colors ${
            id === activeCategory
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:text-white hover:bg-gray-800'
          }`}
        >
          {label}
        </button>
      ))}
    </aside>
  )
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
npx vitest run client/src/components/Sidebar.test.tsx
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/asset-manager/client/src/components/Sidebar.tsx \
        tools/asset-manager/client/src/components/Sidebar.test.tsx
git commit -m "feat: implement Sidebar component"
```

---

## Chunk 4: BuildingCard, BuildingGrid, useGenerate, RegenDrawer, App wiring

### Task 9: BuildingCard component (TDD)

**Files:**
- Create: `tools/asset-manager/client/src/components/BuildingCard.tsx`
- Create: `tools/asset-manager/client/src/components/BuildingCard.test.tsx`

- [ ] **Step 1: Create `tools/asset-manager/client/src/components/BuildingCard.test.tsx`**

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'
import BuildingCard from './BuildingCard'

describe('BuildingCard', () => {
  const base = { buildingType: 'apartment', category: 'residential', onSelect: vi.fn() }

  test('shows green Generated badge when status is ready', () => {
    render(<BuildingCard {...base} status="ready" />)
    expect(screen.getByText(/generated/i)).toHaveClass('text-green-400')
  })

  test('shows amber Preview badge when status is preview', () => {
    render(<BuildingCard {...base} status="preview" />)
    expect(screen.getByText(/preview/i)).toHaveClass('text-amber-400')
  })

  test('shows red Missing badge when status is missing', () => {
    render(<BuildingCard {...base} status="missing" />)
    expect(screen.getByText(/missing/i)).toHaveClass('text-red-400')
  })

  test('renders a thumbnail img when status is ready', () => {
    render(<BuildingCard {...base} status="ready" />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', '/assets/buildings/residential/apartment.png')
  })

  test('renders a thumbnail img when status is preview', () => {
    render(<BuildingCard {...base} status="preview" />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', '/assets/buildings/residential/apartment_preview.png')
  })

  test('calls onSelect with buildingType when clicked', () => {
    const onSelect = vi.fn()
    render(<BuildingCard {...base} status="missing" onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onSelect).toHaveBeenCalledWith('apartment')
  })

  test('displays a human-readable building name', () => {
    render(<BuildingCard {...base} status="missing" buildingType="power_plant" />)
    expect(screen.getByText(/power plant/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx vitest run client/src/components/BuildingCard.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Create `tools/asset-manager/client/src/components/BuildingCard.tsx`**

```tsx
import React from 'react'
import { AssetStatus } from '../types'

interface Props {
  buildingType: string
  category: string
  status: AssetStatus
  onSelect: (buildingType: string) => void
}

function humanize(type: string) {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const STATUS_CONFIG: Record<AssetStatus, { label: string; className: string }> = {
  ready:   { label: 'Generated', className: 'text-green-400' },
  preview: { label: 'Preview',   className: 'text-amber-400' },
  missing: { label: 'Missing',   className: 'text-red-400'   },
}

export default function BuildingCard({ buildingType, category, status, onSelect }: Props) {
  const { label, className } = STATUS_CONFIG[status]

  const imgSrc =
    status === 'ready'
      ? `/assets/buildings/${category}/${buildingType}.png`
      : status === 'preview'
      ? `/assets/buildings/${category}/${buildingType}_preview.png`
      : null

  return (
    <button
      onClick={() => onSelect(buildingType)}
      className="bg-gray-800 border border-gray-700 hover:border-indigo-500 rounded-lg p-3 text-center transition-colors w-full"
    >
      <div className="h-20 bg-gray-900 rounded mb-2 flex items-center justify-center overflow-hidden">
        {imgSrc ? (
          <img src={imgSrc} alt={humanize(buildingType)} className="max-h-full max-w-full object-contain" />
        ) : (
          <span className="text-3xl">🏗️</span>
        )}
      </div>
      <p className="text-xs text-gray-300 mb-1">{humanize(buildingType)}</p>
      <p className={`text-xs font-medium ${className}`}>{label}</p>
    </button>
  )
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
npx vitest run client/src/components/BuildingCard.test.tsx
```

Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/asset-manager/client/src/components/BuildingCard.tsx \
        tools/asset-manager/client/src/components/BuildingCard.test.tsx
git commit -m "feat: implement BuildingCard component"
```

---

### Task 10: BuildingGrid component (TDD)

**Files:**
- Create: `tools/asset-manager/client/src/components/BuildingGrid.tsx`
- Create: `tools/asset-manager/client/src/components/BuildingGrid.test.tsx`

- [ ] **Step 1: Create `tools/asset-manager/client/src/components/BuildingGrid.test.tsx`**

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'
import BuildingGrid from './BuildingGrid'
import { AssetMap } from '../types'

const assets: AssetMap = {
  residential: {
    apartment: 'ready',
    house: 'missing',
    mansion: 'preview',
    tenement: 'missing',
  },
}

describe('BuildingGrid', () => {
  test('renders a card for each building in the active category', () => {
    render(
      <BuildingGrid category="residential" assets={assets} onSelectBuilding={vi.fn()} />
    )
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })

  test('passes the correct status to each card', () => {
    render(
      <BuildingGrid category="residential" assets={assets} onSelectBuilding={vi.fn()} />
    )
    expect(screen.getByText(/generated/i)).toBeInTheDocument()
    expect(screen.getAllByText(/missing/i)).toHaveLength(2)
    expect(screen.getByText(/preview/i)).toBeInTheDocument()
  })

  test('calls onSelectBuilding with the building type when a card is clicked', () => {
    const onSelect = vi.fn()
    render(
      <BuildingGrid category="residential" assets={assets} onSelectBuilding={onSelect} />
    )
    fireEvent.click(screen.getByText(/apartment/i).closest('button')!)
    expect(onSelect).toHaveBeenCalledWith('apartment')
  })

  test('renders nothing when category has no assets', () => {
    render(
      <BuildingGrid category="residential" assets={{}} onSelectBuilding={vi.fn()} />
    )
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx vitest run client/src/components/BuildingGrid.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Create `tools/asset-manager/client/src/components/BuildingGrid.tsx`**

```tsx
import React from 'react'
import BuildingCard from './BuildingCard'
import { AssetMap } from '../types'

interface Props {
  category: string
  assets: AssetMap
  onSelectBuilding: (buildingType: string) => void
}

export default function BuildingGrid({ category, assets, onSelectBuilding }: Props) {
  const buildings = assets[category] ?? {}

  return (
    <main className="flex-1 overflow-y-auto p-4">
      <p className="text-xs text-gray-500 uppercase tracking-widest mb-4">
        {category.charAt(0).toUpperCase() + category.slice(1)} Buildings
      </p>
      <div className="grid grid-cols-3 gap-3">
        {Object.entries(buildings).map(([buildingType, status]) => (
          <BuildingCard
            key={buildingType}
            buildingType={buildingType}
            category={category}
            status={status}
            onSelect={onSelectBuilding}
          />
        ))}
      </div>
    </main>
  )
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
npx vitest run client/src/components/BuildingGrid.test.tsx
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/asset-manager/client/src/components/BuildingGrid.tsx \
        tools/asset-manager/client/src/components/BuildingGrid.test.tsx
git commit -m "feat: implement BuildingGrid component"
```

---

### Task 11: useGenerate hook (TDD)

**Files:**
- Create: `tools/asset-manager/client/src/hooks/useGenerate.ts`
- Create: `tools/asset-manager/client/src/hooks/useGenerate.test.ts`

- [ ] **Step 1: Create `tools/asset-manager/client/src/hooks/useGenerate.test.ts`**

```ts
import { renderHook, act } from '@testing-library/react'
import { vi, describe, test, expect, beforeEach } from 'vitest'
import { useGenerate } from './useGenerate'

describe('useGenerate', () => {
  const selected = { category: 'residential', buildingType: 'apartment' }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('starts in idle state', () => {
    const { result } = renderHook(() => useGenerate(selected))
    expect(result.current.drawerState).toBe('idle')
    expect(result.current.previewUrl).toBeNull()
  })

  test('transitions to generating then preview on successful generate', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ previewUrl: '/assets/buildings/residential/apartment_preview.png' }),
    } as Response)

    const { result } = renderHook(() => useGenerate(selected))
    await act(async () => {
      await result.current.generate('my prompt', 'my negative')
    })

    expect(result.current.drawerState).toBe('preview')
    expect(result.current.previewUrl).toBe('/assets/buildings/residential/apartment_preview.png')
  })

  test('transitions to failed state on error', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: 'A1111 unreachable' }),
    } as Response)

    const { result } = renderHook(() => useGenerate(selected))
    await act(async () => {
      await result.current.generate('prompt', 'neg')
    })

    expect(result.current.drawerState).toBe('failed')
    expect(result.current.errorMessage).toBe('A1111 unreachable')
  })

  test('accept posts /api/accept and transitions to accepted', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ finalUrl: '/assets/buildings/residential/apartment.png' }),
    } as Response)

    const { result } = renderHook(() => useGenerate(selected))
    await act(async () => { await result.current.accept() })

    expect(global.fetch).toHaveBeenCalledWith('/api/accept', expect.objectContaining({ method: 'POST' }))
    expect(result.current.drawerState).toBe('accepted')
  })

  test('discard posts /api/discard and transitions to discarded', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useGenerate(selected))
    await act(async () => { await result.current.discard() })

    expect(global.fetch).toHaveBeenCalledWith('/api/discard', expect.objectContaining({ method: 'POST' }))
    expect(result.current.drawerState).toBe('discarded')
  })

  test('resets to idle when selected building changes', async () => {
    const { result, rerender } = renderHook(
      (props) => useGenerate(props),
      { initialProps: selected }
    )

    // Simulate a completed state
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ previewUrl: '/preview.png' }),
    } as Response)
    await act(async () => { await result.current.generate('p', 'n') })
    expect(result.current.drawerState).toBe('preview')

    // Switch to a different building
    rerender({ category: 'commercial', buildingType: 'shop' })
    expect(result.current.drawerState).toBe('idle')
    expect(result.current.previewUrl).toBeNull()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx vitest run client/src/hooks/useGenerate.test.ts
```

Expected: FAIL

- [ ] **Step 3: Create `tools/asset-manager/client/src/hooks/useGenerate.ts`**

```ts
import { useState, useEffect } from 'react'
import { DrawerState, SelectedBuilding } from '../types'

interface UseGenerateResult {
  drawerState: DrawerState
  previewUrl: string | null
  errorMessage: string | null
  generate: (prompt: string, negativePrompt: string) => Promise<void>
  accept: () => Promise<void>
  discard: () => Promise<void>
}

export function useGenerate(selected: SelectedBuilding): UseGenerateResult {
  const [drawerState, setDrawerState] = useState<DrawerState>('idle')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Reset when selected building changes
  useEffect(() => {
    setDrawerState('idle')
    setPreviewUrl(null)
    setErrorMessage(null)
  }, [selected.category, selected.buildingType])

  async function generate(prompt: string, negativePrompt: string) {
    setDrawerState('generating')
    setErrorMessage(null)
    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          building_type: selected.buildingType,
          category: selected.category,
          prompt,
          negative_prompt: negativePrompt,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setErrorMessage(data.error ?? 'Generation failed')
        setDrawerState('failed')
        return
      }
      setPreviewUrl(data.previewUrl)
      setDrawerState('preview')
    } catch {
      setErrorMessage('Network error')
      setDrawerState('failed')
    }
  }

  async function accept() {
    await fetch('/api/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        building_type: selected.buildingType,
        category: selected.category,
      }),
    })
    setDrawerState('accepted')
  }

  async function discard() {
    await fetch('/api/discard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        building_type: selected.buildingType,
        category: selected.category,
      }),
    })
    setDrawerState('discarded')
  }

  return { drawerState, previewUrl, errorMessage, generate, accept, discard }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
npx vitest run client/src/hooks/useGenerate.test.ts
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/asset-manager/client/src/hooks/useGenerate.ts \
        tools/asset-manager/client/src/hooks/useGenerate.test.ts
git commit -m "feat: implement useGenerate hook"
```

---

### Task 12: RegenDrawer component (TDD)

**Files:**
- Create: `tools/asset-manager/client/src/components/RegenDrawer.tsx`
- Create: `tools/asset-manager/client/src/components/RegenDrawer.test.tsx`

- [ ] **Step 1: Create `tools/asset-manager/client/src/components/RegenDrawer.test.tsx`**

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, test, expect, beforeEach } from 'vitest'
import RegenDrawer from './RegenDrawer'
import { AssetMap } from '../types'

const assets: AssetMap = { residential: { apartment: 'ready' } }
const selected = { category: 'residential', buildingType: 'apartment' }
const baseProps = {
  selected,
  assets,
  onClose: vi.fn(),
  onAccepted: vi.fn(),
  onDiscarded: vi.fn(),
}

describe('RegenDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    global.fetch = vi.fn()
  })

  test('renders the building name', () => {
    render(<RegenDrawer {...baseProps} />)
    expect(screen.getByText(/apartment/i)).toBeInTheDocument()
  })

  test('shows the current asset image when status is ready', () => {
    render(<RegenDrawer {...baseProps} />)
    expect(screen.getByAltText(/current/i)).toHaveAttribute(
      'src',
      '/assets/buildings/residential/apartment.png'
    )
  })

  test('pre-fills prompt textarea with the template', () => {
    render(<RegenDrawer {...baseProps} />)
    const prompt = screen.getByLabelText(/prompt/i) as HTMLTextAreaElement
    expect(prompt.value).toContain('simcity apartment')
  })

  test('pre-fills negative prompt textarea', () => {
    render(<RegenDrawer {...baseProps} />)
    const neg = screen.getByLabelText(/negative/i) as HTMLTextAreaElement
    expect(neg.value).toContain('EasyNegative')
  })

  test('clicking Generate calls /api/generate', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ previewUrl: '/assets/buildings/residential/apartment_preview.png' }),
    } as Response)

    render(<RegenDrawer {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: /generate/i }))

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith('/api/generate', expect.objectContaining({ method: 'POST' }))
    )
  })

  test('shows spinner and disables Generate button while generating', async () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {})) // never resolves

    render(<RegenDrawer {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: /generate/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate/i })).toBeDisabled()
      expect(screen.getByTestId('spinner')).toBeInTheDocument()
    })
  })

  test('shows Accept and Discard buttons after successful generation', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ previewUrl: '/preview.png' }),
    } as Response)

    render(<RegenDrawer {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: /generate/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /discard/i })).toBeInTheDocument()
    })
  })

  test('shows inline error message on failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: 'A1111 unreachable' }),
    } as Response)

    render(<RegenDrawer {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: /generate/i }))

    await waitFor(() => {
      expect(screen.getByText(/A1111 unreachable/i)).toBeInTheDocument()
    })
  })

  test('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn()
    render(<RegenDrawer {...baseProps} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })

  test('calls onAccepted after accepting', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ previewUrl: '/preview.png' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ finalUrl: '/final.png' }),
      } as Response)

    const onAccepted = vi.fn()
    render(<RegenDrawer {...baseProps} onAccepted={onAccepted} />)
    fireEvent.click(screen.getByRole('button', { name: /generate/i }))

    await waitFor(() => screen.getByRole('button', { name: /accept/i }))
    fireEvent.click(screen.getByRole('button', { name: /accept/i }))

    await waitFor(() => expect(onAccepted).toHaveBeenCalled())
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
npx vitest run client/src/components/RegenDrawer.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Create `tools/asset-manager/client/src/components/RegenDrawer.tsx`**

```tsx
import React, { useState } from 'react'
import { AssetMap, SelectedBuilding } from '../types'
import { useGenerate } from '../hooks/useGenerate'
import { PROMPT_TEMPLATE, NEGATIVE_PROMPT } from '../constants'

interface Props {
  selected: SelectedBuilding
  assets: AssetMap
  onClose: () => void
  onAccepted: () => void
  onDiscarded: () => void
}

function humanize(type: string) {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function RegenDrawer({ selected, assets, onClose, onAccepted, onDiscarded }: Props) {
  const { category, buildingType } = selected
  const status = assets[category]?.[buildingType] ?? 'missing'

  const defaultPrompt = PROMPT_TEMPLATE.replace('{building_type}', buildingType.replace(/_/g, ' '))
  const [prompt, setPrompt] = useState(defaultPrompt)
  const [negPrompt, setNegPrompt] = useState(NEGATIVE_PROMPT)

  const { drawerState, previewUrl, errorMessage, generate, accept, discard } = useGenerate(selected)

  const currentSrc =
    status === 'ready' ? `/assets/buildings/${category}/${buildingType}.png`
    : status === 'preview' ? `/assets/buildings/${category}/${buildingType}_preview.png`
    : null

  async function handleAccept() {
    await accept()
    onAccepted()
  }

  async function handleDiscard() {
    await discard()
    onDiscarded()
  }

  return (
    <aside className="w-80 flex-shrink-0 bg-gray-900 border-l border-indigo-600 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <span className="text-sm font-semibold text-indigo-400">{humanize(buildingType)}</span>
        <button
          aria-label="Close"
          onClick={onClose}
          className="text-gray-400 hover:text-white text-lg leading-none"
        >
          ✕
        </button>
      </div>

      {/* Current image */}
      <div className="px-4 pt-4">
        <p className="text-xs text-gray-500 mb-1">Current</p>
        <div className="h-32 bg-gray-800 rounded flex items-center justify-center mb-4">
          {currentSrc ? (
            <img src={currentSrc} alt="current" className="max-h-full max-w-full object-contain" />
          ) : (
            <span className="text-3xl">🏗️</span>
          )}
        </div>

        {/* Preview image (after generation) */}
        {previewUrl && (
          <>
            <p className="text-xs text-gray-500 mb-1">New</p>
            <div className="h-32 bg-gray-800 rounded flex items-center justify-center mb-4">
              <img src={previewUrl} alt="preview" className="max-h-full max-w-full object-contain" />
            </div>
          </>
        )}
      </div>

      {/* Prompts */}
      <div className="px-4 flex-1 overflow-y-auto">
        <label className="block text-xs text-gray-500 mb-1" htmlFor="prompt">Prompt</label>
        <textarea
          id="prompt"
          aria-label="prompt"
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={drawerState === 'generating'}
          className="w-full bg-gray-950 border border-gray-700 rounded p-2 text-xs text-gray-300 font-mono resize-none mb-3 disabled:opacity-50"
        />

        <label className="block text-xs text-gray-500 mb-1" htmlFor="neg-prompt">Negative Prompt</label>
        <textarea
          id="neg-prompt"
          aria-label="negative prompt"
          rows={2}
          value={negPrompt}
          onChange={(e) => setNegPrompt(e.target.value)}
          disabled={drawerState === 'generating'}
          className="w-full bg-gray-950 border border-gray-700 rounded p-2 text-xs text-gray-300 font-mono resize-none mb-3 disabled:opacity-50"
        />

        {errorMessage && (
          <p className="text-xs text-red-400 mb-3">{errorMessage}</p>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-gray-700 flex gap-2">
        {drawerState === 'preview' ? (
          <>
            <button
              onClick={handleAccept}
              className="flex-1 bg-green-700 hover:bg-green-600 text-white text-sm py-2 rounded"
            >
              Accept
            </button>
            <button
              onClick={handleDiscard}
              className="flex-1 bg-gray-700 hover:bg-gray-600 text-white text-sm py-2 rounded"
            >
              Discard
            </button>
          </>
        ) : (
          <button
            onClick={() => generate(prompt, negPrompt)}
            disabled={drawerState === 'generating'}
            className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm py-2 rounded flex items-center justify-center gap-2"
          >
            {drawerState === 'generating' ? (
              <>
                <span data-testid="spinner" className="animate-spin">⏳</span>
                Generating…
              </>
            ) : (
              '⚡ Generate'
            )}
          </button>
        )}
      </div>
    </aside>
  )
}
```

- [ ] **Step 4: Create `tools/asset-manager/client/src/constants.ts`**

```ts
export const PROMPT_TEMPLATE =
  '((masterpiece, best quality)), <lora:Stylized_Setting_SDXL:0.7>, Isometric_Setting, simcity {building_type}, plain background'

export const NEGATIVE_PROMPT = 'EasyNegative, (worst quality, low quality: 1.0)'
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
npx vitest run client/src/components/RegenDrawer.test.tsx
```

Expected: 9 tests PASS

- [ ] **Step 6: Run all client tests**

```bash
npx vitest run client/src
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add tools/asset-manager/client/src/
git commit -m "feat: implement RegenDrawer component — client complete"
```

---

### Task 13: Wire up App.tsx + smoke test

**Files:**
- Modify: `tools/asset-manager/client/src/App.tsx` (already wired — verify it matches final component interfaces)

- [ ] **Step 1: Verify App.tsx imports match final component signatures**

Check that the imports in `App.tsx` (created in Task 6, Step 10) match:
- `Sidebar` props: `activeCategory`, `onSelect`
- `BuildingGrid` props: `category`, `assets`, `onSelectBuilding`
- `RegenDrawer` props: `selected`, `assets`, `onClose`, `onAccepted`, `onDiscarded`
- `useAssets` returns: `{ assets, reload }`

If any prop names differ from what was implemented, update `App.tsx` to match.

- [ ] **Step 2: Create `frontend/public/assets/buildings/` directory structure**

```bash
mkdir -p frontend/public/assets/buildings/residential
mkdir -p frontend/public/assets/buildings/commercial
mkdir -p frontend/public/assets/buildings/industrial
mkdir -p frontend/public/assets/buildings/civic
```

- [ ] **Step 3: Add a `.gitkeep` in each directory so they're tracked**

```bash
touch frontend/public/assets/buildings/residential/.gitkeep
touch frontend/public/assets/buildings/commercial/.gitkeep
touch frontend/public/assets/buildings/industrial/.gitkeep
touch frontend/public/assets/buildings/civic/.gitkeep
```

- [ ] **Step 4: TypeScript type-check the client**

```bash
cd tools/asset-manager/client
npx tsc --noEmit
```

Expected: Zero errors. If prop mismatches exist between App.tsx and the components, they will surface here. Fix any reported errors before proceeding.

- [ ] **Step 5: Run all tests one final time**

```bash
cd tools/asset-manager
npx jest tests/server/ --no-coverage
npx vitest run client/src
```

Expected: All server and client tests PASS

- [ ] **Step 6: Manual smoke test**

Start A1111 with `--api`, then:

```bash
cd tools/asset-manager
npm run dev
```

Open `http://localhost:3002`. Verify:
- Sidebar shows 4 categories
- Clicking a category loads building cards
- All cards show "Missing" (no assets generated yet)
- Clicking a card opens the drawer
- Prompt is pre-filled with the correct building type
- Clicking Generate triggers A1111 → background removal → preview image shown
- Accept saves to `frontend/public/assets/buildings/{category}/{type}.png`
- Card shows "Generated" after reload

- [ ] **Step 7: Final commit**

```bash
git add frontend/public/assets/buildings/
git add tools/asset-manager/
git commit -m "feat: complete asset manager tool — ready for artwork generation"
```
