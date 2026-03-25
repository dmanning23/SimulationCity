import Phaser from "phaser";
import { GameScene } from "./GameScene";

export interface PhaserGameConfig {
  parent: HTMLElement;
  cityId?: string;
}

export function createPhaserGame({ parent, cityId }: PhaserGameConfig): Phaser.Game {
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    backgroundColor: "#111827",
    scene: [], // empty — scene is added and started manually once the game is ready
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });

  // Add and start GameScene exactly once with cityId data, avoiding double-init.
  // scene.add(key, SceneClass, autoStart, initData) passes data directly to init().
  game.events.once("ready", () => {
    game.scene.add("GameScene", GameScene, true, { cityId: cityId ?? null });
  });

  return game;
}
