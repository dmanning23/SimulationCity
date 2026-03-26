# Phase 5a — HUD Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add floating React HUD panels (stats bar, tool palette display, view mode switcher, player list) over the Phaser game canvas, wired to Zustand stores and Socket.IO events.

**Architecture:** `<HUD>` is a `position: fixed; inset: 0; pointer-events: none` wrapper rendered alongside `<GameCanvas>` in App.tsx. Three panel components float inside it: `StatsBar` (top-left), `PlayerList` (top-right), `Toolbar` (bottom-center). Backend `join_city` is extended to emit `username`+`role` in `player_joined` and include active collaborators in `initial_state`.

**Tech Stack:** React 18, TypeScript, Zustand 4, Vitest, @testing-library/react, python-socketio, Beanie/MongoDB

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `backend/app/socket_handlers.py` | Extend `player_joined` + `initial_state` payloads |
| Create | `backend/tests/test_socket_handlers.py` | Tests for updated payload shapes |
| Create | `frontend/src/components/StatsBar.tsx` | Treasury / population / happiness display |
| Create | `frontend/src/components/StatsBar.test.tsx` | Unit tests for StatsBar |
| Create | `frontend/src/components/PlayerList.tsx` | Active collaborator avatars |
| Create | `frontend/src/components/PlayerList.test.tsx` | Unit tests for PlayerList |
| Create | `frontend/src/components/Toolbar.tsx` | Tool palette (display) + view mode switcher |
| Create | `frontend/src/components/Toolbar.test.tsx` | Unit tests for Toolbar |
| Create | `frontend/src/components/HUD.tsx` | Overlay wrapper — no logic |
| Modify | `frontend/src/socket.ts` | Add `player_joined`, `player_left`; update `initial_state` |
| Modify | `frontend/src/socket.test.ts` | Tests for new socket event handlers |
| Modify | `frontend/src/App.tsx` | Add `<HUD />` alongside `<GameCanvas />` |

---

## Task 1: Backend — extend player_joined and initial_state

**Files:**
- Modify: `backend/app/socket_handlers.py`
- Create: `backend/tests/test_socket_handlers.py`

### Context

The current `join_city` handler in `socket_handlers.py` (around line 139) emits `player_joined` with only `{ user_id }`. The `initial_state` emission (around line 149) does not include `collaborators`. Both need to be extended so the frontend can populate `PlayerList`.

The `Player` model is at `app.models.player.Player` and has a `username: str` field.

The `City` model's `collaborators` list is `list[Collaborator]` where `Collaborator` has `user_id: PydanticObjectId` and `role: CollaboratorRole`. The `owner_id` field identifies the city owner (role = "admin").

`sio.manager.get_participants(namespace, room)` is a **synchronous** call (no `await`) that returns the sids currently in the room. Note: the namespace argument for the default namespace is `"/"`.

- [ ] **Step 1: Write the failing backend tests**

Create `backend/tests/test_socket_handlers.py`:

