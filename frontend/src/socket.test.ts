import { describe, it, expect, beforeEach, vi } from "vitest";
import { io } from "socket.io-client";
import { useViewportStore } from "./stores/viewportStore";
import { useCityStore } from "./stores/cityStore";
import { usePlayerStore } from "./stores/playerStore";
import type { Collaborator } from "./stores/playerStore";

vi.mock("socket.io-client");

// Capture the event handlers registered in initSocket
const handlers: Record<string, (...args: unknown[]) => void> = {};
const mockSocket = {
  on: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
    handlers[event] = handler;
  }),
  emit: vi.fn(),
  disconnect: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  // IMPORTANT: set mock return AFTER clearAllMocks
  vi.mocked(io).mockReturnValue(mockSocket as unknown as ReturnType<typeof io>);
  useViewportStore.setState({ loadedChunks: new Map() });
  usePlayerStore.setState({ collaborators: [] });
});

describe("socket event handlers", () => {
  it("viewport_seed calls updateChunk for each chunk", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    const chunk = {
      city_id: "city1",
      coordinates: { x: 0, y: 0 },
      version: 1,
      base: { terrain: [[0]], buildings: [], roads: [] },
      layers: { electricity: {}, pollution: {}, water: {} },
    };
    handlers["viewport_seed"]({ chunks: [chunk] });

    expect(useViewportStore.getState().loadedChunks.get("0,0")).toEqual(chunk);
  });

  it("chunk_update calls patchBase with correct args", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    const patchBase = vi.spyOn(useViewportStore.getState(), "patchBase");
    handlers["chunk_update"]({
      city_id: "city1",
      chunk_x: 2,
      chunk_y: 3,
      buildings: [{ type: "residential" }],
      roads: [],
    });

    expect(patchBase).toHaveBeenCalledWith(2, 3, [{ type: "residential" }], []);
  });

  it("layers_update calls patchLayers with correct args", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    const patchLayers = vi.spyOn(useViewportStore.getState(), "patchLayers");
    const layers = { electricity: { coverage: 0.5 }, pollution: {}, water: {} };
    handlers["layers_update"]({ city_id: "city1", chunk_x: 1, chunk_y: 1, layers });

    expect(patchLayers).toHaveBeenCalledWith(1, 1, layers);
  });

  it("stats_update sets city stats from flat payload", async () => {
    const { initSocket } = await import("./socket");
    initSocket("city1");

    handlers["stats_update"]({ population: 1000, treasury: 500.0, happiness: 75 });

    const state = useCityStore.getState();
    expect(state.globalStats.population).toBe(1000);
    expect(state.globalStats.treasury).toBe(500.0);
    expect(state.globalStats.happiness).toBe(75);
  });
});

describe("emitUpdateViewport", () => {
  it("emits update_viewport with city_id and bbox", async () => {
    const { initSocket, emitUpdateViewport } = await import("./socket");
    initSocket("city1");

    emitUpdateViewport("city1", { min_x: 0, min_y: 0, max_x: 2, max_y: 2 });
    expect(mockSocket.emit).toHaveBeenCalledWith("update_viewport", {
      city_id: "city1",
      min_x: 0,
      min_y: 0,
      max_x: 2,
      max_y: 2,
    });
  });
});

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
