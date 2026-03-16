import { io, Socket } from "socket.io-client";

import { useCityStore } from "./stores/cityStore";
import type { GlobalStats } from "./stores/cityStore";
import type { Chunk } from "./stores/viewportStore";
import { useViewportStore } from "./stores/viewportStore";

let socket: Socket | null = null;

export function initSocket(token: string): Socket {
  if (socket) socket.disconnect();

  socket = io(import.meta.env.VITE_SOCKET_URL ?? "", {
    auth: { token },
    transports: ["websocket", "polling"],
  });

  socket.on("connect", () => console.log("[socket] connected"));
  socket.on("disconnect", () => console.log("[socket] disconnected"));
  socket.on("connect_error", (err) =>
    console.error("[socket] connection error:", err.message)
  );

  socket.on("chunk_update", ({ chunk }: { chunk: Chunk }) => {
    useViewportStore.getState().updateChunk(chunk);
  });

  socket.on("city_stats_update", ({ stats }: { stats: GlobalStats }) => {
    useCityStore.getState().setGlobalStats(stats);
  });

  socket.on(
    "initial_state",
    (data: { city: { id: string; name: string; global_stats: GlobalStats }; chunks: Chunk[] }) => {
      useCityStore.getState().setCityId(data.city.id, data.city.name);
      useCityStore.getState().setGlobalStats(data.city.global_stats);
      data.chunks.forEach((chunk) => useViewportStore.getState().updateChunk(chunk));
    }
  );

  socket.on("error", ({ message }: { message: string }) => {
    console.error("[socket] server error:", message);
  });

  return socket;
}

export const getSocket = (): Socket | null => socket;

export function disconnectSocket(): void {
  socket?.disconnect();
  socket = null;
}