```python
"""Tests for player_joined and initial_state payload shapes in join_city."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from beanie import PydanticObjectId

from app.socket_handlers import sio


_FAKE_OWNER_SID = "owner-sid-001"
_FAKE_JOINER_SID = "joiner-sid-002"
_FAKE_OWNER_ID = str(ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"))
_FAKE_JOINER_ID = str(ObjectId("bbbbbbbbbbbbbbbbbbbbbbbb"))


def _get_handler(event: str):
    handler = sio.handlers.get("/", {}).get(event)
    if handler is None:
        raise RuntimeError(f"Event '{event}' not registered on sio")
    return handler


@pytest.mark.asyncio
async def test_player_joined_includes_username_and_role(db):
    """player_joined emitted to room includes username and role, not just user_id."""
    from app.models.city import City
    from app.models.player import Player
    from app.models.city import Collaborator, CollaboratorRole

    # Create the owner player
    owner = Player(username="ownerplayer", hashed_password="x", email="o@x.com")
    await owner.insert()
    owner_id = str(owner.id)

    # Create the joining player (a collaborator)
    joiner = Player(username="joinerplayer", hashed_password="x", email="j@x.com")
    await joiner.insert()
    joiner_id = str(joiner.id)

    # Create city with the joiner as a builder collaborator
    city = City(
        name="Test City",
        owner_id=PydanticObjectId(owner_id),
        collaborators=[
            Collaborator(user_id=PydanticObjectId(joiner_id), role=CollaboratorRole.builder)
        ],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": joiner_id}

    emitted_events = []

    async def capture_emit(event, data, **kwargs):
        emitted_events.append((event, data, kwargs))

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock(side_effect=capture_emit)), \
         patch.object(sio.manager, "get_participants", return_value=[]):
        await handler(_FAKE_JOINER_SID, {"city_id": city_id})

    # Find the player_joined event
    player_joined_calls = [(e, d, kw) for e, d, kw in emitted_events if e == "player_joined"]
    assert len(player_joined_calls) == 1
    _, payload, _ = player_joined_calls[0]
    assert payload["user_id"] == joiner_id
    assert payload["username"] == "joinerplayer"
    assert payload["role"] == "builder"


@pytest.mark.asyncio
async def test_player_joined_owner_has_admin_role(db):
    """City owner joining is reported with role='admin' in player_joined."""
    from app.models.city import City
    from app.models.player import Player

    owner = Player(username="adminuser", hashed_password="x", email="a@x.com")
    await owner.insert()
    owner_id = str(owner.id)

    city = City(
        name="Admin City",
        owner_id=PydanticObjectId(owner_id),
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    handler = _get_handler("join_city")
    session = {"user_id": owner_id}

    emitted_events = []

    async def capture_emit(event, data, **kwargs):
        emitted_events.append((event, data, kwargs))

    with patch.object(sio, "get_session", new=AsyncMock(return_value=session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock(side_effect=capture_emit)), \
         patch.object(sio.manager, "get_participants", return_value=[]):
        await handler(_FAKE_OWNER_SID, {"city_id": city_id})

    player_joined_calls = [(e, d, kw) for e, d, kw in emitted_events if e == "player_joined"]
    assert len(player_joined_calls) == 1
    _, payload, _ = player_joined_calls[0]
    assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_initial_state_includes_collaborators_list(db):
    """initial_state includes active collaborators so PlayerList is seeded on join."""
    from app.models.city import City
    from app.models.player import Player

    owner = Player(username="cityowner", hashed_password="x", email="co@x.com")
    await owner.insert()
    owner_id = str(owner.id)

    already_online = Player(username="onlineplayer", hashed_password="x", email="on@x.com")
    await already_online.insert()
    online_id = str(already_online.id)

    city = City(
        name="Populated City",
        owner_id=PydanticObjectId(owner_id),
        collaborators=[],
        global_stats={"population": 0, "treasury": 0.0, "happiness": 50},
        settings={"design_style": "default"},
    )
    await city.insert()
    city_id = str(city.id)

    new_joiner = Player(username="newplayer", hashed_password="x", email="np@x.com")
    await new_joiner.insert()
    new_joiner_id = str(new_joiner.id)

    handler = _get_handler("join_city")
    session = {"user_id": new_joiner_id}

    # Simulate online_player already in the room
    async def fake_get_session(sid):
        if sid == "online-sid":
            return {"user_id": online_id, "city_id": city_id}
        return {"user_id": new_joiner_id}

    emitted_events = []

    async def capture_emit(event, data, **kwargs):
        emitted_events.append((event, data, kwargs))

    with patch.object(sio, "get_session", new=AsyncMock(side_effect=fake_get_session)), \
         patch.object(sio, "enter_room", new=AsyncMock()), \
         patch.object(sio, "save_session", new=AsyncMock()), \
         patch.object(sio, "emit", new=AsyncMock(side_effect=capture_emit)), \
         patch.object(sio.manager, "get_participants", return_value=["online-sid"]):
        await handler("new-joiner-sid", {"city_id": city_id})

    initial_state_calls = [(e, d, kw) for e, d, kw in emitted_events if e == "initial_state"]
    assert len(initial_state_calls) == 1
    _, payload, _ = initial_state_calls[0]
    collaborators = payload["city"]["collaborators"]
    assert len(collaborators) == 1
    assert collaborators[0]["user_id"] == online_id
    assert collaborators[0]["username"] == "onlineplayer"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && uv run pytest tests/test_socket_handlers.py -v 2>&1 | tail -20
```
Expected: 3 FAILED — `player_joined` payload missing `username`/`role`, `initial_state` missing `collaborators`

