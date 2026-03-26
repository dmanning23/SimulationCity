# Phase 5a — HUD Panels Design

## Goal

Add floating React UI panels over the Phaser game canvas: a stats bar (treasury, population, happiness), a toolbar (tool palette display + view mode switcher), and a player list (active collaborators).

Building placement (tile-click → `build_action`) and time controls are deferred to Phase 5b.

---

## Architecture

### Overlay Layer

`App.tsx` renders two siblings:

```tsx
export default function App() {
  const cityId = new URLSearchParams(window.location.search).get("city") ?? undefined;
  return (
    <>
      <GameCanvas cityId={cityId} />
      <HUD />
    </>
  );
}
```

`<HUD>` is `position: fixed; inset: 0; pointer-events: none; z-index: 10`. Individual panels inside it set `pointer-events: auto` only where user interaction is needed (view mode buttons). This keeps mouse events flowing to the Phaser canvas everywhere else.

### Panels

| Component | Position | Interaction | Store |
|-----------|----------|-------------|-------|
| `StatsBar` | top-left | none (display only) | `useCityStore.globalStats` |
| `PlayerList` | top-right | none (display only) | `usePlayerStore.collaborators` |
| `Toolbar` | bottom-center | view mode clicks only | `useCityStore.activeViewMode` |

---

## Component Specs

### `HUD.tsx`

Wrapper only — no state, no logic. Renders three panels in fixed positions:

```tsx
export function HUD() {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 10, pointerEvents: "none" }}>
      <StatsBar />
      <PlayerList />
      <Toolbar />
    </div>
  );
}
```

### `StatsBar.tsx`

Reads `useCityStore(s => s.globalStats)`. Renders treasury (§), population (👥), happiness (😊) in a semi-transparent floating pill, top-left.

- `treasury`: formatted with `§` prefix and locale number formatting (e.g. `§10,000`)
- `population`: integer
- `happiness`: integer percentage (e.g. `72%`)
- Style: `position: absolute; top: 12px; left: 12px; pointer-events: none`
- Background: `rgba(22, 27, 34, 0.85)` with `backdrop-filter: blur(8px)`
- Border: `1px solid rgba(48, 54, 61, 0.8)`, `border-radius: 8px`

### `PlayerList.tsx`

Reads `usePlayerStore(s => s.collaborators)`. Renders a row of avatar + username pairs, top-right.

- Each collaborator: colored circle with first letter of username + username text
- Avatar colors: deterministic from `userId` (use a small palette — cycle through 6 colors)
- Style: `position: absolute; top: 12px; right: 12px; pointer-events: none`
- Same glass background as StatsBar
- Hidden/empty if `collaborators` array is empty

### `Toolbar.tsx`

Bottom-center pill. Two groups separated by a vertical divider:

**Tool group (display-only, Phase 5b wires these up):**
- R (Residential), C (Commercial), I (Industrial), 🛣️ (Road), ⚡ (Power), 🔨 (Demolish)
- `cursor: default`, no click handlers
- All rendered at equal opacity — no "active" state in Phase 5a

**View mode group (interactive):**
- Base, ⚡ (Electricity), 🌫️ (Pollution), 💧 (Water)
- Reads `useCityStore(s => s.activeViewMode)`
- Active mode: highlighted blue background (`#1d4ed8`, border `#3b82f6`, text `#93c5fd`)
- Inactive: `#21262d` background, `#8b949e` text
- Click calls `useCityStore.getState().setViewMode(mode)` with the exact `ViewMode` string:
  - "Base" button → `setViewMode("base")`
  - "⚡" button → `setViewMode("electricity")`
  - "🌫️" button → `setViewMode("pollution")`
  - "💧" button → `setViewMode("water")`
- `pointer-events: auto` on this group only

Style: `position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%)`, same glass background, `border-radius: 24px`.

---

## Backend Changes Required

Two backend changes are in scope for Phase 5a:

### 1. Extend `player_joined` payload with `username` and `role`

In `backend/app/socket_handlers.py`, the `join_city` handler currently emits `{ user_id }` only. It must be extended to include `username` and `role`. Since `username` is not in the session, the handler must query the `Player` model:

```python
from backend.app.models.player import Player as PlayerModel

# Inside join_city, before the player_joined emit:
player = await PlayerModel.find_one(PlayerModel.id == PydanticObjectId(user_id))
player_username = player.username if player else user_id

# Find the joining player's role (owner = "admin", collaborator = their stored role)
if is_owner:
    player_role = "admin"
else:
    collab = next((c for c in city.collaborators if str(c.user_id) == user_id), None)
    player_role = collab.role.value if collab else "viewer"

await sio.emit(
    "player_joined",
    {"user_id": user_id, "username": player_username, "role": player_role},
    room=f"city:{city_id}",
    skip_sid=sid,
)
```

### 2. Extend `initial_state` payload with `collaborators`

The `initial_state` emission must include a `collaborators` list so the joining player can populate their `PlayerList` immediately without waiting for subsequent `player_joined` events from other players. Since `city.collaborators` only stores `user_id` + `role`, the handler must fetch usernames:

