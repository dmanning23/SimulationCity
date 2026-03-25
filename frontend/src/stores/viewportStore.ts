import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export type Chunk = {
  city_id: string;
  coordinates: { x: number; y: number };
  version: number;
  base: {
    terrain: number[][];
    buildings: unknown[];
    roads: unknown[];
  };
  layers: {
    electricity: Record<string, unknown>;
    pollution: Record<string, unknown>;
    water: Record<string, unknown>;
  };
};

type ViewportState = {
  chunkX: number;
  chunkY: number;
  zoom: number;
  loadedChunks: Map<string, Chunk>;
  setViewport: (x: number, y: number) => void;
  setZoom: (zoom: number) => void;
  updateChunk: (chunk: Chunk) => void;
  patchBase: (x: number, y: number, buildings: unknown[], roads: unknown[]) => void;
  patchLayers: (x: number, y: number, layers: Chunk["layers"]) => void;
  removeChunk: (key: string) => void;
  clearChunks: () => void;
};

export const useViewportStore = create<ViewportState>()(
  subscribeWithSelector((set) => ({
    chunkX: 0,
    chunkY: 0,
    zoom: 1,
    loadedChunks: new Map(),

    setViewport: (chunkX, chunkY) => set({ chunkX, chunkY }),
    setZoom: (zoom) => set({ zoom }),
    updateChunk: (chunk) =>
      set((state) => {
        const key = `${chunk.coordinates.x},${chunk.coordinates.y}`;
        const next = new Map(state.loadedChunks);
        next.set(key, chunk);
        return { loadedChunks: next };
      }),
    patchBase: (x, y, buildings, roads) =>
      set((state) => {
        const key = `${x},${y}`;
        const existing = state.loadedChunks.get(key);
        if (!existing) return {};
        const next = new Map(state.loadedChunks);
        next.set(key, { ...existing, base: { ...existing.base, buildings, roads } });
        return { loadedChunks: next };
      }),
    patchLayers: (x, y, layers) =>
      set((state) => {
        const key = `${x},${y}`;
        const existing = state.loadedChunks.get(key);
        if (!existing) return {};
        const next = new Map(state.loadedChunks);
        next.set(key, { ...existing, layers });
        return { loadedChunks: next };
      }),
    removeChunk: (key) =>
      set((state) => {
        const next = new Map(state.loadedChunks);
        next.delete(key);
        return { loadedChunks: next };
      }),
    clearChunks: () => set({ loadedChunks: new Map() }),
  }))
);