- [ ] **Step 3: Implement the changes in `socket_handlers.py`**

Add the import at the top of `backend/app/socket_handlers.py` (after existing imports):

```python
from app.models.player import Player as PlayerModel
```

Inside the `join_city` handler, find the `player_joined` emit block (around line 139) and replace it with:

```python
    # Resolve username and role for the joining player
    player_doc = await PlayerModel.find_one(PlayerModel.id == PydanticObjectId(user_id))
    player_username = player_doc.username if player_doc else user_id

    is_owner = str(city.owner_id) == user_id
    if is_owner:
        player_role = "admin"
    else:
        collab = next((c for c in city.collaborators if str(c.user_id) == user_id), None)
        player_role = collab.role.value if collab else "viewer"

    # Notify others in the room (skip the joining player)
    await sio.emit(
        "player_joined",
        {"user_id": user_id, "username": player_username, "role": player_role},
        room=f"city:{city_id}",
        skip_sid=sid,
    )
```

Then find the `initial_state` emit block (around line 147) and replace it with:

```python
    # Collect active collaborators already in the room (excluding the joining player)
    active_sids = sio.manager.get_participants("/", f"city:{city_id}")
    active_user_ids: set[str] = set()
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
            c = next((x for x in city.collaborators if str(x.user_id) == uid), None)
            role = c.role.value if c else "viewer"
        active_collaborators.append({
            "user_id": uid,
            "username": p.username if p else uid,
            "role": role,
        })

    # Send initial state: city metadata + active collaborators + visible chunks
    chunks = await _load_viewport_chunks(city_id, data.get("viewport"))
    await sio.emit(
        "initial_state",
        {
            "city": {
                "id": str(city.id),
                "name": city.name,
                "global_stats": city.global_stats.model_dump(),
                "settings": city.settings.model_dump(),
                "collaborators": active_collaborators,
            },
            "chunks": chunks,
        },
        to=sid,
    )
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd backend && uv run pytest tests/test_socket_handlers.py -v 2>&1 | tail -20
```
Expected: 3 PASSED

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && uv run pytest -v 2>&1 | tail -20
```
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add backend/app/socket_handlers.py backend/tests/test_socket_handlers.py && git commit -m "feat: extend player_joined and initial_state with username, role, and collaborators"
```

---

## Task 2: Frontend test helpers — install @testing-library/react

**Files:**
- Modify: `frontend/package.json` (devDependencies)

- [ ] **Step 1: Install testing libraries**

```bash
cd frontend && npm install --save-dev @testing-library/react @testing-library/user-event
```

- [ ] **Step 2: Verify install**

```bash
cd frontend && npm test 2>&1 | tail -10
```
Expected: existing 29 tests still pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add frontend/package.json frontend/package-lock.json && git commit -m "chore: install @testing-library/react for component tests"
```

---

## Task 3: StatsBar component

**Files:**
- Create: `frontend/src/components/StatsBar.tsx`
- Create: `frontend/src/components/StatsBar.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/StatsBar.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatsBar } from "./StatsBar";
import { useCityStore } from "../stores/cityStore";

beforeEach(() => {
  useCityStore.setState({
    globalStats: { population: 0, treasury: 0, happiness: 50 },
  });
});

