"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as maplibregl from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { request } from "@/lib/api";
import "./electric.css";
import RainControls, { type RainEffect } from "./RainControls";
import LoadControls, { type LoadTelemetry } from "./LoadControls";
import { registerElectricalSymbols, ElectricalLegend } from "./ElectricalSymbols";

type Asset = { road_context?: string; id: string; kind: string; parent: string | null; station: string; lon: number; lat: number; demand_kw: number; upstream?: string[]; children?: Asset[] };
type Task = { id: string; asset_id: string; status: string; crew: string; note: string };
type Snapshot = { rain_effects: RainEffect[]; telemetry: Record<string, LoadTelemetry>; running: boolean; speed: number; overloaded_ids: string[]; version: number; counts: Record<string, number>; off_ids: string[]; affected_stations: string[]; faults: string[]; unserved_kw: number; signals_without_supply: number; seconds: number; queues: Record<string, number>; tasks: Task[]; stations: Asset[]; events: { id: number; action: string; asset_id: string; operator: string; note: string; at: string; simulation_seconds: number }[] };
const label = (text: string) => text.replaceAll("_", " ");

function ElectricMap({ station, off, onSelect, focus, overloaded, drawing, polygon, rain, onPoint }: { drawing: boolean; polygon: [number, number][]; rain: RainEffect[]; onPoint: (point: [number, number]) => void; overloaded: string[]; focus: Asset | null; station: string; off: string[]; onSelect: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const latest = useRef({ station, off, onSelect, focus, overloaded, drawing, polygon, rain, onPoint });
  const mapRef = useRef<maplibregl.Map | null>(null);
  const reload = useRef<(() => void) | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { latest.current = { station, off, onSelect, focus, overloaded, drawing, polygon, rain, onPoint }; reload.current?.(); }, [station, off, onSelect, focus, overloaded, drawing, polygon, rain, onPoint]);
  useEffect(() => { if (focus) mapRef.current?.flyTo({ center: [focus.lon, focus.lat], zoom: focus.kind === "SUBSTATION" ? 13 : 15, duration: 700 }); }, [focus]);
  useEffect(() => {
    if (!container.current) return;
    maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({ container: container.current, center: [78.455,17.405], zoom: 11, style: {
        version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } },
        layers: [{ id: "base", type: "raster", source: "osm", paint: { "raster-saturation": -0.25, "raster-brightness-max": 1 } }] } });
    } catch { queueMicrotask(() => setError("Map unavailable. Use the asset list below to operate the simulation.")); return; }
    mapRef.current = map;
    let disposed = false, sequence = 0, cachedKey = "";
    let geometry: FeatureCollection = { type: "FeatureCollection", features: [] };
    const update = async () => {
      const seq = ++sequence;
      const bounds = map.getBounds();
      const q = new URLSearchParams({ west: String(bounds.getWest()), south: String(bounds.getSouth()), east: String(bounds.getEast()), north: String(bounds.getNorth()), zoom: String(map.getZoom()), station: latest.current.station });
      try {
        if (cachedKey !== q.toString()) {
          const result = await request<FeatureCollection>(`/electric/map?${q}`, {}, 15000);
          if (disposed || seq !== sequence) return;
          geometry = result; cachedKey = q.toString();
        }
        if (disposed || seq !== sequence) return;
        const offSet = new Set(latest.current.off);
        const painted: FeatureCollection = { ...geometry, features: geometry.features.map(f => ({ ...f, properties: { ...f.properties, off: offSet.has(f.properties?.id), overloaded: latest.current.overloaded.includes(f.properties?.id) } })) };
        (map.getSource("assets") as maplibregl.GeoJSONSource)?.setData(painted);
        const rainFeatures: FeatureCollection = { type: "FeatureCollection", features: latest.current.rain.map(z => ({ type: "Feature", properties: { intensity: z.intensity }, geometry: { type: "Polygon", coordinates: [[...z.polygon, z.polygon[0]]] } })) };
        const draft = latest.current.polygon;
        if (draft.length >= 3) rainFeatures.features.push({ type: "Feature", properties: { draft: true }, geometry: { type: "Polygon", coordinates: [[...draft, draft[0]]] } });
        (map.getSource("rain") as maplibregl.GeoJSONSource)?.setData(rainFeatures);
        (map.getSource("rain-corners") as maplibregl.GeoJSONSource)?.setData({ type: "FeatureCollection", features: draft.map(coordinates => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates } })) });
        map.getCanvas().style.cursor = latest.current.drawing ? "crosshair" : "";
        setError("");
      } catch (e) { if (!disposed) setError(e instanceof Error ? e.message : "Map data unavailable"); }
    };
    map.on("style.load", () => {
      map.addSource("rain", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "rain-fill", type: "fill", source: "rain", paint: { "fill-color": "#598cff", "fill-opacity": 0.22 } });
      map.addLayer({ id: "rain-border", type: "line", source: "rain", paint: { "line-color": "#a4bfff", "line-width": 2, "line-dasharray": [3,2] } });
      map.addSource("rain-corners", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "rain-corner-points", type: "circle", source: "rain-corners", paint: { "circle-radius": 5, "circle-color": "#c9d7ff" } });
      map.addSource("assets", { type: "geojson", data: geometry });
      map.addLayer({ id: "connections", type: "line", source: "assets", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": ["case", ["get", "off"], "#ff8d73", "#5ec9f5"], "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 16, 2.2], "line-opacity": 0.6 } });
      registerElectricalSymbols(map);
      map.addLayer({ id: "points", type: "symbol", source: "assets", filter: ["==", ["geometry-type"], "Point"], layout: {
        "icon-image": ["concat", ["get", "kind"], ["case", ["get", "off"], "-off", ["get", "overloaded"], "-overload", ""]],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 13, 0.75, 16, 0.95],
        "icon-allow-overlap": true, "icon-ignore-placement": true,
        "icon-offset": ["case", ["==", ["get", "kind"], "POWER_TRANSFORMER"],
          ["case", ["==", ["slice", ["get", "id"], -1], "1"], ["literal", [-22, 17]], ["literal", [22, 17]]],
          ["==", ["get", "kind"], "SIGNAL_LOAD"], ["literal", [15, -15]], ["literal", [0, 0]]]
      } });
      reload.current = () => { void update(); }; void update();
      const selected = latest.current.focus;
      if (selected) map.flyTo({ center: [selected.lon, selected.lat], zoom: selected.kind === "SUBSTATION" ? 13 : 15, duration: 700 });
    });
    map.on("moveend", () => { if (map.getSource("assets")) void update(); });
    map.on("idle", () => {
      if (container.current && map.getLayer("points")) {
        const visible = map.queryRenderedFeatures({ layers: ["points"] });
        container.current.dataset.visibleAssets = String(visible.length);
        container.current.dataset.visibleKinds = [...new Set(visible.map(f => f.properties.kind))].join(",");
      }
    });
    map.on("click", event => { if (latest.current.drawing) latest.current.onPoint([event.lngLat.lng, event.lngLat.lat]); });
    map.on("click", "points", event => { if (latest.current.drawing) return; const id = event.features?.[0]?.properties?.id; if (id) latest.current.onSelect(String(id)); });
    map.addControl(new maplibregl.NavigationControl());
    const resize = new ResizeObserver(() => map.resize()); resize.observe(container.current);
    return () => { disposed = true; sequence++; reload.current = null; resize.disconnect(); mapRef.current = null; map.remove(); };
  }, []);
  return <div><button onClick={() => mapRef.current?.fitBounds([[78.30,17.30],[78.61,17.56]], { padding: 35, duration: 700 })}>City overview</button><div className="electric-map" ref={container} aria-label="Synthetic electrical network map" />{error && <p role="alert">{error}</p>}<ElectricalLegend /><p className="muted">Symbol shape identifies the asset type. Red indicates lost supply or affected descendants. Power transformer and signal symbols are offset slightly when co-located. Lines: synthetic feeder paths following imported streets; not surveyed cables. Select a substation; zoom to street level for its distribution transformers.</p></div>;
}

