export const TILE_W = 128;  // px — isometric tile width
export const TILE_H = 64;   // px — isometric tile height (TILE_W / 2)
export const CHUNK_SIZE = 16;  // tiles per chunk side

/** Convert tile grid coordinates to Phaser world (px) coordinates. */
export function tileToWorld(tx: number, ty: number): { x: number; y: number } {
  return {
    x: (tx - ty) * (TILE_W / 2),
    y: (tx + ty) * (TILE_H / 2),
  };
}

/**
 * Convert Phaser world (px) coordinates back to tile grid coordinates.
 * Rounds to the nearest integer tile.
 */
export function worldToTile(x: number, y: number): { tx: number; ty: number } {
  return {
    tx: Math.round((x / (TILE_W / 2) + y / (TILE_H / 2)) / 2),
    ty: Math.round((y / (TILE_H / 2) - x / (TILE_W / 2)) / 2),
  };
}

/**
 * Convert a Phaser camera worldView bounding box to a chunk-coordinate bbox.
 * Adds ±1 chunk padding to avoid edge popping on fast scrolls.
 * min values are NOT clamped — the server decides which chunks exist.
 */
export function cameraBoundsToChunkBbox(
  worldX: number,
  worldY: number,
  worldRight: number,
  worldBottom: number
): { min_x: number; min_y: number; max_x: number; max_y: number } {
  // Convert all four corners to tile coords
  const corners = [
    worldToTile(worldX, worldY),
    worldToTile(worldRight, worldY),
    worldToTile(worldX, worldBottom),
    worldToTile(worldRight, worldBottom),
  ];

  const minTx = Math.min(...corners.map((c) => c.tx));
  const maxTx = Math.max(...corners.map((c) => c.tx));
  const minTy = Math.min(...corners.map((c) => c.ty));
  const maxTy = Math.max(...corners.map((c) => c.ty));

  // No clamp to zero — the server handles chunk existence; the client requests whatever
  // the camera sees, including negative indices for worlds that extend left/above origin.
  return {
    min_x: Math.floor(minTx / CHUNK_SIZE) - 1,
    min_y: Math.floor(minTy / CHUNK_SIZE) - 1,
    max_x: Math.ceil(maxTx / CHUNK_SIZE) + 1,
    max_y: Math.ceil(maxTy / CHUNK_SIZE) + 1,
  };
}