describe("StatsBar", () => {
  it("renders treasury with § prefix and locale formatting", () => {
    useCityStore.setState({
      globalStats: { population: 0, treasury: 10000, happiness: 50 },
    });
    render(<StatsBar />);
    expect(screen.getByText(/§10,000/)).toBeInTheDocument();
  });

  it("renders population as integer", () => {
    useCityStore.setState({
      globalStats: { population: 1240, treasury: 0, happiness: 50 },
    });
    render(<StatsBar />);
    expect(screen.getByText(/1240/)).toBeInTheDocument();
  });

  it("renders happiness as percentage", () => {
    useCityStore.setState({
      globalStats: { population: 0, treasury: 0, happiness: 72 },
    });
    render(<StatsBar />);
    expect(screen.getByText(/72%/)).toBeInTheDocument();
  });

  it("updates when globalStats changes in store", () => {
    render(<StatsBar />);
    useCityStore.setState({
      globalStats: { population: 999, treasury: 5000, happiness: 88 },
    });
    expect(screen.getByText(/§5,000/)).toBeInTheDocument();
    expect(screen.getByText(/999/)).toBeInTheDocument();
    expect(screen.getByText(/88%/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test -- StatsBar 2>&1 | tail -15
```
Expected: FAIL — `Cannot find module './StatsBar'`

- [ ] **Step 3: Implement `frontend/src/components/StatsBar.tsx`**

```tsx
import { useCityStore } from "../stores/cityStore";

export function StatsBar() {
  const globalStats = useCityStore((s) => s.globalStats);

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        pointerEvents: "none",
        background: "rgba(22, 27, 34, 0.85)",
        backdropFilter: "blur(8px)",
        border: "1px solid rgba(48, 54, 61, 0.8)",
        borderRadius: 8,
        padding: "8px 14px",
        display: "flex",
        gap: 18,
        alignItems: "center",
      }}
    >
      <span style={{ color: "#f59e0b" }}>
        §{globalStats.treasury.toLocaleString()}
      </span>
      <span style={{ color: "#60a5fa" }}>
        👥 {globalStats.population}
      </span>
      <span style={{ color: "#34d399" }}>
        😊 {globalStats.happiness}%
      </span>
    </div>
  );
}
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd frontend && npm test -- StatsBar 2>&1 | tail -15
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add frontend/src/components/StatsBar.tsx frontend/src/components/StatsBar.test.tsx && git commit -m "feat: add StatsBar component with treasury/population/happiness display"
```

---

## Task 4: PlayerList component

**Files:**
- Create: `frontend/src/components/PlayerList.tsx`
- Create: `frontend/src/components/PlayerList.test.tsx`

### Avatar color logic

Colors are deterministic: sum all char codes of `userId` modulo 6, index into a fixed palette.

```typescript
const AVATAR_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444"];

function avatarColor(userId: string): string {
  const sum = userId.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}
```

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/PlayerList.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlayerList } from "./PlayerList";
import { usePlayerStore } from "../stores/playerStore";

beforeEach(() => {
  usePlayerStore.setState({ collaborators: [] });
});

describe("PlayerList", () => {
  it("renders nothing when collaborators is empty", () => {
    const { container } = render(<PlayerList />);
    expect(container.firstChild).toBeNull();
  });

  it("renders username for each collaborator", () => {
    usePlayerStore.setState({
      collaborators: [
        { userId: "abc123", username: "alice", role: "builder" },
        { userId: "def456", username: "bob", role: "viewer" },
      ],
    });
    render(<PlayerList />);
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders avatar with first letter of username", () => {
    usePlayerStore.setState({
      collaborators: [{ userId: "uid1", username: "charlie", role: "builder" }],
    });
    render(<PlayerList />);
    expect(screen.getByText("c")).toBeInTheDocument();
  });

  it("same userId always produces the same avatar color", () => {
    const collaborator = { userId: "stable-id-001", username: "dana", role: "builder" as const };
    usePlayerStore.setState({ collaborators: [collaborator] });

    const { unmount } = render(<PlayerList />);
    const firstAvatar = screen.getByText("d").style.backgroundColor;
    unmount();

    usePlayerStore.setState({ collaborators: [collaborator] });
    render(<PlayerList />);
    const secondAvatar = screen.getByText("d").style.backgroundColor;

    expect(firstAvatar).toBe(secondAvatar);
    expect(firstAvatar).not.toBe("");
  });

  it("two collaborators with different userId values produce different colors when palette indices differ", () => {
    // Find two userIds that hash to different palette indices
    // userId "a" (97) % 6 = 1, userId "g" (103) % 6 = 1 — not useful
    // We need userIds where charcode-sum % 6 differ
    // "aaa" = 97*3 = 291 % 6 = 3;  "b" = 98 % 6 = 2
    usePlayerStore.setState({
      collaborators: [
        { userId: "aaa", username: "user1", role: "builder" },
        { userId: "b", username: "user2", role: "builder" },
      ],
    });
    render(<PlayerList />);
    const avatars = screen.getAllByRole("img", { hidden: true });
    // Get the rendered avatar divs (first letter of each username)
    const avatar1 = screen.getByText("u", { selector: "[data-avatar]" });
    // Since both have same first letter "u", use getAllByText and check colors differ
    const allU = screen.getAllByText("u");
    expect(allU).toHaveLength(2);
    expect(allU[0].style.backgroundColor).not.toBe(allU[1].style.backgroundColor);
  });
});
```

Note: The last test uses `data-avatar` attribute. If both usernames start with the same letter, we need a `data-avatar` attribute on the avatar element to distinguish them. Include `data-avatar="true"` on the avatar div in the implementation.

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test -- PlayerList 2>&1 | tail -15
```
Expected: FAIL — `Cannot find module './PlayerList'`

- [ ] **Step 3: Implement `frontend/src/components/PlayerList.tsx`**

```tsx
import { usePlayerStore } from "../stores/playerStore";

const AVATAR_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444"];

function avatarColor(userId: string): string {
  const sum = userId.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

export function PlayerList() {
  const collaborators = usePlayerStore((s) => s.collaborators);

  if (collaborators.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        right: 12,
        pointerEvents: "none",
        background: "rgba(22, 27, 34, 0.85)",
        backdropFilter: "blur(8px)",
        border: "1px solid rgba(48, 54, 61, 0.8)",
        borderRadius: 8,
        padding: "6px 12px",
        display: "flex",
        gap: 10,
        alignItems: "center",
      }}
    >
      {collaborators.map((c) => (
        <div
          key={c.userId}
          style={{ display: "flex", alignItems: "center", gap: 5 }}
        >
          <div
            data-avatar="true"
            style={{
              width: 22,
              height: 22,
              borderRadius: "50%",
              backgroundColor: avatarColor(c.userId),
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              color: "#fff",
              fontFamily: "monospace",
            }}
          >
            {c.username[0]}
          </div>
          <span style={{ color: "#e6edf3", fontFamily: "monospace", fontSize: 12 }}>
            {c.username}
          </span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Fix the color-difference test**

The last test (`getAllByText("u")`) assumes both usernames start with "u". Update the test so it checks `data-avatar` element `backgroundColor` directly, using `screen.getAllByRole` won't work for divs. Simplify: use `getAllByText` with a selector:

```tsx
// Replace the last test in PlayerList.test.tsx with:
it("two collaborators with different userId palette indices produce different avatar colors", () => {
  // "aaa": 97+97+97=291, 291%6=3 → color index 3 (#f59e0b)
  // "b":   98,           98%6=2  → color index 2 (#ec4899)
  usePlayerStore.setState({
    collaborators: [
      { userId: "aaa", username: "xfirst", role: "builder" },
      { userId: "b", username: "xsecond", role: "builder" },
    ],
  });
  render(<PlayerList />);
  const avatars = document.querySelectorAll("[data-avatar='true']");
  expect(avatars).toHaveLength(2);
  expect((avatars[0] as HTMLElement).style.backgroundColor).not.toBe(
    (avatars[1] as HTMLElement).style.backgroundColor
  );
});
```

Replace the last test in `PlayerList.test.tsx` with this version before running.

- [ ] **Step 5: Run tests — expect all to pass**

```bash
cd frontend && npm test -- PlayerList 2>&1 | tail -15
```
Expected: 5 PASSED

- [ ] **Step 6: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add frontend/src/components/PlayerList.tsx frontend/src/components/PlayerList.test.tsx && git commit -m "feat: add PlayerList component with deterministic avatar colors"
```

---

## Task 5: Toolbar component

**Files:**
- Create: `frontend/src/components/Toolbar.tsx`
- Create: `frontend/src/components/Toolbar.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/Toolbar.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toolbar } from "./Toolbar";
import { useCityStore } from "../stores/cityStore";

beforeEach(() => {
  useCityStore.setState({ activeViewMode: "base" });
});

describe("Toolbar — tool buttons", () => {
  it("renders all 6 tool buttons", () => {
    render(<Toolbar />);
    expect(screen.getByText("R")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("I")).toBeInTheDocument();
    expect(screen.getByText("🛣️")).toBeInTheDocument();
    expect(screen.getByText("⚡")).toBeInTheDocument();
    expect(screen.getByText("🔨")).toBeInTheDocument();
  });

  it("tool buttons do not call setViewMode when clicked", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByText("R"));
    expect(setViewMode).not.toHaveBeenCalled();
  });
});

describe("Toolbar — view mode buttons", () => {
  it("renders all 4 view mode buttons", () => {
    render(<Toolbar />);
    expect(screen.getByText("Base")).toBeInTheDocument();
    // ⚡ appears in tools AND view modes — use getAllByText
    expect(screen.getAllByText("⚡")).toHaveLength(2);
    expect(screen.getByText("🌫️")).toBeInTheDocument();
    expect(screen.getByText("💧")).toBeInTheDocument();
  });

  it("active view mode button has blue background", () => {
    useCityStore.setState({ activeViewMode: "base" });
    render(<Toolbar />);
    const baseBtn = screen.getByTestId("viewmode-base");
    expect(baseBtn.style.backgroundColor).toBe("rgb(29, 78, 216)"); // #1d4ed8
  });

  it("inactive view mode buttons do not have blue background", () => {
    useCityStore.setState({ activeViewMode: "base" });
    render(<Toolbar />);
    const pollutionBtn = screen.getByTestId("viewmode-pollution");
    expect(pollutionBtn.style.backgroundColor).not.toBe("rgb(29, 78, 216)");
  });

  it("clicking Base calls setViewMode('base')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-base"));
    expect(setViewMode).toHaveBeenCalledWith("base");
  });

  it("clicking electricity button calls setViewMode('electricity')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-electricity"));
    expect(setViewMode).toHaveBeenCalledWith("electricity");
  });

  it("clicking pollution button calls setViewMode('pollution')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-pollution"));
    expect(setViewMode).toHaveBeenCalledWith("pollution");
  });

  it("clicking water button calls setViewMode('water')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-water"));
    expect(setViewMode).toHaveBeenCalledWith("water");
  });
});
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test -- Toolbar 2>&1 | tail -15
```
Expected: FAIL — `Cannot find module './Toolbar'`

- [ ] **Step 3: Implement `frontend/src/components/Toolbar.tsx`**

```tsx
import { useCityStore } from "../stores/cityStore";
import type { ViewMode } from "../stores/cityStore";

