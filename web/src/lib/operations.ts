// Deterministic presentation fixtures. Never used as inputs to the routing API.
import type { FeatureCollection } from "geojson";
import type { Incident, RouteResult } from "@/types/aegis";
import type { AgentStatus, Alert, DemoAsset, DepartmentRecommendation, EmergencyVehicle, FloodState, MapSelection, PowerState, Scenario, SimulationState, TrafficState } from "@/types/operations";
export const scenarios: Scenario[] = ["NORMAL", "ROAD BLOCKAGE", "ACCIDENT", "WATERLOGGING", "SIGNAL FAILURE", "AMBULANCE EVENT", "POWER FAULT"];
export const initialSimulation: SimulationState = { scenario: "WATERLOGGING", playing: false, speed: 1, tick: 0, provenance: "SYNTHETIC" };
export const agents: AgentStatus[] = ["Traffic", "Emergency", "Flood", "Grid", "Metro", "Coordination"].map((department, i) => ({ department, symbol: ["↗", "✚", "≋", "ϟ", "M", "◎"][i], state: i === 2 ? "DEMO REVIEW" : "DEMO READY", provenance: "SYNTHETIC" }));
export function demoState(sim: SimulationState) {
  const storm = sim.scenario === "WATERLOGGING", normal = sim.scenario === "NORMAL";
  const phase = Math.min(12, Math.floor(sim.tick / 3));
  const load = normal ? 34 : Math.min(94, (storm ? 72 : 61) + phase);
  const traffic: TrafficState = { load, normal: 100-load, slow: 25, congested: load-(normal ? 25 : 30), blocked: normal ? 0 : 5, provenance: "SYNTHETIC" };
  const flood: FloodState = { rainfall: storm ? 24 + phase : 0, risk: storm ? 68 + phase : 12, depth: storm ? 18 + phase : 0, forecast: storm ? 38 + phase : 0, trend: Array.from({ length: 24 }, (_, i) => storm ? Math.round(8 + i * .7 + Math.sin(i*.6)*4 + phase) : 0), provenance: "SYNTHETIC" };
  const failed = sim.scenario === "POWER FAULT" ? 3 : 0;
  const power: PowerState = { total: 86, normal: 69-failed, overloaded: 11, failed, maintenance: 6, load: sim.scenario === "POWER FAULT" ? 91 : 64, provenance: "SYNTHETIC" };
  const vehicles: EmergencyVehicle[] = [
    { id: "DEMO-21", route: "Care point A → Receiving hospital B", eta: 12 + phase, delay: normal ? 0 : 4, coordinate: [78.471,17.422], provenance: "SYNTHETIC" },
    { id: "DEMO-22", route: "Response base → East sector", eta: 9 + phase, delay: sim.scenario === "AMBULANCE EVENT" ? 7 : 0, coordinate: [78.51,17.402], provenance: "SYNTHETIC" },
  ];
  const alerts: Alert[] = normal ? [] : [
    { id: "demo-primary", title: storm ? "Waterlogging threshold exceeded" : sim.scenario.toLowerCase().replace(/\b\w/g, c => c.toUpperCase()), location: "Central exercise corridor", level: "HIGH", symbol: storm ? "≋" : "!", provenance: "SYNTHETIC", source: "Scenario fixture" },
    { id: "demo-traffic", title: "Congestion building", location: "East approach · corridor C-02", level: "MODERATE", symbol: "↗", provenance: "SYNTHETIC", source: "Scenario fixture" },
    { id: "demo-grid", title: "Transformer load warning", location: "Exercise transformer T-08", level: "MODERATE", symbol: "ϟ", provenance: "SYNTHETIC", source: "Scenario fixture" },
    { id: "demo-signal", title: "Signal inspection requested", location: "Exercise junction J-04", level: "MODERATE", symbol: "▥", provenance: "SYNTHETIC", source: "Scenario fixture" },
    { id: "demo-ambulance", title: "Ambulance delay", location: "DEMO-21 · +4 min illustrative", level: "HIGH", symbol: "✚", provenance: "SYNTHETIC", source: "Scenario fixture" },
  ];
  return { traffic, flood, power, vehicles, alerts };
}
export const demoAssets: DemoAsset[] = [
  { id: "J-04", name: "Junction J-04", kind: "signal", symbol: "▥", coordinate: [78.458,17.431], provenance: "SYNTHETIC" },
  { id: "J-09", name: "Junction J-09", kind: "signal", symbol: "▥", coordinate: [78.512,17.447], provenance: "SYNTHETIC" },
  { id: "T-08", name: "Transformer T-08", kind: "transformer", symbol: "ϟ", coordinate: [78.451,17.466], provenance: "SYNTHETIC" },
  { id: "T-12", name: "Transformer T-12", kind: "transformer", symbol: "ϟ", coordinate: [78.524,17.397], provenance: "SYNTHETIC" },
  { id: "H-01", name: "Exercise hospital A", kind: "hospital", symbol: "✚", coordinate: [78.464,17.40], provenance: "SYNTHETIC" },
  { id: "H-02", name: "Exercise hospital B", kind: "hospital", symbol: "✚", coordinate: [78.519,17.464], provenance: "SYNTHETIC" },
];
export const demoZones: FeatureCollection = { type: "FeatureCollection", features: [
  { name: "NORTH SECTOR", color: "#39b8ef", ring: [[78.425,17.442],[78.422,17.492],[78.455,17.51],[78.501,17.486],[78.495,17.448],[78.46,17.433],[78.425,17.442]] },
  { name: "EAST SECTOR", color: "#b378e8", ring: [[78.495,17.448],[78.501,17.486],[78.548,17.468],[78.554,17.401],[78.521,17.391],[78.494,17.41],[78.495,17.448]] },
  { name: "SOUTH SECTOR", color: "#e1b647", ring: [[78.453,17.403],[78.494,17.41],[78.521,17.391],[78.53,17.36],[78.48,17.345],[78.446,17.367],[78.453,17.403]] },
  { name: "WEST SECTOR", color: "#64c891", ring: [[78.425,17.442],[78.46,17.433],[78.453,17.403],[78.446,17.367],[78.407,17.385],[78.399,17.423],[78.425,17.442]] },
].map(z => ({ type: "Feature", properties: { name: z.name, color: z.color, provenance: "SYNTHETIC", meaning: "Exercise sector, not an administrative boundary" }, geometry: { type: "Polygon", coordinates: [z.ring] } })) };
export function demoRoads(sim: SimulationState): FeatureCollection {
  return { type: "FeatureCollection", features: [
    { id:"C-01", state:"normal", coords:[[78.426,17.443],[78.445,17.431],[78.458,17.431],[78.478,17.419],[78.489,17.408]] },
    { id:"C-02", state:sim.scenario === "NORMAL" ? "normal" : "congested", coords:[[78.458,17.431],[78.475,17.439],[78.493,17.442],[78.512,17.447],[78.537,17.438]] },
    { id:"C-03", state:"slow", coords:[[78.445,17.473],[78.451,17.466],[78.458,17.448],[78.458,17.431]] },
    { id:"C-04", state:sim.scenario === "NORMAL" ? "normal" : "blocked", coords:[[78.489,17.408],[78.504,17.399],[78.518,17.383]] },
    { id:"C-05", state:"normal", coords:[[78.426,17.393],[78.441,17.403],[78.464,17.40],[78.489,17.408],[78.524,17.397]] },
  ].map(r => ({ type:"Feature", properties:{ id:r.id, name:`Exercise corridor ${r.id}`, state:r.state, provenance:"SYNTHETIC" }, geometry:{type:"LineString",coordinates:r.coords} })) };
}
export const demoFlood: FeatureCollection = { type: "FeatureCollection", features: [{ type: "Feature", properties: { name: "Exercise waterlogging footprint", provenance: "SYNTHETIC" }, geometry: { type: "Polygon", coordinates: [[[78.471,17.433],[78.478,17.449],[78.493,17.446],[78.5,17.433],[78.486,17.423],[78.471,17.433]]] } }] };
export function selectionForDemo(id: string, name: string, kind: string, state: string, sim: SimulationState): MapSelection {
  const road = kind === "road";
  return { id, name, kind, status: state.toUpperCase(), baseSpeed: road ? "40 km/h" : "N/A", currentSpeed: road ? state === "blocked" ? "0 km/h" : state === "congested" ? "12 km/h" : "32 km/h" : "N/A", congestion: road ? state === "normal" ? "22%" : "78%" : "N/A", impact: road ? "Exercise capacity reduction" : "Exercise asset only", waterRisk: sim.scenario === "WATERLOGGING" ? "HIGH · demo" : "LOW · demo", etaImpact: road ? "+4 min · illustrative" : "Not calculated", affectedRoutes: "No backend routes affected", provenance: "SYNTHETIC", source: "Hand-authored demonstration geometry; not surveyed" };
}
export function recommendations(sim: SimulationState, incidents: Incident[], route: RouteResult | null): DepartmentRecommendation[] {
  const incident = incidents[0];
  const runtime: DepartmentRecommendation[] = incident ? [{ id: incident.id, department: "TRAFFIC POLICE", incident: `${incident.incident_type.replaceAll("_", " ")} · ${incident.id.slice(0,8)}`, whyThisMatters: incident.affected_edges.length ? `${incident.affected_edges.length} directed edge is blocked in the loaded routing graph.` : "This incident has not matched a road in the current graph; geographic impact is unconfirmed.", criticalLevel: "HIGH", recommendedAction: "Verify the incident location and review the backend route before approving a diversion.", whyThisSolution: "NetworkX accounts for the runtime closure; human review is still needed for safe field deployment.", expectedResult: route ? `Current computed route: ${route.distance_km.toFixed(2)} km / ${route.eta_minutes.toFixed(1)} min. No validated before/after impact estimate.` : "Impact pending a successful route calculation.", dependencies: ["Confirmed incident location", "Current route result", "Operator approval"], fallback: "If no path is available, select another endpoint or review road coverage. Do not infer a safe diversion.", confidence: "Not calibrated · rule-based advisory", evidence: [`Incident source: ${incident.provenance}`, `Backend incident ${incident.id}`, route ? `${route.route_edges.length} route edges returned by NetworkX` : "No current route result"], provenance: "DERIVED" }] : [];
  const storm = sim.scenario === "WATERLOGGING";
  return [...runtime, ...(["DISASTER RESPONSE", "POWER DISTRIBUTION", "EMERGENCY SERVICES"] as const).map((department,i): DepartmentRecommendation => ({
    id: `demo-${i}`, department, incident: [storm ? "Waterlogging in exercise corridor C-02" : `${sim.scenario} exercise readiness`, "Illustrative transformer overload T-08", "Exercise ambulance corridor delay"][i],
    whyThisMatters: ["The demo scenario represents reduced road capacity and potential access disruption.", "A simulated load increase may reduce supply resilience in the exercise sector.", "The scenario demonstrates how road disruption can affect an emergency transfer."][i],
    criticalLevel: sim.scenario === "NORMAL" ? "NORMAL" : i===1 ? "MODERATE" : "HIGH",
    recommendedAction: ["Review a drainage inspection and traffic liaison checklist.", "Request operator review of the exercise load-balancing checklist.", "Review the receiving facility and a separately verified route."][i],
    whyThisSolution: "This is a prewritten demonstration of cross-department coordination, not an AI prediction or an executable instruction.",
    expectedResult: "Illustrative readiness review only. No measured benefit or municipal action is claimed.",
    dependencies: ["Verified field observations", "Department duty officer", "Operator approval"],
    fallback: "Escalate to the duty officer; do not act on synthetic data.", confidence: "Not scored · SYNTHETIC template", evidence: [`Scenario: ${sim.scenario}`, `Exercise step: ${sim.tick}`, "No live sensor or AI model connected"], provenance: "SYNTHETIC",
  }))];
}
