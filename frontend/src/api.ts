import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
});

export function setAuthToken(token: string): void {
  api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
}

export function clearAuthToken(): void {
  delete api.defaults.headers.common["Authorization"];
}

// Auth
export const authApi = {
  register: (data: { username: string; email: string; password: string }) =>
    api.post<{ access_token: string; token_type: string }>(
      "/api/auth/register",
      data
    ),
  login: (data: { email: string; password: string }) =>
    api.post<{ access_token: string; token_type: string }>(
      "/api/auth/login",
      data
    ),
};

// Cities
export const citiesApi = {
  list: () => api.get("/api/cities"),
  create: (data: { name: string }) => api.post("/api/cities", data),
  get: (cityId: string) => api.get(`/api/cities/${cityId}`),
  update: (cityId: string, data: unknown) =>
    api.patch(`/api/cities/${cityId}`, data),
  delete: (cityId: string) => api.delete(`/api/cities/${cityId}`),
};

export default api;
