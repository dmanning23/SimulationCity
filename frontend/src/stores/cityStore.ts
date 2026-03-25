import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export type ViewMode = "base" | "electricity" | "pollution" | "water";

export interface GlobalStats {
  population: number;
  happiness: number;
  treasury: number;
}

interface CityStore {
  cityId: string | null;
  cityName: string | null;
  globalStats: GlobalStats;
  activeViewMode: ViewMode;
  setCityId: (id: string | null, name?: string | null) => void;
  setGlobalStats: (stats: Partial<GlobalStats>) => void;
  setViewMode: (mode: ViewMode) => void;
  clearCity: () => void;
}

export const useCityStore = create<CityStore>()(
  subscribeWithSelector((set) => ({
    cityId: null,
    cityName: null,
    globalStats: { population: 0, happiness: 50, treasury: 10000 },
    activeViewMode: "base",

    setCityId: (cityId, cityName = null) => set({ cityId, cityName }),
    setGlobalStats: (stats) =>
      set((state) => ({ globalStats: { ...state.globalStats, ...stats } })),
    setViewMode: (activeViewMode) => set({ activeViewMode }),
    clearCity: () =>
      set({
        cityId: null,
        cityName: null,
        globalStats: { population: 0, happiness: 50, treasury: 10000 },
        activeViewMode: "base",
      }),
  }))
);
