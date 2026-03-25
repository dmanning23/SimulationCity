import Phaser from "phaser";
import { TILE_W, TILE_H, CHUNK_SIZE, tileToWorld } from "./coords";
import type { Chunk } from "../stores/viewportStore";

export type ViewMode = "base" | "electricity" | "pollution" | "water";

/**
 * Manages one Phaser.GameObjects.Graphics per loaded chunk.
 * Redraws tiles as isometric diamonds with placeholder colors.
 */
export class ChunkManager {
  private scene: Phaser.Scene;
  private graphics: Map<string, Phaser.GameObjects.Graphics> = new Map();

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
  }

  /**
   * Render or re-render a single chunk.
   * Creates a Graphics object if one doesn't exist yet.
   */
  renderChunk(chunk: Chunk, viewMode: ViewMode): void {
    const key = `${chunk.coordinates.x},${chunk.coordinates.y}`;
    let gfx = this.graphics.get(key);
    if (!gfx) {
      gfx = this.scene.add.graphics();
      this.graphics.set(key, gfx);
    }
    gfx.clear();

    const chunkOriginTileX = chunk.coordinates.x * CHUNK_SIZE;
    const chunkOriginTileY = chunk.coordinates.y * CHUNK_SIZE;

    for (let lx = 0; lx < CHUNK_SIZE; lx++) {
      for (let ly = 0; ly < CHUNK_SIZE; ly++) {
        const tx = chunkOriginTileX + lx;
        const ty = chunkOriginTileY + ly;
        const { x, y } = tileToWorld(tx, ty);
        const color = this.getTileColor(chunk, lx, ly, viewMode);

        gfx.fillStyle(color, 1);
        gfx.lineStyle(1, 0x111111, 0.5);

        // Draw isometric diamond
        gfx.beginPath();
        gfx.moveTo(x, y);                          // top
        gfx.lineTo(x + TILE_W / 2, y + TILE_H / 2);  // right
        gfx.lineTo(x, y + TILE_H);                 // bottom
        gfx.lineTo(x - TILE_W / 2, y + TILE_H / 2);  // left
        gfx.closePath();
        gfx.fillPath();
        gfx.strokePath();
      }
    }
  }

  /**
   * Re-render all loaded chunks (e.g., when view mode changes).
   */
  renderAll(chunks: Map<string, Chunk>, viewMode: ViewMode): void {
    for (const chunk of chunks.values()) {
      this.renderChunk(chunk, viewMode);
    }
  }

  /**
   * Remove and destroy the Graphics object for a chunk.
   */
  removeChunk(key: string): void {
    const gfx = this.graphics.get(key);
    if (gfx) {
      gfx.destroy();
      this.graphics.delete(key);
    }
  }

  /**
   * Destroy all graphics objects.
   */
  destroy(): void {
    for (const gfx of this.graphics.values()) {
      gfx.destroy();
    }
    this.graphics.clear();
  }

  // ---- Private color logic ----

  private getTileColor(chunk: Chunk, lx: number, ly: number, viewMode: ViewMode): number {
    switch (viewMode) {
      case "base":
        return this.getBaseColor(chunk);
      case "electricity":
        return this.getElectricityColor(chunk);
      case "pollution":
        return this.getPollutionColor(chunk);
      case "water":
        return this.getWaterColor(chunk);
      default:
        return 0x4a7c59;
    }
  }

  /** Base mode: chunk-level heuristic (not per-tile) */
  private getBaseColor(chunk: Chunk): number {
    if (chunk.base.buildings.length > 0) return 0x6b7280;  // building present
    if (chunk.base.roads.length > 0) return 0x374151;      // road present
    return 0x4a7c59;                                         // grass
  }

  /** Electricity: powered vs unpowered based on coverage field presence */
  private getElectricityColor(chunk: Chunk): number {
    const coverage = (chunk.layers.electricity as { coverage?: number }).coverage ?? 0;
    return coverage > 0 ? 0xf59e0b : 0x1f2937;
  }

  /** Pollution: clean / moderate / heavy */
  private getPollutionColor(chunk: Chunk): number {
    const coverage = (chunk.layers.pollution as { coverage?: number }).coverage ?? 0;
    if (coverage > 0.6) return 0xef4444;   // heavy
    if (coverage > 0.25) return 0xeab308;  // moderate
    return 0x22c55e;                        // clean
  }

  /** Water: covered vs no water */
  private getWaterColor(chunk: Chunk): number {
    const coverage = (chunk.layers.water as { coverage?: number }).coverage ?? 0;
    return coverage > 0 ? 0x3b82f6 : 0x92400e;
  }
}
