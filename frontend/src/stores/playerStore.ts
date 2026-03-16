import { create } from "zustand";

export type CollaboratorRole = "admin" | "builder" | "viewer";

export interface Collaborator {
  userId: string;
  username: string;
  role: CollaboratorRole;
}

interface PlayerStore {
  playerId: string | null;
  username: string | null;
  isPremium: boolean;
  generationCredits: number;
  collaborators: Collaborator[];
  setPlayer: (id: string, username: string, isPremium: boolean) => void;
  setCredits: (credits: number) => void;
  setCollaborators: (collaborators: Collaborator[]) => void;
  clearPlayer: () => void;
}

export const usePlayerStore = create<PlayerStore>((set) => ({
  playerId: null,
  username: null,
  isPremium: false,
  generationCredits: 0,
  collaborators: [],

  setPlayer: (playerId, username, isPremium) =>
    set({ playerId, username, isPremium }),
  setCredits: (generationCredits) => set({ generationCredits }),
  setCollaborators: (collaborators) => set({ collaborators }),
  clearPlayer: () =>
    set({
      playerId: null,
      username: null,
      isPremium: false,
      generationCredits: 0,
    }),
}));
