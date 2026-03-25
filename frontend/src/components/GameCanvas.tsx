import { useEffect, useRef } from "react";
import { createPhaserGame } from "../game/PhaserGame";
import { initSocket } from "../socket";
import type Phaser from "phaser";

interface GameCanvasProps {
  cityId?: string;
}

export function GameCanvas({ cityId }: GameCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    if (!containerRef.current || gameRef.current) return;

    if (cityId) {
      initSocket(cityId);
    }

    gameRef.current = createPhaserGame({
      parent: containerRef.current,
      cityId,
    });

    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []); // cityId intentionally omitted — game is created once

  return (
    <div
      ref={containerRef}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 0,
      }}
    />
  );
}
