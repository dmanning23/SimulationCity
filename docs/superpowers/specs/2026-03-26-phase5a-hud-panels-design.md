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
- Click calls `useCityStore.getState().setViewMode(mode)`
- `pointer-events: auto` on this group only

Style: `position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%)`, same glass background, `border-radius: 24px`.

---

## Socket Events

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

`initial_state` handler already fires on join — update it to populate `collaborators` from `data.city.collaborators` if present.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `frontend/src/components/HUD.tsx` | Overlay wrapper |
| Create | `frontend/src/components/StatsBar.tsx` | Treasury / population / happiness |
| Create | `frontend/src/components/Toolbar.tsx` | Tool palette (display) + view mode switcher |
| Create | `frontend/src/components/PlayerList.tsx` | Active collaborator avatars |
| Modify | `frontend/src/socket.ts` | Add `player_joined` / `player_left` handlers |
| Modify | `frontend/src/App.tsx` | Add `<HUD />` alongside `<GameCanvas />` |

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
