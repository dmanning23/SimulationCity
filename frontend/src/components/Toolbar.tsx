import { useCityStore } from "../stores/cityStore";
import type { ViewMode } from "../stores/cityStore";

const TOOLS = [
  { label: "R", title: "Residential zone" },
  { label: "C", title: "Commercial zone" },
  { label: "I", title: "Industrial zone" },
  { label: "🛣️", title: "Road" },
  { label: "⚡", title: "Power line" },
  { label: "🔨", title: "Demolish" },
];

const VIEW_MODES: { label: string; mode: ViewMode }[] = [
  { label: "Base", mode: "base" },
  { label: "⚡", mode: "electricity" },
  { label: "🌫️", mode: "pollution" },
  { label: "💧", mode: "water" },
];

const pillStyle: React.CSSProperties = {
  position: "absolute",
  bottom: 16,
  left: "50%",
  transform: "translateX(-50%)",
  background: "rgba(22, 27, 34, 0.9)",
  backdropFilter: "blur(8px)",
  border: "1px solid rgba(48, 54, 61, 0.8)",
  borderRadius: 24,
  padding: "8px 16px",
  display: "flex",
  alignItems: "center",
  gap: 4,
  pointerEvents: "none",
};

const toolBtnStyle: React.CSSProperties = {
  background: "#21262d",
  border: "1px solid #30363d",
  borderRadius: 6,
  padding: "6px 10px",
  color: "#8b949e",
  fontFamily: "monospace",
  fontSize: 12,
  cursor: "default",
};

const dividerStyle: React.CSSProperties = {
  width: 1,
  height: 24,
  background: "#30363d",
  margin: "0 6px",
};

export function Toolbar() {
  const activeViewMode = useCityStore((s) => s.activeViewMode);

  return (
    <div style={pillStyle}>
      {/* Tool group — display only */}
      {TOOLS.map((tool) => (
        <div key={tool.label} style={toolBtnStyle} title={tool.title}>
          {tool.label}
        </div>
      ))}

      <div style={dividerStyle} />

      {/* View mode group — interactive */}
      <div style={{ display: "flex", gap: 4, pointerEvents: "auto" }}>
        {VIEW_MODES.map(({ label, mode }) => {
          const isActive = activeViewMode === mode;
          return (
            <button
              key={mode}
              data-testid={`viewmode-${mode}`}
              onClick={() => useCityStore.getState().setViewMode(mode)}
              style={{
                background: isActive ? "#1d4ed8" : "#21262d",
                border: `1px solid ${isActive ? "#3b82f6" : "#30363d"}`,
                borderRadius: 6,
                padding: "6px 10px",
                color: isActive ? "#93c5fd" : "#8b949e",
                fontFamily: "monospace",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
