import { usePlayerStore } from "../stores/playerStore";

const AVATAR_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444"];

function avatarColor(userId: string): string {
  const sum = userId.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

export function PlayerList() {
  const collaborators = usePlayerStore((s) => s.collaborators);

  if (collaborators.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        right: 12,
        pointerEvents: "none",
        background: "rgba(22, 27, 34, 0.85)",
        backdropFilter: "blur(8px)",
        border: "1px solid rgba(48, 54, 61, 0.8)",
        borderRadius: 8,
        padding: "6px 12px",
        display: "flex",
        gap: 10,
        alignItems: "center",
      }}
    >
      {collaborators.map((c) => (
        <div
          key={c.userId}
          style={{ display: "flex", alignItems: "center", gap: 5 }}
        >
          <div
            data-avatar="true"
            style={{
              width: 22,
              height: 22,
              borderRadius: "50%",
              backgroundColor: avatarColor(c.userId),
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              color: "#fff",
              fontFamily: "monospace",
            }}
          >
            {c.username[0]}
          </div>
          <span style={{ color: "#e6edf3", fontFamily: "monospace", fontSize: 12 }}>
            {c.username}
          </span>
        </div>
      ))}
    </div>
  );
}
