import Phaser from "phaser";
import { ChunkManager } from "./ChunkManager";
import type { ViewMode } from "./ChunkManager";
import { cameraBoundsToChunkBbox } from "./coords";
import { useViewportStore } from "../stores/viewportStore";
import { useCityStore } from "../stores/cityStore";
import { emitUpdateViewport } from "../socket";

export class GameScene extends Phaser.Scene {
  private chunkManager!: ChunkManager;
  private cityId: string | null = null;
  private lastBbox: string = "";
  private lastViewportEmit: number = 0;
  private readonly THROTTLE_MS = 150;

  // Unsubscribe callbacks for Zustand subscriptions
  private unsubChunks?: () => void;
  private unsubViewMode?: () => void;

  constructor() {
    super({ key: "GameScene" });
  }

  init(data: { cityId?: string }) {
    this.cityId = data.cityId ?? null;
  }

  create() {
    this.chunkManager = new ChunkManager(this);

    // Camera setup
    this.cameras.main.setBounds(-16384, -16384, 32768, 32768);
    this.input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
      if (pointer.isDown) {
        this.cameras.main.scrollX -= pointer.velocity.x / this.cameras.main.zoom;
        this.cameras.main.scrollY -= pointer.velocity.y / this.cameras.main.zoom;
      }
    });

    // Mouse wheel zoom
    this.input.on(
      "wheel",
      (
        _pointer: Phaser.Input.Pointer,
        _gameObjects: unknown,
        _deltaX: number,
        deltaY: number
      ) => {
        const cam = this.cameras.main;
        const newZoom = Phaser.Math.Clamp(cam.zoom - deltaY * 0.001, 0.25, 2);
        cam.setZoom(newZoom);
      }
    );

    // Subscribe to loadedChunks changes
    this.unsubChunks = useViewportStore.subscribe(
      (state) => state.loadedChunks,
      (loadedChunks, prevLoadedChunks) => {
        const viewMode = useCityStore.getState().activeViewMode as ViewMode;

        // Remove chunks that were unloaded
        for (const key of prevLoadedChunks.keys()) {
          if (!loadedChunks.has(key)) {
            this.chunkManager.removeChunk(key);
          }
        }

        // Render chunks that are new or changed
        for (const [key, chunk] of loadedChunks) {
          const prev = prevLoadedChunks.get(key);
          if (!prev || prev !== chunk) {
            this.chunkManager.renderChunk(chunk, viewMode);
          }
        }
      }
    );

    // Subscribe to activeViewMode changes — re-render all chunks
    this.unsubViewMode = useCityStore.subscribe(
      (state) => state.activeViewMode,
      (viewMode) => {
        const chunks = useViewportStore.getState().loadedChunks;
        this.chunkManager.renderAll(chunks, viewMode as ViewMode);
      }
    );
  }

  update(_time: number, _delta: number) {
    if (!this.cityId) return;

    const now = Date.now();
    if (now - this.lastViewportEmit < this.THROTTLE_MS) return;

    const cam = this.cameras.main;
    const wv = cam.worldView;
    const bbox = cameraBoundsToChunkBbox(wv.left, wv.top, wv.right, wv.bottom);
    const bboxStr = `${bbox.min_x},${bbox.min_y},${bbox.max_x},${bbox.max_y}`;

    if (bboxStr !== this.lastBbox) {
      this.lastBbox = bboxStr;
      this.lastViewportEmit = now;
      emitUpdateViewport(this.cityId, bbox);
    }
  }

  shutdown() {
    this.unsubChunks?.();
    this.unsubViewMode?.();
    this.chunkManager.destroy();
  }
}