const TOOLS = [
  { label: "R", title: "Residential zone" },
  { label: "C", title: "Commercial zone" },
  { label: "I", title: "Industrial zone" },
  { label: "🛣️", title: "Road" },
  { label: "⚡", title: "Power line" },
  { label: "🔨", title: "Demolish" },
];

const VIEW_MODES: { label: string; mode: ViewMode }[] = [
  { label: "Base", mode: "base" },
  { label: "⚡", mode: "electricity" },
  { label: "🌫️", mode: "pollution" },
  { label: "💧", mode: "water" },
];

const pillStyle: React.CSSProperties = {
  position: "absolute",
  bottom: 16,
  left: "50%",
  transform: "translateX(-50%)",
  pointerEvents: "none",
  background: "rgba(22, 27, 34, 0.9)",
  backdropFilter: "blur(8px)",
  border: "1px solid rgba(48, 54, 61, 0.8)",
  borderRadius: 24,
  padding: "8px 16px",
  display: "flex",
  alignItems: "center",
  gap: 4,
};

const toolBtnStyle: React.CSSProperties = {
  background: "#21262d",
  border: "1px solid #30363d",
  borderRadius: 6,
  padding: "6px 10px",
  color: "#8b949e",
  fontFamily: "monospace",
  fontSize: 12,
  cursor: "default",
};

