import { GameCanvas } from "./components/GameCanvas";
import { HUD } from "./components/HUD";

export default function App() {
  const cityId = new URLSearchParams(window.location.search).get("city") ?? undefined;
  return (
    <>
      <GameCanvas cityId={cityId} />
      <HUD />
    </>
  );
}
