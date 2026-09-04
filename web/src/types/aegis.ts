import type { Feature, FeatureCollection, LineString } from "geojson";
export type Coordinate = { lat: number; lon: number; target_edge_id?: string };
export type MapMode = "start" | "destination" | "incident" | "inspect";
export type EndpointSnap = { requested: Coordinate; snapped: Coordinate; distance_m: number };
export type Incident = Coordinate & {
  id: string; incident_type: string; severity: number; status: string;
  closure_scope?: string; match_source?: string; match_distance_m?: number; matched_edge_id?: string;
  provenance: string; created_at: string; affected_edges: string[];
  affected_geometry?: LineString | null;
};
export type RouteResult = {
  snapping: { method: "ROAD_SEGMENT"; max_distance_m: number; start: EndpointSnap; end: EndpointSnap };
  endpoint_snap_ms: number;
  start_node: string; end_node: string; distance_m: number; distance_km: number;
  eta_seconds: number; eta_minutes: number; graph_load_ms: number;
  nearest_node_ms: number; route_compute_ms: number; total_ms: number; cache_hit: boolean;
  route_edges: { external_id: string; road_name: string | null }[];
  route_segments?: FeatureCollection<LineString, { external_id: string; road_name: string | null }>;
  route: Feature<LineString, { engine: string; source: string }>;
  incidents: Incident[];
};
export type Health = { status: string; routing_engine: string; database: string; road_source: string };
