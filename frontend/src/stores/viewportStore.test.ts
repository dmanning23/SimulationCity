import { describe, it, expect, beforeEach } from "vitest";
import { useViewportStore } from "./viewportStore";
import type { Chunk } from "./viewportStore";

const makeChunk = (x: number, y: number): Chunk => ({
  city_id: "city1",
  coordinates: { x, y },
  version: 1,
  base: {
    terrain: [[0]],
    buildings: [],
    roads: [],
  },
  layers: {
    electricity: {},
    pollution: {},
    water: {},
  },
});

beforeEach(() => {
  useViewportStore.setState({ loadedChunks: new Map() });
});

describe("updateChunk", () => {
  it("inserts a chunk by 'x,y' key", () => {
    const chunk = makeChunk(3, 7);
    useViewportStore.getState().updateChunk(chunk);
    expect(useViewportStore.getState().loadedChunks.get("3,7")).toEqual(chunk);
  });

  it("upserts without affecting other chunks", () => {
    useViewportStore.getState().updateChunk(makeChunk(0, 0));
    useViewportStore.getState().updateChunk(makeChunk(1, 1));
    expect(useViewportStore.getState().loadedChunks.size).toBe(2);
  });
});

describe("patchBase", () => {
  it("updates buildings and roads on an existing chunk", () => {
    useViewportStore.getState().updateChunk(makeChunk(2, 2));
    const buildings = [{ type: "residential" }];
    const roads = [{ direction: "NS" }];
    useViewportStore.getState().patchBase(2, 2, buildings, roads);

    const chunk = useViewportStore.getState().loadedChunks.get("2,2")!;
    expect(chunk.base.buildings).toEqual(buildings);
    expect(chunk.base.roads).toEqual(roads);
  });

  it("leaves layers and other fields untouched", () => {
    const original = makeChunk(2, 2);
    original.layers.electricity = { coverage: 1 };
    useViewportStore.getState().updateChunk(original);
    useViewportStore.getState().patchBase(2, 2, [], []);

    const chunk = useViewportStore.getState().loadedChunks.get("2,2")!;
    expect(chunk.layers.electricity).toEqual({ coverage: 1 });
    expect(chunk.version).toBe(1);
  });

  it("is a no-op if the chunk is not loaded", () => {
    useViewportStore.getState().patchBase(99, 99, [], []);  // must not throw
    expect(useViewportStore.getState().loadedChunks.size).toBe(0);
  });
});

describe("patchLayers", () => {
  it("updates layers on an existing chunk", () => {
    useViewportStore.getState().updateChunk(makeChunk(1, 0));
    const layers = {
      electricity: { coverage: 0.8 },
      pollution: { coverage: 0.1 },
      water: { coverage: 1 },
    };
    useViewportStore.getState().patchLayers(1, 0, layers);

    const chunk = useViewportStore.getState().loadedChunks.get("1,0")!;
    expect(chunk.layers).toEqual(layers);
  });

  it("leaves base untouched", () => {
    const original = makeChunk(1, 0);
    original.base.buildings = [{ type: "commercial" }];
    useViewportStore.getState().updateChunk(original);
    useViewportStore.getState().patchLayers(1, 0, {
      electricity: {},
      pollution: {},
      water: {},
    });

    const chunk = useViewportStore.getState().loadedChunks.get("1,0")!;
    expect(chunk.base.buildings).toEqual([{ type: "commercial" }]);
  });

  it("is a no-op if the chunk is not loaded", () => {
    useViewportStore.getState().patchLayers(99, 99, {
      electricity: {},
      pollution: {},
      water: {},
    });
    expect(useViewportStore.getState().loadedChunks.size).toBe(0);
  });
});

describe("removeChunk", () => {
  it("removes an existing chunk", () => {
    useViewportStore.getState().updateChunk(makeChunk(5, 5));
    useViewportStore.getState().removeChunk("5,5");
    expect(useViewportStore.getState().loadedChunks.has("5,5")).toBe(false);
  });

  it("does not affect other chunks", () => {
    useViewportStore.getState().updateChunk(makeChunk(0, 0));
    useViewportStore.getState().updateChunk(makeChunk(1, 1));
    useViewportStore.getState().removeChunk("0,0");
    expect(useViewportStore.getState().loadedChunks.size).toBe(1);
    expect(useViewportStore.getState().loadedChunks.has("1,1")).toBe(true);
  });

  it("is a no-op if key doesn't exist", () => {
    useViewportStore.getState().removeChunk("99,99");  // must not throw
    expect(useViewportStore.getState().loadedChunks.size).toBe(0);
  });
});
