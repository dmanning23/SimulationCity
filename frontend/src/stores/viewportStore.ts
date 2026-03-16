import { create } from "zustand";

export interface Chunk {
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
}

interface ViewportStore {
  chunkX: number;
  chunkY: number;
  zoom: number;
  loadedChunks: Map<string, Chunk>;
  setViewport: (x: number, y: number) => void;
  setZoom: (zoom: number) => void;
  updateChunk: (chunk: Chunk) => void;
  clearChunks: () => void;
}

export const useViewportStore = create<ViewportStore>((set) => ({
  chunkX: 0,
  chunkY: 0,
  zoom: 1,
  loadedChunks: new Map(),

  setViewport: (chunkX, chunkY) => set({ chunkX, chunkY }),
  setZoom: (zoom) => set({ zoom }),
  updateChunk: (chunk) =>
    set((state) => {
      const key = `${chunk.coordinates.x},${chunk.coordinates.y}`;
      const updated = new Map(state.loadedChunks);
      updated.set(key, chunk);
      return { loadedChunks: updated };
    }),
  clearChunks: () => set({ loadedChunks: new Map() }),
}));
