import { describe, it, expect, beforeEach, vi } from "vitest";
import { io } from "socket.io-client";
import { useViewportStore } from "./stores/viewportStore";
import { useCityStore } from "./stores/cityStore";

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