```python
# Fetch usernames for all currently connected collaborators
# (only active sessions — those in the city room)
# Note: get_participants is synchronous (no await)
active_sids = sio.manager.get_participants("/", f"city:{city_id}")
active_user_ids = set()
for s in active_sids:
    sess = await sio.get_session(s)
    if sess and sess.get("user_id") and sess.get("user_id") != user_id:
        active_user_ids.add(sess["user_id"])

active_collaborators = []
for uid in active_user_ids:
    p = await PlayerModel.find_one(PlayerModel.id == PydanticObjectId(uid))
    is_player_owner = str(city.owner_id) == uid
    if is_player_owner:
        role = "admin"
    else:
        collab = next((c for c in city.collaborators if str(c.user_id) == uid), None)
        role = collab.role.value if collab else "viewer"
    active_collaborators.append({
        "user_id": uid,
        "username": p.username if p else uid,
        "role": role,
    })

await sio.emit(
    "initial_state",
    {
        "city": {
            "id": str(city.id),
            "name": city.name,
            "global_stats": city.global_stats.model_dump(),
            "settings": city.settings.model_dump(),
            "collaborators": active_collaborators,  # new field
        },
        "chunks": chunks,
    },
    to=sid,
)
```

---

## Socket Events (Frontend)

Add two new handlers to `socket.ts`:

```typescript
socket.on("player_joined", (data: { user_id: string; username: string; role: string }) => {
  const { collaborators } = usePlayerStore.getState();
  const already = collaborators.some(c => c.userId === data.user_id);
  if (!already) {
    usePlayerStore.getState().setCollaborators([
      ...collaborators,
      { userId: data.user_id, username: data.username, role: data.role as CollaboratorRole },
    ]);
  }
});

socket.on("player_left", (data: { user_id: string }) => {
  const { collaborators } = usePlayerStore.getState();
  usePlayerStore.getState().setCollaborators(
    collaborators.filter(c => c.userId !== data.user_id)
  );
});
```

Update `initial_state` handler to seed `collaborators` from `data.city.collaborators`:

```typescript
socket.on("initial_state", (data) => {
  if (data.city?.collaborators) {
    usePlayerStore.getState().setCollaborators(
      data.city.collaborators.map((c: { user_id: string; username: string; role: string }) => ({
        userId: c.user_id,
        username: c.username,
        role: c.role as CollaboratorRole,
      }))
    );
  }
});
```

**Self-filtering:** `player_joined` is emitted with `skip_sid=sid`, so the joining player never receives their own event. The `collaborators` list in `PlayerStore` represents all *other* active players — the local player is never included. `PlayerList` renders `collaborators` as-is with no filtering needed.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `frontend/src/components/HUD.tsx` | Overlay wrapper |
| Create | `frontend/src/components/StatsBar.tsx` | Treasury / population / happiness |
| Create | `frontend/src/components/Toolbar.tsx` | Tool palette (display) + view mode switcher |
| Create | `frontend/src/components/PlayerList.tsx` | Active collaborator avatars |
| Modify | `frontend/src/socket.ts` | Add `player_joined` / `player_left` handlers; update `initial_state` handler |
| Modify | `frontend/src/App.tsx` | Add `<HUD />` alongside `<GameCanvas />` |
| Modify | `backend/app/socket_handlers.py` | Extend `player_joined` payload with `username`+`role`; extend `initial_state` with `collaborators` |
| Modify | `backend/tests/test_socket_handlers.py` | Tests for updated payload shapes |

---

## Testing

Unit tests (Vitest + jsdom) for each component:

**`StatsBar.test.tsx`**
- Renders treasury with `§` prefix and locale formatting
- Renders population as integer
- Renders happiness as percentage
- Reactively updates when `globalStats` changes in store

**`Toolbar.test.tsx`**
- Renders all tool buttons (R, C, I, road, power, demolish)
- Active view mode button has blue highlight class/style
- Clicking a view mode button calls `setViewMode` with correct mode
- Tool buttons have no click handlers (no Zustand calls on tool click)

**`PlayerList.test.tsx`**
- Renders nothing when collaborators is empty
- Renders username for each collaborator
- Renders avatar with first letter of username
- Same `userId` always produces the same avatar color (deterministic): render the same collaborator twice and assert the color class/style is identical both times
- Two collaborators with different `userId` values that map to different palette indices produce different colors

**`socket.test.ts` additions**
- `player_joined` handler adds collaborator to store (no duplicate on second call)
- `player_left` handler removes collaborator from store

No unit tests for `HUD.tsx` (it's a pass-through wrapper with no logic).

---

## What's NOT in Phase 5a

- Time controls (pause/play/speed) — Phase 5b
- Tool selection state (`selectedTool` in Zustand) — Phase 5b
- Tile click → `build_action` emission — Phase 5b
- Admin-only UI gating — Phase 5b
- Building placement flow — Phase 5b