export default function ElectricWorkspace({ role }: { role: "command" | "lineman" }) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [asset, setAsset] = useState<Asset | null>(null);
  const [station, setStation] = useState("SS-001");
  const [search, setSearch] = useState("SS-001");
  const [operator, setOperator] = useState("");
  const [note, setNote] = useState("");
  const [crew, setCrew] = useState("");
  const [drawing, setDrawing] = useState(false);
  const [polygon, setPolygon] = useState<[number, number][]>([]);
  const addPoint = useCallback((point: [number, number]) => setPolygon(previous => previous.length < 40 ? [...previous, point] : previous), []);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const mutating = useRef(false), sequence = useRef(0), selectionSequence = useRef(0);
  const refresh = useCallback(async () => {
    const seq = ++sequence.current;
    try { const next = await request<Snapshot>("/electric", {}, 15000); if (seq === sequence.current) { setData(next); setConnectionError(""); } }
    catch (e) { if (seq === sequence.current) setConnectionError(e instanceof Error ? e.message : "Backend unavailable"); }
  }, []);
  const select = useCallback(async (id: string) => {
    const seq = ++selectionSequence.current;
    try { const next = await request<Asset>(`/electric/assets/${encodeURIComponent(id)}`, {}, 15000); if (seq === selectionSequence.current) { setAsset(next); setStation(next.station); setSearch(next.id); setError(""); } }
    catch (e) { if (seq === selectionSequence.current) setError(e instanceof Error ? e.message : "Asset not found"); }
  }, []);
  useEffect(() => {
    let alive = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { if (!mutating.current) await refresh(); if (alive) timer = setTimeout(poll, 1000); };
    void poll();
    const initialSelection = setTimeout(() => { void select("SS-001"); }, 0);
    const snapshotSequence = sequence, assetSequence = selectionSequence;
    return () => { alive = false; clearTimeout(timer); clearTimeout(initialSelection); snapshotSequence.current++; assetSequence.current++; };
  }, [refresh, select]);
  const act = async (action: string, task?: Task, options: Record<string, unknown> = {}) => {
    if (!data || mutating.current) return;
    mutating.current = true; sequence.current++; setBusy(true); setError("");
    try { await request("/electric/actions", { method: "POST", body: JSON.stringify({ action, version: data.version, asset_id: asset?.id || "", task_id: task?.id || "", operator: operator.trim() || "Local simulation operator", note: note.trim() || "Operator adjusted synthetic simulation", crew, ...options }) }); }
    catch (e) { setError(e instanceof Error ? e.message : "Action failed"); }
    await refresh(); setBusy(false); mutating.current = false;
  };
  const disabled = busy || !!connectionError || !operator.trim() || note.trim().length < 3;
  return <main className="electric-shell">
    <nav><Link href="/traffic">Traffic</Link><Link href="/ambulance">Ambulance</Link><Link href="/electric-command">Electric Command</Link><Link href="/lineman">Lineman</Link></nav>
    <header><div><p className="eyebrow">AEGISGRID / SYNTHETIC INFRASTRUCTURE</p><h1>{role === "command" ? "Electric Command" : "Lineman workspace"}</h1><p>Hyderabad pilot · Connected supply, faults and repair consequences</p></div><span className="electric-badge">SYNTHETIC · {data?.running ? "RUNNING" : "PAUSED"}</span></header>
    <p className="electric-notice">Electrical sites are synthetic, placed on the imported Hyderabad road network. Feeder paths follow real street geometry; electrical connections, loads and queues are modeled. This pilot is not TGSPDCL’s asset inventory.</p>
    {(error || connectionError) && <p role="alert" className="electric-error">{error || connectionError}</p>}
    {!data ? <p>Loading saved electrical world…</p> : <>
      {role === "command" && <section className="electric-clock electric-panel"><div><h2>Realtime load simulation</h2><p>Simulation time: {Math.floor(data.seconds / 60)}m {data.seconds % 60}s · {data.running ? "RUNNING" : "PAUSED"} · {data.speed}×</p></div><button disabled={busy || !!connectionError} onClick={() => void act("CLOCK", undefined, { running: !data.running, speed: data.speed })}>{data.running ? "Pause simulation" : "Run simulation"}</button><label>Simulation speed<select aria-label="Simulation speed" value={data.speed} disabled={busy || !!connectionError} onChange={e => void act("CLOCK", undefined, { running: data.running, speed: Number(e.target.value) })}><option value="1">1× realtime</option><option value="5">5× faster</option><option value="10">10× faster</option></select></label><p className="muted">Demand changes propagate through the network. Yellow = overloaded; red = disconnected. Protection trips after 10 continuous simulated seconds above the modeled limit. The clock continues while this page is closed.</p></section>}
      {role === "command" && <RainControls drawing={drawing} points={polygon.length} zones={data.rain_effects} busy={busy || !!connectionError} onDraw={() => { setPolygon([]); setDrawing(true); }} onClear={() => { setPolygon([]); setDrawing(false); }} onApply={intensity => { void act("RAIN", undefined, { polygon, intensity, note: `Applied synthetic rain at ${intensity} mm/hour` }); setDrawing(false); }} onChange={(asset_id, intensity) => void act("RAIN_INTENSITY", undefined, { asset_id, intensity, note: `Rain changed to ${intensity} mm/hour` })} onRemove={asset_id => void act("REMOVE_RAIN", undefined, { asset_id, note: "Removed synthetic rainfall area" })} />}
      <section className="electric-stats">{[["Substations", data.counts.SUBSTATION], ["Power transformers", data.counts.POWER_TRANSFORMER], ["11 kV feeders", data.counts.FEEDER_11KV], ["Distribution transformers", data.counts.DISTRIBUTION_TRANSFORMER], ["Unserved demand · kW", data.unserved_kw], ["Signals without supply", data.signals_without_supply]].map(([name, value]) => <div key={name}><small>{name}</small><strong>{value?.toLocaleString()}</strong></div>)}</section>
      <div className="electric-grid"><section className="electric-panel"><div className="electric-toolbar"><h2>Network explorer</h2><select aria-label="Substation" value={station} onChange={e => void select(e.target.value)}>{data.stations.map(s => <option key={s.id} value={s.id}>{s.id} · {s.road_context || "Local streets"}</option>)}</select></div>
        <ElectricMap drawing={drawing} polygon={polygon} rain={data.rain_effects} onPoint={addPoint} overloaded={data.overloaded_ids} focus={asset} station={station} off={data.off_ids.concat(data.affected_stations)} onSelect={select} />
      </section><section className="electric-panel"><h2>Asset inspection</h2><form onSubmit={e => { e.preventDefault(); void select(search.trim().toUpperCase()); }}><label>Find asset by ID<input value={search} onChange={e => setSearch(e.target.value)} placeholder="DT-00001" /></label><button>Inspect</button></form>
        {asset && <><h3>{asset.id}</h3><p>{label(asset.kind)} · {data.off_ids.includes(asset.id) ? "WITHOUT SUPPLY" : "SUPPLIED"}</p><p className="muted">Road context: {asset.road_context || "Imported local street"}<br />Synthetic position: {asset.lat}, {asset.lon}</p><p>Upstream: {asset.upstream?.join(" ← ")}</p>{role === "command" && data.telemetry[asset.id] && <LoadControls key={asset.id} id={asset.id} value={data.telemetry[asset.id]} busy={busy || !!connectionError} running={data.running} onLoad={load_percent => void act("LOAD", undefined, { load_percent })} onReset={() => void act("RESET_PROTECTION")} />}<details><summary>Connected children ({asset.children?.length})</summary><div className="electric-children">{asset.children?.map(a => <button key={a.id} onClick={() => void select(a.id)}>{a.id} · {label(a.kind)}</button>)}</div></details>{role === "command" && <details><summary>Advanced: inject an equipment fault</summary><form className="electric-fault-form" onSubmit={e => { e.preventDefault(); if (!operator.trim() || note.trim().length < 3) { setError("Enter your operator name and a fault reason of at least 3 characters."); return; } void act("FAULT"); }}>
          <h3>Inject a fault</h3>
          <p className="muted">Enter these two details to inject a synthetic fault at {asset.id}. They are saved with the event.</p>
          <label>Fault operator<input required value={operator} onChange={e => setOperator(e.target.value)} maxLength={100} placeholder="Your name" /></label>
          <label>Fault reason<input required minLength={3} value={note} onChange={e => setNote(e.target.value)} maxLength={500} placeholder="For example: transformer failure exercise" /></label>
          <button className="danger" disabled={busy || !!connectionError || asset.kind === "SIGNAL_LOAD" || data.faults.includes(asset.id)}>{busy ? "Applying action…" : `Inject synthetic fault at ${asset.id}`}</button>
          {data.faults.includes(asset.id) && <p role="status">This asset already has an active fault. Use its repair work order below.</p>}
          {asset.kind === "SIGNAL_LOAD" && <p>Select its upstream transformer or feeder to simulate a supply failure.</p>}
          {connectionError && <p role="status">Injection is unavailable while the backend is disconnected.</p>}
        </form></details>}</>}
      </section></div>
      <section className="electric-panel"><h2>Action record</h2><p className="muted">Enter your operator name and a reason before acting. These demo workspaces do not authenticate staff roles.</p><div className="electric-inputs"><label>Operator<input value={operator} onChange={e => setOperator(e.target.value)} maxLength={100} /></label><label>Reason / repair evidence<input value={note} onChange={e => setNote(e.target.value)} maxLength={500} /></label>{role === "command" && <label>Assign to crew<input value={crew} onChange={e => setCrew(e.target.value)} maxLength={100} /></label>}</div></section>
      <div className="electric-grid"><section className="electric-panel"><h2>Repair work orders</h2>{!data.tasks.length && <p>No faults injected. Adjust demand to exercise overload protection, or use advanced fault injection for a repair exercise.</p>}{data.tasks.map(t => <article className="electric-job" key={t.id}><button onClick={() => void select(t.asset_id)}>{t.asset_id}</button><strong>{label(t.status)}</strong><p>{t.id} · {t.crew || "Unassigned"} · {t.note}</p>{role === "command" && t.status === "OPEN" && <button disabled={disabled || !crew.trim()} onClick={() => void act("ASSIGN", t)}>Assign crew</button>}{role === "lineman" && t.status === "ASSIGNED" && <button disabled={disabled} onClick={() => void act("START", t)}>Start repair</button>}{role === "lineman" && t.status === "IN_PROGRESS" && <button disabled={disabled} onClick={() => void act("COMPLETE", t)}>Submit repair for verification</button>}{role === "command" && t.status === "AWAITING_VERIFICATION" && <button disabled={disabled} onClick={() => void act("VERIFY", t)}>Verify repair and restore</button>}</article>)}</section>
      <section className="electric-panel"><h2>Simulation consequences</h2><p>Simulation time: {(data.seconds / 60).toFixed(1)} min · Revision {data.version}</p><p>{Math.round(Object.values(data.queues).reduce((a,b) => a+b,0))} modeled queued vehicles at {data.counts.SIGNAL_LOAD} synthetic signal loads.</p><p className="muted">Each minute: a dark signal adds 12 queued vehicles; a supplied signal drains up to 18. This uncalibrated electrical exercise does not yet alter traffic routes or represent measured traffic.</p>{role === "command" && <button disabled={busy || !!connectionError || data.running} onClick={() => void act("ADVANCE")}>Advance simulation by 1 minute</button>}<p className="muted">Assets keep the same IDs and positions. Faults, repair progress and the simulation clock survive API restarts in local storage.</p></section></div>
      <section className="electric-panel"><h2>Event journal</h2>{!data.events.length && <p>No actions yet.</p>}{data.events.map(e => <p className="electric-event" key={e.id}><strong>{label(e.action)} {e.asset_id}</strong> · T+{e.simulation_seconds}s · {e.operator}<br /><span>{e.note} · {new Date(e.at).toLocaleString()}</span></p>)}</section>
    </>}
  </main>;
}
