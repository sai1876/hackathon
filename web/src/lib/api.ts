import type { Coordinate, Health, Incident, RouteResult } from "@/types/aegis";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export async function request<T>(path: string, init: RequestInit = {}, timeout = 180000): Promise<T> {
  const signal = init.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout);
  let response: Response;
  try { response = await fetch(`${API_URL}${path}`, { ...init, signal, cache: "no-store", headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers } }); }
  catch (error) {
    if (init.signal?.aborted) throw error;
    throw new Error(signal.aborted ? "Request timed out. A cold graph load can take several minutes; try again." : "Cannot reach the backend. Check the API service and CORS configuration.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}). Check your input and retry.`);
  }
  return response.json() as Promise<T>;
}
export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }, 10000),
  incidents: (signal?: AbortSignal) => request<Incident[]>("/incidents", { signal }),
  route: (start: Coordinate, end: Coordinate, signal?: AbortSignal) => request<RouteResult>("/route", { method: "POST", body: JSON.stringify({ start, end }), signal }),
  inject: (point: Coordinate) => request<Incident>("/incidents", { method: "POST", body: JSON.stringify({ ...point, incident_type: "ROAD_BLOCKAGE", severity: 3, provenance: "SYNTHETIC", description: "SYNTHETIC operator-injected traffic exercise" }) }),
  resolve: (id: string) => request<{ status: string }>(`/incidents/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
