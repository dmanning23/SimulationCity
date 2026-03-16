# SimulationCity - Premium Features: AI-Generated Building Assets

## Overview

Premium subscribers can generate custom building sprites for their cities using Stable Diffusion. This feature is scoped to a curated **style palette** system rather than freeform text prompts — this keeps visual consistency high, limits content moderation surface, and produces better in-game results.

---

## Feature Summary

| Feature | Free | Premium |
|---|---|---|
| Standard building sprites | ✓ | ✓ |
| City design style selection | — | ✓ |
| AI building generation | — | ✓ |
| Variants per building type | — | Up to 5 |
| Monthly generation credits | — | 100 |
| Asset gallery (saved variants) | — | ✓ |
| Style palette options | — | 3 (expandable) |

---

## Style Palette System

A **design style** is a named aesthetic applied city-wide. All AI-generated buildings in a city use the same style as a prompt modifier, ensuring visual cohesion.

Players select a style in city settings. The style is stored as `City.settings.design_style`.

### Available Styles (v1)

| Style ID | Display Name | Prompt Modifier |
|---|---|---|
| `art_deco` | Art Deco | "1920s art deco architecture, ornate geometric facades, gold accents, stepped crown" |
| `brutalist` | Brutalist | "brutalist concrete architecture, raw exposed concrete, geometric monolithic forms" |
| `cyberpunk` | Cyberpunk | "cyberpunk neon-lit urban architecture, holographic signage, dark rain-slicked surfaces" |

Additional styles are added as paid tier expansions (e.g., Medieval, Futuristic, Tropical).

---

## Generation Pipeline

### Overview

```
Player requests generation
        │
        ▼
FastAPI endpoint (POST /api/premium/generate)
  - Validate premium status
  - Deduct generation credit
  - Enqueue Celery task
        │
        ▼
Celery: sd_generation queue
  - Build full SD prompt
  - Call Replicate API (async poll)
  - Post-process image (background removal, resize to tile dimensions)
  - Upload to S3
  - Write GeneratedAsset document to MongoDB
        │
        ▼
Socket.IO: notify client
  - Emit 'asset_ready' event to player's socket session
  - Frontend shows new variant in generation modal
```

### Prompt Construction

Prompts are constructed programmatically — players never write raw prompts. This eliminates moderation risk and ensures output is always architecturally relevant.

```python
STYLE_MODIFIERS = {
    'art_deco': '1920s art deco architecture, ornate geometric facades, gold accents, stepped crown',
    'brutalist': 'brutalist concrete architecture, raw exposed concrete, geometric monolithic forms',
    'cyberpunk': 'cyberpunk neon-lit urban architecture, holographic signage, dark rain-slicked surfaces',
}

BUILDING_BASE_PROMPTS = {
    'residential_apartment': 'isometric apartment building, {style}, city building sprite, white background, pixel-perfect edges',
    'commercial_shop':       'isometric commercial shop building, {style}, city building sprite, white background, pixel-perfect edges',
    'industrial_factory':    'isometric factory building, {style}, smokestack, city building sprite, white background, pixel-perfect edges',
    'civic_park':            'isometric urban park with trees, {style}, city tile sprite, white background',
    # ... additional building types
}

NEGATIVE_PROMPT = (
    "photorealistic, photograph, people, cars, blurry, low quality, "
    "perspective distortion, top-down view, side view, watermark"
)

def build_prompt(building_type: str, style_id: str) -> tuple[str, str]:
    style_modifier = STYLE_MODIFIERS[style_id]
    base = BUILDING_BASE_PROMPTS[building_type]
    prompt = base.format(style=style_modifier)
    return prompt, NEGATIVE_PROMPT
```

### SD Model Configuration

Consistent output is critical for in-game usability. Recommended Replicate model and settings:

```python
REPLICATE_MODEL = "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37281cc453dc3ad96f31e523"

SD_CONFIG = {
    "width": 512,
    "height": 512,
    "num_inference_steps": 30,
    "guidance_scale": 7.5,
    "scheduler": "DPMSolverMultistep",
    # ControlNet depth conditioning enforces consistent isometric perspective
    "controlnet_conditioning_scale": 0.8,
}
```

**Note on visual consistency**: The isometric perspective is the hardest constraint to enforce reliably. V1 will use a fixed ControlNet depth map template per building size (1x1, 2x2, 3x3 tiles) to anchor perspective. This template library lives in `backend/workers/sd_templates/`.

---

## Data Model

### GeneratedAsset Document

```python
from beanie import Document, PydanticObjectId
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class AssetStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"

class GeneratedAsset(Document):
    player_id: PydanticObjectId
    city_id: PydanticObjectId
    building_type: str          # e.g. "residential_apartment"
    style_id: str               # e.g. "art_deco"
    prompt: str                 # Full prompt used (for debugging/reproducibility)
    s3_key: str | None = None   # S3 object key once uploaded
    s3_url: str | None = None   # Public CDN URL
    status: AssetStatus = AssetStatus.PENDING
    is_active: bool = False     # True if this variant is currently applied to buildings
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    class Settings:
        name = "generated_assets"
```

