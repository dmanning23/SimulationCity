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
    scene: [GameScene],
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  });

  // Pass cityId to the scene once the game is ready.
  // GameScene.init(data) will receive { cityId }.
  if (cityId) {
    game.events.once("ready", () => {
      game.scene.start("GameScene", { cityId });
    });
  }

  return game;
}
