import { io, Socket } from "socket.io-client";

import { useCityStore } from "./stores/cityStore";
import type { Chunk } from "./stores/viewportStore";
import { useViewportStore } from "./stores/viewportStore";
import { usePlayerStore } from "./stores/playerStore";
import type { CollaboratorRole } from "./stores/playerStore";

let socket: Socket | null = null;

export function initSocket(cityId: string): Socket {
  if (socket) socket.disconnect();

  let token = "";
  try {
    token = localStorage.getItem("token") ?? "";
  } catch {
    // localStorage unavailable (e.g. test environment)
  }

  socket = io(import.meta.env.VITE_SOCKET_URL ?? "", {
    auth: { token },
    transports: ["websocket", "polling"],
  });

  socket.on("connect", () => console.log("[socket] connected"));
  socket.on("disconnect", () => console.log("[socket] disconnected"));
  socket.on("connect_error", (err) =>
    console.error("[socket] connection error:", err.message)
  );

  socket.on(
    "initial_state",
    (data: {
      city_id: string;
      city: {
        collaborators?: Array<{ user_id: string; username: string; role: string }>;
      };
    }) => {
      if (data.city?.collaborators) {
        usePlayerStore.getState().setCollaborators(
          data.city.collaborators.map((c) => ({
            userId: c.user_id,
            username: c.username,
            role: c.role as CollaboratorRole,
          }))
        );
      }
    }
  );

  socket.on("viewport_seed", (data: { chunks: Chunk[] }) => {
    data.chunks.forEach((chunk) => useViewportStore.getState().updateChunk(chunk));
  });

  socket.on(
    "chunk_update",
    (data: { city_id: string; chunk_x: number; chunk_y: number; buildings: unknown[]; roads: unknown[] }) => {
      useViewportStore.getState().patchBase(data.chunk_x, data.chunk_y, data.buildings, data.roads);
    }
  );

  socket.on(
    "layers_update",
    (data: { city_id: string; chunk_x: number; chunk_y: number; layers: Chunk["layers"] }) => {
      useViewportStore.getState().patchLayers(data.chunk_x, data.chunk_y, data.layers);
    }
  );

  socket.on(
    "stats_update",
    (data: { population: number; treasury: number; happiness: number }) => {
      useCityStore.getState().setGlobalStats(data);
    }
  );

  socket.on(
    "player_joined",
    (data: { user_id: string; username: string; role: string }) => {
      const { collaborators } = usePlayerStore.getState();
      const already = collaborators.some((c) => c.userId === data.user_id);
      if (!already) {
        usePlayerStore.getState().setCollaborators([
          ...collaborators,
          { userId: data.user_id, username: data.username, role: data.role as CollaboratorRole },
        ]);
      }
    }
  );

  socket.on("player_left", (data: { user_id: string }) => {
    const { collaborators } = usePlayerStore.getState();
    usePlayerStore.getState().setCollaborators(
      collaborators.filter((c) => c.userId !== data.user_id)
    );
  });

  socket.on("error", ({ message }: { message: string }) => {
    console.error("[socket] server error:", message);
  });

  socket.emit("join_city", { city_id: cityId, viewport: { chunkX: 0, chunkY: 0, radius: 2 } });

  return socket;
}

export function emitUpdateViewport(
  cityId: string,
  bbox: { min_x: number; min_y: number; max_x: number; max_y: number }
): void {
  socket?.emit("update_viewport", { city_id: cityId, ...bbox });
}

export const getSocket = (): Socket | null => socket;

export function disconnectSocket(): void {
  socket?.disconnect();
  socket = null;
}
