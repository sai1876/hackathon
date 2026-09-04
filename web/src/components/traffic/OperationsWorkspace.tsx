"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { command, useOperations } from "@/lib/dispatch";
import type { Coordinate, MapMode } from "@/types/aegis";
import type { Corridor } from "@/types/dispatch";
import "./dispatch.css";
import ScenarioControls from "@/components/command/ScenarioControls";
import "@/components/command/main-command.css";
import RouteCalibration from "./RouteCalibration";
const TrafficMap = dynamic(() => import("./TrafficMap"), { ssr: false, loading: () => <div className="map-shell map-loading">Loading operational map…</div> });
const timestamp = (value: string) => new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false });
const coord = (value: Coordinate) => `${value.lat.toFixed(5)}, ${value.lon.toFixed(5)}`;
const noop = () => {};
export default function OperationsWorkspace({ ambulance = false }: { ambulance?: boolean }) {
  const { data, busy, error, connectionError, act, refresh } = useOperations();
  const [selectedId, setSelectedId] = useState("");
  const [visibleId, setVisibleId] = useState("");
  const [mode, setMode] = useState<MapMode>("inspect");
  const [start, setStart] = useState<Coordinate | null>(null), [end, setEnd] = useState<Coordinate | null>(null);
  const [point, setPoint] = useState<Coordinate | null>(null);
  const [vehicle, setVehicle] = useState(""), [destination, setDestination] = useState("");
  const [priority, setPriority] = useState("URGENT");
  const synthetic = false;
  const [operator, setOperator] = useState(""), [reason, setReason] = useState("");
  const [selectedIncident, setSelectedIncident] = useState("");
  const [notice, setNotice] = useState("");
  const [reviewedVersion, setReviewedVersion] = useState(0);
  const key = useRef<{ payload: string; value: string } | null>(null);
  const corridors = data?.corridors ?? [];
  const selected = corridors.find(c => c.id === selectedId) ?? corridors.find(c => c.status === "PENDING") ?? corridors.at(-1);
  const shown = selected && (ambulance || (selected.status === "APPROVED" && visibleId === selected.id)) ? selected : undefined;
  const pending = corridors.filter(c => c.status === "PENDING"), approved = corridors.filter(c => c.status === "APPROVED");
  const incident = data?.incidents.find(i => i.id === selectedIncident);
  const pick = (value: Coordinate) => {
    if (busy) return;
    if (ambulance && mode === "start") { setStart(value); setMode("destination"); }
    else if (ambulance && mode === "destination") { setEnd(value); setMode("inspect"); }
    else if (mode === "incident") { setPoint(value); setMode("inspect"); }
  };
  const submit = async () => {
    if (!start || !end) return;
    const payload = { start, end, ambulance_id: vehicle.trim(), destination_name: destination.trim(), priority, provenance: synthetic ? "SYNTHETIC" : "OPERATOR_REPORTED" };
    const encoded = JSON.stringify(payload);
    if (key.current?.payload !== encoded) key.current = { payload: encoded, value: crypto.randomUUID() };
    const requestKey = key.current.value;
    const ok = await act(async () => {
      const created = await command<Corridor>("/corridors", { ...payload, request_key: requestKey });
      setSelectedId(created.id); setNotice("Request received by the backend. Awaiting traffic review.");
    });
    if (ok) { key.current = null; setStart(null); setEnd(null); }
  };
  const decide = (decision: string) => {
    if (!selected) return;
    void act(() => command(`/corridors/${selected.id}/decision`, { version: reviewedVersion, decision, operator: operator.trim(), reason: reason.trim() })).then(ok => { if (ok) { setReason(""); setNotice(`Corridor decision recorded: ${decision}.`); } });
  };
  const route = shown?.route ?? null;
  const mapStart = ambulance ? start ?? shown?.position ?? null : null;
  const mapEnd = ambulance ? end ?? shown?.end ?? null : null;
  const stale = !!connectionError;
  return <main className="dispatch-app">
    {!ambulance && <RouteCalibration/>}
    {!!data?.weather_zones?.length && <p className="dispatch-error" role="status">Synthetic rainfall active in {data.weather_zones.length} area(s). Intersecting roads have modeled travel delays; active corridor routes are re-evaluated when rainfall effects change.</p>}
    <header className="dispatch-header"><div><Link href="/traffic" className="dispatch-brand">AEGIS<span>GRID</span></Link><p>HYDERABAD · OPERATIONAL WORKSPACE</p></div><nav aria-label="Workspaces"><Link href="/command">Command Center</Link><Link href="/traffic" aria-current={!ambulance ? "page" : undefined}>Traffic control</Link><Link href="/ambulance" aria-current={ambulance ? "page" : undefined}>Ambulance operator</Link><Link href="/electric-command">Electric Command</Link><Link href="/lineman">Lineman</Link><Link href="/metro-command">Metro Command</Link></nav><div className={stale ? "connection stale" : "connection"}>{stale ? "BACKEND DATA STALE" : data ? "BACKEND CONNECTED" : "CONNECTING"}<small>{data ? `${timestamp(data.server_time)} IST` : "Waiting for operational state"}</small></div></header>
    <div className="dispatch-title"><div><p className="eyebrow">{ambulance ? "REQUEST / TRACK / REPORT" : "REVIEW / DECIDE / COORDINATE"}</p><h1>{ambulance ? "Ambulance corridor request" : "Traffic operations"}</h1></div><button disabled={busy} onClick={() => void refresh()}>Refresh state</button></div>
    {error && <div className="dispatch-error" role="alert">{error} {stale ? "Displayed data may be stale. Refresh before acting." : "Review the current state before retrying."}</div>}
    {notice && <div className="dispatch-notice" role="status">{notice}<button onClick={() => setNotice("")}>Dismiss</button></div>}
    <section className="dispatch-metrics" aria-label="Backend-derived metrics">{[["Awaiting review", pending.length], ["Approved corridors", approved.length], ["Active incidents", data?.incidents.length], ["Open exercises", data?.exercises.filter(e => e.status !== "RESOLVED").length]].map(([label, value]) => <div key={label}><small>{label}</small><strong>{data ? value : "—"}</strong><span>BACKEND STATE</span></div>)}</section>
    {!ambulance&&<ScenarioControls polygon={[]} drawing={false} onDraw={noop} onClear={noop} readOnly/>}
    <div className="dispatch-grid">
      <aside className="dispatch-column">
        {ambulance && <section className="dispatch-panel"><h2>Request a corridor</h2><p>Choose the pickup and destination on an imported road. Traffic approval is required before an exercise can move.</p><form onSubmit={e => { e.preventDefault(); void submit(); }}>
          <label>Ambulance identifier<input required maxLength={60} value={vehicle} onChange={e => setVehicle(e.target.value)} placeholder="Enter vehicle identifier" /></label>
          <label>Destination name<input required maxLength={120} value={destination} onChange={e => setDestination(e.target.value)} placeholder="Hospital or receiving facility" /></label>
          <label>Priority<select value={priority} onChange={e => setPriority(e.target.value)}><option>CRITICAL</option><option>URGENT</option><option>TRANSFER</option></select></label>
          <div className="dispatch-buttons"><button type="button" disabled={busy} aria-pressed={mode === "start"} onClick={() => setMode("start")}>Pick pickup</button><button type="button" disabled={busy} aria-pressed={mode === "destination"} onClick={() => setMode("destination")}>Pick destination</button></div>
          <p>Pickup: {start ? coord(start) : "Not selected"}<br />Destination: {end ? coord(end) : "Not selected"}</p>

          <button className="primary-action" disabled={busy || stale || !data || !start || !end || !vehicle.trim() || !destination.trim()} type="submit">{busy ? "Sending…" : "Request corridor"}</button>
        </form></section>}
        <section className="dispatch-panel"><h2>{ambulance ? "Corridor status" : "Corridor requests"}<span>{corridors.length}</span></h2>{!corridors.length && <p>{data ? "No corridor requests. Ambulance operators can submit from the Ambulance page." : "Loading requests…"}</p>}
          <div className="request-list">{[...corridors].reverse().map(c => <button key={c.id} className={`request-card ${selected?.id === c.id ? "selected" : ""}`} onClick={() => { setSelectedId(c.id); setReason(""); }}><span className={`state state-${c.status.toLowerCase()}`}>{c.status}</span><strong>{c.ambulance_id}</strong><span>{c.destination_name} · {c.priority}</span><small>{c.provenance} · v{c.version}</small></button>)}</div>
        </section>
        {!ambulance && <section className="dispatch-panel provenance-panel"><h2>Data provenance</h2><p>Roads: imported OpenStreetMap geometry.</p><p>Routes and ETAs: NetworkX calculations using road hierarchy, turns and available measured speeds. Missing traffic readings use modeled free flow.</p><p>Weather, signal phases and demand: <b>shared database simulation</b>. Live traffic counts and GPS are not connected.</p><p>Requests and decisions: operator inputs. Exercises: explicitly synthetic.</p><p>Runtime records reset on backend restart. Single backend worker required.</p></section>}
      </aside>
      <div className="dispatch-column dispatch-center">
        <section className="map-workspace"><div className="selection-bar">{mode === "start" ? "Click a road for the pickup location" : mode === "destination" ? "Click a road for the destination" : mode === "incident" ? "Click a road for the event location" : "Inspect roads, incidents and approved corridors"}<button onClick={() => setMode("inspect")}>Inspect</button></div>
          <TrafficMap start={mapStart} end={mapEnd} route={start || end ? null : route} incidents={data?.incidents ?? []} mode={mode} onPick={pick} selected={null} target={point} onSelect={noop} onIncidentSelect={setSelectedIncident} ambulances={shown ? [{ id: shown.ambulance_id, position: shown.position, provenance: shown.position_provenance }] : []} />
          <div className="map-footer"><span>OSM GEOMETRY · COVERAGE SNAPSHOT</span><span>{shown ? `${shown.ambulance_id} · ${shown.position_provenance} LOCATION` : "NO AMBULANCE OVERLAY SELECTED"}</span></div>
        </section>
        {selected ? <section className="dispatch-panel corridor-detail"><h2>{selected.ambulance_id} → {selected.destination_name}<span className={`state state-${selected.status.toLowerCase()}`}>{selected.status}</span></h2><p className="dispatch-meta">Request {selected.id} · version {selected.version} · {selected.provenance}</p>
          <div className="corridor-facts"><div><small>Remaining modeled ETA</small><strong>{selected.status === "COMPLETED" ? "Closed" : selected.route ? `${selected.route.eta_minutes.toFixed(1)} min` : "Unavailable"}</strong></div><div><small>Route distance</small><strong>{selected.route ? `${selected.route.distance_km.toFixed(2)} km` : "—"}</strong></div><div><small>Change at last route evaluation</small><strong>{selected.route ? `${selected.eta_change_seconds > 0 ? "+" : ""}${selected.eta_change_seconds} s` : "—"}</strong></div></div>
          {selected.route_error && <p className="dispatch-error">{selected.route_error}</p>}
          {selected.route?.incidents.some(i => i.provenance === "SYNTHETIC") && <p className="dispatch-error">This route evaluation includes synthetic exercise incidents. It is not a route based only on field reports.</p>}
          {!!selected.route?.incidents.length && <details><summary>Incident inputs to this route evaluation</summary>{selected.route.incidents.map(i => <p key={i.id}>{i.incident_type} · {i.provenance} · {i.id}<br />{i.affected_edges.length ? `${i.affected_edges.length} directed edge matched in this evaluation` : "No matching edge in this evaluated graph"}</p>)}</details>}
          <p>Last reported position: {coord(selected.position)}<br /><small>{selected.position_provenance} · {timestamp(selected.position_at)} IST · not live GPS</small></p>
          {selected.route && <details><summary>Review route evidence</summary><p>{selected.route.route_edges.length} directed edges in the latest evaluated plan; computation took {selected.route.total_ms} ms. Exercise steps trim the displayed path; this list records the evaluated plan.</p><p>{selected.route.route_edges.map(e => e.road_name || e.external_id).join(" → ")}</p><p>Pickup snap offset: {selected.route.snapping.start.distance_m.toFixed(1)} m. Destination offset: {selected.route.snapping.end.distance_m.toFixed(1)} m. Offsets are not routed travel.</p></details>}
          {!ambulance && selected.status === "APPROVED" && <label className="check overlay-toggle"><input type="checkbox" checked={visibleId === selected.id} onChange={e => setVisibleId(e.target.checked ? selected.id : "")} />Show ambulance route and location on map</label>}
          {!ambulance && ["PENDING", "APPROVED"].includes(selected.status) && <div className="decision-form"><label>Traffic operator<input maxLength={80} value={operator} onChange={e => setOperator(e.target.value)} placeholder="Operator name or ID" /></label><label>Decision reason<textarea maxLength={500} value={reason} onChange={e => { setReason(e.target.value); setReviewedVersion(selected.version); }} placeholder="Record the reason for this decision" /></label>{reason && reviewedVersion !== selected.version && <p role="alert">This request changed while you were reviewing it. Review the latest route and update your decision reason.</p>}<div className="dispatch-buttons">{selected.status === "PENDING" ? <><button className="primary-action" disabled={busy || stale || !selected.route || !operator.trim() || reason.trim().length < 3 || reviewedVersion !== selected.version} onClick={() => decide("APPROVE")}>Approve corridor</button><button disabled={busy || stale || !operator.trim() || reason.trim().length < 3 || reviewedVersion !== selected.version} onClick={() => decide("REJECT")}>Reject request</button></> : <button disabled={busy || stale || !operator.trim() || reason.trim().length < 3 || reviewedVersion !== selected.version} onClick={() => decide("COMPLETE")}>Mark corridor complete</button>}</div><p>Approval records a coordination decision. Signal control and dispatch are not connected.</p></div>}
          {["PENDING", "APPROVED"].includes(selected.status) && <button disabled={busy || stale} onClick={() => void act(() => command(`/corridors/${selected.id}/reevaluate`, { version: selected.version }))}>Re-evaluate route</button>}
          {ambulance && selected.provenance !== "SYNTHETIC" && ["PENDING", "APPROVED"].includes(selected.status) && <div><p>Report a new position using a map point. A new traffic review will be required.</p><button disabled={busy} onClick={() => setMode("incident")}>Pick current location</button><button disabled={!point || busy || stale} onClick={() => void act(() => command(`/corridors/${selected.id}/position`, { ...point, version: selected.version }))}>Report {point ? coord(point) : "location"}</button></div>}
          {selected.decisions.length > 0 && <details open><summary>Decision history</summary>{selected.decisions.map((d, i) => <p key={i}><b>{d.decision}</b> · {d.operator} · {timestamp(d.at)} IST<br />{d.reason}</p>)}</details>}
        </section> : <section className="dispatch-panel"><h2>No corridor selected</h2><p>{ambulance ? "Submit a request to calculate and review its route." : "Incoming ambulance requests will appear here for review."}</p></section>}
      </div>
      <aside className="dispatch-column">
        {!ambulance && <><section className="dispatch-panel"><h2>Scenario setup</h2><p>All simulation configuration belongs in the main Command Center.</p><Link href="/command">Open Command Center</Link></section>
        <section className="dispatch-panel"><h2>Active incidents<span>{data?.incidents.length ?? "—"}</span></h2>{!data?.incidents.length && <p>No active incidents reported by the backend.</p>}{data?.incidents.map(i => <article className={`operational-incident ${incident?.id === i.id ? "selected" : ""}`} key={i.id}><button onClick={() => setSelectedIncident(i.id)}><b>{i.incident_type.replaceAll("_", " ")}</b></button><p>{i.provenance} · severity {i.severity}/5<br />{coord(i)}<br />{timestamp(i.created_at)} IST</p><p>{i.affected_edges.length ? `${i.affected_edges.length} directed edges closed on the matched physical road` : "No edge matched in latest evaluated graph; coverage or route evaluation may be missing."}</p><p>{i.match_source === "SELECTED_ROUTE_EDGE" ? "Matched to selected route segment" : "Matched to nearest road"}{i.match_distance_m !== undefined ? ` · ${i.match_distance_m.toFixed(1)} m from click` : ""} · both directions</p><button disabled={busy || stale} onClick={() => void act(() => api.resolve(i.id))}>Resolve incident</button></article>)}</section>
        <section className="dispatch-panel"><h2>Recommended actions<span>DERIVED</span></h2>{data?.recommendations.length ? data.recommendations.map(r => <article className="recommendation" key={r.id}><h3>{r.action}</h3><p>{r.evidence}</p><p>{r.consequence}</p><button onClick={() => { if (r.id.startsWith("review-")) setSelectedId(r.subject); else setSelectedIncident(r.subject); }}>Review evidence</button></article>) : <p>No actions recommended from current backend state.</p>}</section></>}
        {ambulance && <section className="dispatch-panel"><h2>How requests progress</h2><ol><li>Submit pickup and destination.</li><li>Backend calculates an available road route.</li><li>Traffic operator approves or rejects with a reason.</li><li>Approved corridors can appear on the traffic map.</li><li>A route change triggers a new review.</li></ol><p>Positions are operator-reported or synthetic. Requests persist across page refreshes, but reset when this backend restarts.</p></section>}
      </aside>
    </div>
    <section className="dispatch-panel event-journal"><h2>Operational event journal<span>SERVER STATE · {data?.revision ?? "—"}</span></h2><p>Actions and their consequences, newest first. Up to 500 process-local events. Times shown in IST.</p>{data?.events.length ? <div className="event-list">{[...data.events].reverse().map(e => <article key={e.id}><time>{timestamp(e.at)}</time><div><b>{e.kind.replaceAll("_", " ")}</b><p>{e.detail}</p><small>{e.actor} · {e.provenance} · evidence {e.subject}</small></div></article>)}</div> : <p>No events yet. Submit a corridor request or inject an exercise event.</p>}</section>
    <footer className="dispatch-bottom">Backend-derived counts and actions · Free-flow routing estimates · No live traffic or infrastructure actuation · Runtime state is process-local</footer>
  </main>;
}
