import { describe, it, expect } from "vitest";
import {
  tileToWorld,
  worldToTile,
  cameraBoundsToChunkBbox,
  TILE_W,
  TILE_H,
  CHUNK_SIZE,
} from "./coords";

describe("tileToWorld", () => {
  it("maps origin tile to world origin", () => {
    expect(tileToWorld(0, 0)).toEqual({ x: 0, y: 0 });
  });

  it("maps (1, 0) correctly", () => {
    // x = (1 - 0) * 64 = 64, y = (1 + 0) * 32 = 32
    expect(tileToWorld(1, 0)).toEqual({ x: TILE_W / 2, y: TILE_H / 2 });
  });

  it("maps (0, 1) correctly", () => {
    // x = (0 - 1) * 64 = -64, y = (0 + 1) * 32 = 32
    expect(tileToWorld(0, 1)).toEqual({ x: -(TILE_W / 2), y: TILE_H / 2 });
  });

  it("maps (2, 2) correctly", () => {
    expect(tileToWorld(2, 2)).toEqual({ x: 0, y: TILE_H * 2 });
  });
});

describe("worldToTile", () => {
  it("roundtrips with tileToWorld for origin", () => {
    const world = tileToWorld(0, 0);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: 0, ty: 0 });
  });

  it("roundtrips with tileToWorld for (3, 5)", () => {
    const world = tileToWorld(3, 5);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: 3, ty: 5 });
  });

  it("roundtrips with tileToWorld for negative tile (camera left of origin)", () => {
    const world = tileToWorld(-2, 0);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: -2, ty: 0 });
  });

  it("roundtrips with tileToWorld for (0, -3)", () => {
    const world = tileToWorld(0, -3);
    expect(worldToTile(world.x, world.y)).toEqual({ tx: 0, ty: -3 });
  });
});

describe("cameraBoundsToChunkBbox", () => {
  it("returns chunk 0,0 for world origin area", () => {
    // Small rect around origin — well within chunk (0,0)
    const bbox = cameraBoundsToChunkBbox(-100, -50, 100, 50);
    expect(bbox.min_x).toBeLessThanOrEqual(0);
    expect(bbox.min_y).toBeLessThanOrEqual(0);
    expect(bbox.max_x).toBeGreaterThanOrEqual(0);
    expect(bbox.max_y).toBeGreaterThanOrEqual(0);
  });

  it("min_x <= max_x and min_y <= max_y always", () => {
    const bbox = cameraBoundsToChunkBbox(0, 0, 1920, 1080);
    expect(bbox.min_x).toBeLessThanOrEqual(bbox.max_x);
    expect(bbox.min_y).toBeLessThanOrEqual(bbox.max_y);
  });

  it("larger viewport covers more chunks", () => {
    const small = cameraBoundsToChunkBbox(-100, -50, 100, 50);
    const large = cameraBoundsToChunkBbox(-2000, -1000, 2000, 1000);
    const smallSpan = (small.max_x - small.min_x) * (small.max_y - small.min_y);
    const largeSpan = (large.max_x - large.min_x) * (large.max_y - large.min_y);
    expect(largeSpan).toBeGreaterThan(smallSpan);
  });

  it("constants are correct values", () => {
    expect(TILE_W).toBe(128);
    expect(TILE_H).toBe(64);
    expect(CHUNK_SIZE).toBe(16);
  });
});