const dividerStyle: React.CSSProperties = {
  width: 1,
  height: 24,
  background: "#30363d",
  margin: "0 6px",
};

export function Toolbar() {
  const activeViewMode = useCityStore((s) => s.activeViewMode);

  return (
    <div style={pillStyle}>
      {/* Tool group — display only */}
      {TOOLS.map((tool) => (
        <div key={tool.label} style={toolBtnStyle} title={tool.title}>
          {tool.label}
        </div>
      ))}

      <div style={dividerStyle} />

      {/* View mode group — interactive */}
      <div style={{ display: "flex", gap: 4, pointerEvents: "auto" }}>
        {VIEW_MODES.map(({ label, mode }) => {
          const isActive = activeViewMode === mode;
          return (
            <button
              key={mode}
              data-testid={`viewmode-${mode}`}
              onClick={() => useCityStore.getState().setViewMode(mode)}
              style={{
                background: isActive ? "#1d4ed8" : "#21262d",
                border: `1px solid ${isActive ? "#3b82f6" : "#30363d"}`,
                borderRadius: 6,
                padding: "6px 10px",
                color: isActive ? "#93c5fd" : "#8b949e",
                fontFamily: "monospace",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
cd frontend && npm test -- Toolbar 2>&1 | tail -15
```
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add frontend/src/components/Toolbar.tsx frontend/src/components/Toolbar.test.tsx && git commit -m "feat: add Toolbar component with tool palette display and view mode switcher"
```

---

## Task 6: socket.ts — player event handlers

**Files:**
- Modify: `frontend/src/socket.ts`
- Modify: `frontend/src/socket.test.ts`

- [ ] **Step 1: Add failing tests to `socket.test.ts`**

Add these imports and test cases to the existing `frontend/src/socket.test.ts`:

At the top, add `usePlayerStore` import:
```typescript
import { usePlayerStore } from "./stores/playerStore";
import type { Collaborator } from "./stores/playerStore";
```

Add to the `beforeEach` block:
```typescript
usePlayerStore.setState({ collaborators: [] });
```

Add a new describe block after the existing ones:

```typescript
describe("player event handlers", () => {
  it("player_joined adds collaborator to store", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    handlers["player_joined"]({
      user_id: "uid1",
      username: "alice",
      role: "builder",
    });

    const collaborators = usePlayerStore.getState().collaborators;
    expect(collaborators).toHaveLength(1);
    expect(collaborators[0]).toEqual({
      userId: "uid1",
      username: "alice",
      role: "builder",
    });
  });

  it("player_joined does not add duplicate if user_id already present", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    handlers["player_joined"]({ user_id: "uid1", username: "alice", role: "builder" });
    handlers["player_joined"]({ user_id: "uid1", username: "alice", role: "builder" });

    expect(usePlayerStore.getState().collaborators).toHaveLength(1);
  });

  it("player_left removes collaborator from store", async () => {
    usePlayerStore.setState({
      collaborators: [
        { userId: "uid1", username: "alice", role: "builder" },
        { userId: "uid2", username: "bob", role: "viewer" },
      ],
    });

    const { initSocket } = await import("./socket");
    initSocket("city1");

    handlers["player_left"]({ user_id: "uid1" });

    const collaborators = usePlayerStore.getState().collaborators;
    expect(collaborators).toHaveLength(1);
    expect(collaborators[0].userId).toBe("uid2");
  });

  it("initial_state seeds collaborators from city.collaborators", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    handlers["initial_state"]({
      city_id: "city1",
      city: {
        id: "city1",
        name: "Test City",
        collaborators: [
          { user_id: "uid3", username: "carol", role: "admin" },
        ],
      },
      chunks: [],
    });

    const collaborators = usePlayerStore.getState().collaborators;
    expect(collaborators).toHaveLength(1);
    expect(collaborators[0]).toEqual({
      userId: "uid3",
      username: "carol",
      role: "admin",
    });
  });
});
```

- [ ] **Step 2: Run tests — expect new tests to fail**

```bash
cd frontend && npm test -- socket 2>&1 | tail -20
```
Expected: existing tests pass, new 4 tests FAIL

- [ ] **Step 3: Update `frontend/src/socket.ts`**

Add the `usePlayerStore` import at the top:
```typescript
import { usePlayerStore } from "./stores/playerStore";
import type { CollaboratorRole } from "./stores/playerStore";
```

Replace the `initial_state` handler (currently just a `console.log` with no store updates — safe to replace wholesale) with:
```typescript
  socket.on(
    "initial_state",
    (data: {
      city_id: string;
      city: {
        collaborators?: Array<{ user_id: string; username: string; role: string }>;
      };
    }) => {
      if (data.city?.collaborators) {
        usePlayerStore.getState().setCollaborators(
          data.city.collaborators.map((c) => ({
            userId: c.user_id,
            username: c.username,
            role: c.role as CollaboratorRole,
          }))
        );
      }
    }
  );
```

Add after the `stats_update` handler and before the `error` handler:
```typescript
  socket.on(
    "player_joined",
    (data: { user_id: string; username: string; role: string }) => {
      const { collaborators } = usePlayerStore.getState();
      const already = collaborators.some((c) => c.userId === data.user_id);
      if (!already) {
        usePlayerStore.getState().setCollaborators([
          ...collaborators,
          { userId: data.user_id, username: data.username, role: data.role as CollaboratorRole },
        ]);
      }
    }
  );

  socket.on("player_left", (data: { user_id: string }) => {
    const { collaborators } = usePlayerStore.getState();
    usePlayerStore.getState().setCollaborators(
      collaborators.filter((c) => c.userId !== data.user_id)
    );
  });
```

- [ ] **Step 4: Run all frontend tests — expect all to pass**

```bash
cd frontend && npm test 2>&1 | tail -15
```
Expected: all PASS (33 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add frontend/src/socket.ts frontend/src/socket.test.ts && git commit -m "feat: add player_joined/player_left socket handlers and seed collaborators from initial_state"
```

---

## Task 7: HUD wrapper + App.tsx wiring

**Files:**
- Create: `frontend/src/components/HUD.tsx`
- Modify: `frontend/src/App.tsx`

No unit tests for `HUD.tsx` — it is a pass-through wrapper with no logic.

- [ ] **Step 1: Create `frontend/src/components/HUD.tsx`**

```tsx
import { StatsBar } from "./StatsBar";
import { PlayerList } from "./PlayerList";
import { Toolbar } from "./Toolbar";

export function HUD() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10,
        pointerEvents: "none",
      }}
    >
      <StatsBar />
      <PlayerList />
      <Toolbar />
    </div>
  );
}
```

- [ ] **Step 2: Update `frontend/src/App.tsx`**

Read the current file first. Replace content with:

```tsx
import { GameCanvas } from "./components/GameCanvas";
import { HUD } from "./components/HUD";

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

- [ ] **Step 3: Run all frontend tests**

```bash
cd frontend && npm test 2>&1 | tail -15
```
Expected: all PASS

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v node_modules | grep -v ImportMeta | head -20
```
Expected: no errors in our new files

- [ ] **Step 5: Commit**

```bash
cd /Users/danmanning/Documents/Source/SimulationCity && git add frontend/src/components/HUD.tsx frontend/src/App.tsx && git commit -m "feat: add HUD overlay wrapper and wire into App"
```

---

## Final check

Run the full test suite for both backend and frontend:

```bash
cd backend && uv run pytest -v 2>&1 | tail -10
cd frontend && npm test 2>&1 | tail -10
```

Expected: all tests pass.