### Credit Tracking (on Player document)

```python
# Fields added to Player document (see design-document.md)
generation_credits: int = 0
credits_reset_at: datetime | None = None   # Monthly reset timestamp
```

---

## Celery Task

```python
# backend/workers/sd_generation.py
import replicate
import boto3
import io
import requests
from celery_app import celery_app
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone
from PIL import Image

s3 = boto3.client('s3')

@celery_app.task(queue='sd_generation', bind=True, max_retries=2, time_limit=120)
def generate_building_asset(self, asset_id: str):
    db = MongoClient()['simulationcity']
    asset = db.generated_assets.find_one({'_id': ObjectId(asset_id)})

    if not asset:
        return {'status': 'error', 'message': 'Asset not found'}

    try:
        # Run SD inference via Replicate
        output = replicate.run(
            REPLICATE_MODEL,
            input={
                'prompt': asset['prompt'],
                'negative_prompt': NEGATIVE_PROMPT,
                **SD_CONFIG
            }
        )

        # output is a list of image URLs from Replicate
        image_url = output[0]

        # Download, post-process, upload to S3
        img_data = requests.get(image_url).content
        img = Image.open(io.BytesIO(img_data)).convert('RGBA')
        img = remove_background(img)          # Custom background removal
        img = img.resize((128, 128))          # Normalize to tile dimensions

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        s3_key = f'assets/{asset_id}.png'
        s3.upload_fileobj(buffer, BUCKET_NAME, s3_key, ExtraArgs={'ContentType': 'image/png'})
        s3_url = f'https://{BUCKET_NAME}.s3.amazonaws.com/{s3_key}'

        db.generated_assets.update_one(
            {'_id': ObjectId(asset_id)},
            {'$set': {
                'status': 'ready',
                's3_key': s3_key,
                's3_url': s3_url,
                'completed_at': datetime.now(timezone.utc)
            }}
        )

        return {'status': 'success', 'asset_id': asset_id, 's3_url': s3_url}

    except Exception as exc:
        db.generated_assets.update_one(
            {'_id': ObjectId(asset_id)},
            {'$set': {'status': 'failed'}}
        )
        raise self.retry(exc=exc, countdown=10)
```

---

## REST API Endpoints

All premium endpoints require a valid JWT and `is_premium: true` on the player document.

```
POST   /api/premium/generate
       Body: { city_id, building_type }
       Action: Deduct 1 credit, enqueue generation task, return asset_id
       Response: { asset_id, status: "pending", credits_remaining }

GET    /api/premium/assets?city_id=&building_type=
       Action: List all GeneratedAsset docs for this player/city/type
       Response: [{ asset_id, s3_url, status, is_active, created_at }, ...]

POST   /api/premium/assets/{asset_id}/activate
       Action: Set is_active=true on this asset, false on other variants of same type
       Response: { asset_id, is_active: true }

DELETE /api/premium/assets/{asset_id}
       Action: Mark asset deleted, remove from S3 (async cleanup task)
       Response: 204 No Content

GET    /api/premium/styles
       Action: Return available style palettes
       Response: [{ id, name, preview_url }, ...]

PUT    /api/cities/{city_id}/style
       Body: { style_id }
       Action: Update City.settings.design_style (requires city admin role)
       Response: { city_id, style_id }

GET    /api/premium/credits
       Action: Return current credit balance and reset date
       Response: { credits: 47, resets_at: "2026-04-01T00:00:00Z" }
```

---

## Socket.IO Events

```
Server → Client:

  asset_ready
    { asset_id, building_type, s3_url, credits_remaining }
    Emitted to the player's socket session when generation completes.

  asset_failed
    { asset_id, building_type, error }
    Emitted if Celery task exhausts retries.
```

---

## Credit System

- Premium players receive **100 credits/month**, reset on billing anniversary
- Each generation costs **1 credit**
- Credits do not roll over month to month
- Credit deduction happens at request time (before generation) — no refund on failure in v1
- Future: tiered plans with higher credit limits; credit top-up purchases

---

## Content Moderation

Since players select from a curated style palette and building types rather than entering free-form text, the content risk is low. Mitigations:

- Prompts are fully server-constructed — no player text is injected into the SD prompt
- Output images are reviewed by Replicate's built-in safety filter (NSFW classifier)
- Images failing the safety filter are marked `status: failed` and credits are refunded
- Admin endpoint available to review and delete flagged assets

---

## V1 Limitations and Known Gaps

- Isometric perspective consistency depends on ControlNet depth templates — quality will vary across building types until the template library is tuned
- Background removal is imperfect for complex building silhouettes; manual sprite cleanup tooling is a future feature
- No real-time generation progress indicator in v1 — player is notified via `asset_ready` socket event when done
- Credit refund on failure deferred to v2 (requires idempotency work)
- Style palette is fixed at 3 styles in v1; expansion is additive (no breaking changes required)
