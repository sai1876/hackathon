import type { Coordinate, Incident, RouteResult } from "./aegis";
export type Corridor = {
  id: string; ambulance_id: string; destination_name: string; priority: string;
  start: Coordinate; end: Coordinate; position: Coordinate; position_at: string; position_provenance: string;
  provenance: string; status: "PENDING" | "APPROVED" | "REJECTED" | "COMPLETED";
  version: number; created_at: string; updated_at: string;
  route: RouteResult | null; route_state: string; route_error: string | null;
  eta_change_seconds: number; initial_eta_seconds?: number;
  decisions: { decision: string; operator: string; reason: string; at: string }[];
};
export type OperationsSnapshot = {
  weather_zones?: { id: string; factor: number }[];
  revision: number; server_time: string; storage: string;
  corridors: Corridor[]; incidents: Incident[];
  exercises: { id: string; incident_id: string; status: string; created_at: string; provenance: string }[];
  events: { id: number; at: string; kind: string; subject: string; detail: string; actor: string; provenance: string }[];
  recommendations: { id: string; subject: string; action: string; evidence: string; consequence: string; provenance: string }[];
  provenance: { roads: string; routing: string; telemetry: string; persistence: string };
};
