import { StatsBar } from "./StatsBar";
import { PlayerList } from "./PlayerList";
import { Toolbar } from "./Toolbar";

export function HUD() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10,
        pointerEvents: "none",
      }}
    >
      <StatsBar />
      <PlayerList />
      <Toolbar />
    </div>
  );
}
