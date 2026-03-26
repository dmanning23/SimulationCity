import { useCityStore } from "../stores/cityStore";

export function StatsBar() {
  const globalStats = useCityStore((s) => s.globalStats);

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        pointerEvents: "none",
        background: "rgba(22, 27, 34, 0.85)",
        backdropFilter: "blur(8px)",
        border: "1px solid rgba(48, 54, 61, 0.8)",
        borderRadius: 8,
        padding: "8px 14px",
        display: "flex",
        gap: 18,
        alignItems: "center",
      }}
    >
      <span style={{ color: "#f59e0b" }}>
        §{globalStats.treasury.toLocaleString()}
      </span>
      <span style={{ color: "#60a5fa" }}>
        👥 {globalStats.population}
      </span>
      <span style={{ color: "#34d399" }}>
        😊 {globalStats.happiness}%
      </span>
    </div>
  );
}
