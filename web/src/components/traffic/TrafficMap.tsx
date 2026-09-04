"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import type { Coordinate, Incident, MapMode, RouteResult } from "@/types/aegis";
import type { MapSelection } from "@/types/operations";
import TrafficSignals from "./TrafficSignals";
type Props = { target?: Coordinate | null; start: Coordinate | null; end: Coordinate | null; route: RouteResult | null; incidents: Incident[]; mode: MapMode; onPick: (point: Coordinate) => void; ambulances?: { id: string; position: Coordinate; provenance: string }[]; selected: MapSelection | null; onSelect: (selection: MapSelection) => void; onIncidentSelect: (id: string) => void };
const empty: FeatureCollection = { type: "FeatureCollection", features: [] };
export default function TrafficMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const latest = useRef(props);
  const fittedRoute = useRef("");
  const [ready, setReady] = useState(false);
  const [signalMap, setSignalMap] = useState<maplibregl.Map | null>(null);
  const [error, setError] = useState("");
  const [coverageVisible, setCoverageVisible] = useState(true);
  const [coverage, setCoverage] = useState<{ roadCount: number; generatedAt: string; bounds: [number, number, number, number] } | null>(null);
  const [coverageError, setCoverageError] = useState(false);
  const [center, setCenter] = useState({ lat: 17.415, lon: 78.4867 });
  useLayoutEffect(() => { latest.current = props; });
  useEffect(() => {
    if (!container.current) return;
    let instance: maplibregl.Map;
    try {
      maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");
      instance = new maplibregl.Map({ container: container.current, attributionControl: { compact: false }, center: [78.4867, 17.415], zoom: 11.5, maxBounds: [[78.05, 17.05], [78.95, 17.85]], style: {
        version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>' } },
        layers: [{ id: "background", type: "background", paint: { "background-color": "#f7f8fa" } }, { id: "basemap", type: "raster", source: "osm", paint: { "raster-saturation": -0.25, "raster-brightness-min": 0, "raster-brightness-max": 1, "raster-contrast": 0 } }],
      } });
    } catch {
      // External WebGL initialization failure must be surfaced to the operator.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError("Map could not start. Enable WebGL in your browser and reload."); return;
    }
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    instance.addControl(new maplibregl.ScaleControl(), "bottom-left");
    instance.on("click", (event) => {
      const current = latest.current;
      if ((event.originalEvent.target as HTMLElement)?.closest(".traffic-signal-pin")) return;
      if (current.mode === "inspect" && instance.getLayer("route-line")) {
        const feature = instance.queryRenderedFeatures(event.point, { layers: ["blocked-segments", "route-line"] })[0];
        if (feature?.layer.id === "blocked-segments") { current.onIncidentSelect(feature.properties.id); return; }
        if (feature?.layer.id === "route-line" && current.route) {
          current.onSelect({ id: "backend-route", name: "Calculated route corridor", kind: "route", status: "CALCULATED", baseSpeed: "Per-edge data not exposed", currentSpeed: "Not measured", congestion: "Not measured", impact: `${current.route.route_edges.length} route edges`, waterRisk: "Not measured", etaImpact: `${current.route.eta_minutes.toFixed(1)} min total · modeled travel and turns`, affectedRoutes: "Current route", provenance: "DERIVED", source: "Turn-aware NetworkX on OSM geometry; calibrated costs, not live telemetry", feature: current.route.route }); return;
        }
      }
      const routeHit = current.mode === "incident" && instance.getLayer("route-hit-targets")
        ? instance.queryRenderedFeatures(event.point, { layers: ["route-hit-targets"] })[0] : undefined;
      current.onPick({ lat: event.lngLat.lat, lon: event.lngLat.lng, ...(routeHit?.properties.external_id ? { target_edge_id: String(routeHit.properties.external_id) } : {}) });
    });
    instance.on("error", () => setError("Some map tiles could not load. Routing remains available; check your connection."));
    instance.on("moveend", () => { const point = instance.getCenter(); setCenter({ lat: point.lat, lon: point.lng }); });
    instance.on("idle", () => {
      // Expose render completion for diagnostics, without leaking map internals.
      if (container.current && instance.getLayer("route-line")) {
        container.current.dataset.routeFeatures = String(instance.queryRenderedFeatures({ layers: ["route-line"] }).length);
        container.current.dataset.coverageFeatures = String(instance.queryRenderedFeatures({ layers: ["coverage-fill"] }).length);
      }
    });
    instance.on("load", () => {
      instance.addSource("coverage", { type: "geojson", data: empty });
      instance.addLayer({ id: "coverage-fill", type: "fill", source: "coverage", paint: { "fill-color": "#8bd66f", "fill-opacity": 0.09 } });
      instance.addLayer({ id: "coverage-outline", type: "line", source: "coverage", paint: { "line-color": "#a0df85", "line-opacity": 0.3, "line-width": 0.7 } });
      instance.addSource("route", { type: "geojson", data: empty });
      instance.addSource("endpoint-offsets", { type: "geojson", data: empty });
      instance.addLayer({ id: "endpoint-offset-lines", type: "line", source: "endpoint-offsets", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#c0cbd3", "line-width": 2, "line-dasharray": [2, 3] } });
      instance.addLayer({ id: "requested-points", type: "circle", source: "endpoint-offsets", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 4, "circle-color": "#101b24", "circle-stroke-color": "#d8e1e8", "circle-stroke-width": 2 } });
      instance.addLayer({ id: "route-halo", type: "line", source: "route", paint: { "line-color": "#42e5c1", "line-width": 12, "line-opacity": 0.13 } });
      instance.addLayer({ id: "route-line", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" }, paint: { "line-color": "#58f2cc", "line-width": 4 } });
      instance.addSource("route-segments", { type: "geojson", data: empty });
      instance.addLayer({ id: "route-hit-targets", type: "line", source: "route-segments", paint: { "line-width": 16, "line-opacity": 0 } });
      instance.addSource("incidents", { type: "geojson", data: empty });
      instance.addLayer({ id: "blocked-segments", type: "line", source: "incidents", paint: { "line-color": "#ff986b", "line-width": 7, "line-dasharray": [2, 1] } });
      setReady(true);
      setSignalMap(instance);
    });
    const resize = new ResizeObserver(() => instance.resize()); resize.observe(container.current);
    return () => { resize.disconnect(); map.current = null; instance.remove(); };
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const controller = new AbortController();
    fetch("/data/road-coverage.geojson", { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Coverage unavailable"); return response.json(); })
      .then(data => {
        if (controller.signal.aborted) return;
        if (data.type !== "FeatureCollection" || !data.features?.length || !data.metadata?.roadCount || data.metadata?.bounds?.length !== 4) throw new Error("Invalid coverage snapshot");
        (instance.getSource("coverage") as GeoJSONSource).setData(data);
        setCoverage(data.metadata);
      })
      .catch(() => { if (!controller.signal.aborted) setCoverageError(true); });
    return () => controller.abort();
  }, [ready]);
  useEffect(() => {
    if (!map.current || !ready) return;
    for (const layer of ["coverage-fill", "coverage-outline"]) map.current.setLayoutProperty(layer, "visibility", coverageVisible ? "visible" : "none");
  }, [ready, coverageVisible]);
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    (instance.getSource("route") as GeoJSONSource).setData(props.route?.route ?? empty);
    (instance.getSource("route-segments") as GeoJSONSource).setData(props.route?.route_segments ?? empty);
    const offsets: FeatureCollection = { type: "FeatureCollection", features: [] };
    if (props.route?.snapping) {
      for (const snap of [props.route.snapping.start, props.route.snapping.end]) {
        if (snap.distance_m <= 0.5) continue;
        const click = [snap.requested.lon, snap.requested.lat];
        const road = [snap.snapped.lon, snap.snapped.lat];
        offsets.features.push({ type: "Feature", properties: { meaning: "selection offset, not a drivable route" }, geometry: { type: "LineString", coordinates: [click, road] } });
        offsets.features.push({ type: "Feature", properties: { meaning: "original click" }, geometry: { type: "Point", coordinates: click } });
      }
    }
    (instance.getSource("endpoint-offsets") as GeoJSONSource).setData(offsets);
    const routeKey = props.route ? JSON.stringify(props.route.route.geometry.coordinates) : "";
    if (props.route && routeKey !== fittedRoute.current) {
      fittedRoute.current = routeKey;
      const bounds = new maplibregl.LngLatBounds();
      props.route.route.geometry.coordinates.forEach(([lon, lat]) => bounds.extend([lon, lat]));
      if (props.route.snapping) {
        for (const snap of [props.route.snapping.start, props.route.snapping.end]) bounds.extend([snap.requested.lon, snap.requested.lat]);
      }
      if (!bounds.isEmpty()) instance.fitBounds(bounds, { padding: 70, maxZoom: 15, duration: 0 });
    }
  }, [props.route, ready]);
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const markers: maplibregl.Marker[] = [];
    const add = (point: Coordinate, label: string, className: string, title: string) => {
      const el = document.createElement("div"); el.className = `map-marker ${className}`; el.textContent = label; el.title = title; el.setAttribute("aria-label", title);
      el.dataset.lat = String(point.lat); el.dataset.lon = String(point.lon);
      markers.push(new maplibregl.Marker({ element: el }).setLngLat([point.lon, point.lat]).addTo(instance));
    };
    if (props.start) add(props.route?.snapping?.start.snapped ?? props.start, "A", "start-marker", props.route ? "Route start on road" : "Selected start");
    if (props.end) add(props.route?.snapping?.end.snapped ?? props.end, "B", "end-marker", props.route ? "Route destination on road" : "Selected destination");
    if (props.target) add(props.target, "◎", "event-target-marker", "Selected event / reported location");
    props.ambulances?.forEach(item => add(item.position, "✚", "ambulance-marker", `${item.id} · ${item.provenance} location`));
    props.incidents.forEach((item) => {
      add(item, "!", "incident-marker", `${item.provenance} road blockage`);
      const el = markers[markers.length - 1].getElement(); el.tabIndex = 0; el.setAttribute("role", "button");
      const inspect = () => latest.current.onIncidentSelect(item.id);
      el.onclick = event => { if (latest.current.mode === "inspect") { event.stopPropagation(); inspect(); } };
      el.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspect(); } };
    });
    (instance.getSource("incidents") as GeoJSONSource).setData({ type: "FeatureCollection", features: props.incidents.filter(i => i.affected_geometry).map(i => ({ type: "Feature", properties: { id: i.id }, geometry: i.affected_geometry! })) });
    return () => markers.forEach(marker => marker.remove());
  }, [props.start, props.end, props.incidents, props.route, props.ambulances, props.target, ready]);
  useEffect(() => { if (map.current) map.current.getCanvas().style.cursor = props.mode === "inspect" ? "grab" : "crosshair"; }, [props.mode]);
  return <div className="map-shell"><div ref={container} className="map-canvas" data-testid="traffic-map" aria-label="Hyderabad route selection map" />
    <div className="map-label"><span className="live-dot" /> HYDERABAD <span>/ ROAD NETWORK</span></div>
    <TrafficSignals map={signalMap}/><div className="map-position">{center.lat.toFixed(4)}° N / {center.lon.toFixed(4)}° E</div>
    <div className="coverage-controls" aria-label="Imported road coverage">
      <button className="coverage-toggle" aria-pressed={coverageVisible} disabled={!coverage} onClick={() => setCoverageVisible(value => !value)}><span className="coverage-swatch" /> Coverage <span>{coverageVisible ? "ON" : "OFF"}</span></button>
      {coverage ? <><p>{coverage.roadCount.toLocaleString("en-IN")} directed road segments</p><small>Approximate imported coverage<br />Snapshot · {coverage.generatedAt.slice(0, 10)}</small><button className="coverage-fit" onClick={() => { const [west, south, east, north] = coverage.bounds; map.current?.fitBounds([[west, south], [east, north]], { padding: 45, duration: 0 }); }}>View all coverage ↗</button></> : <p role="status">{coverageError ? "Coverage layer unavailable" : "Loading coverage…"}</p>}
    </div>
    {!ready && !error && <div className="map-notice">Loading Hyderabad basemap…</div>}
    {error && <div className="map-notice" role="alert">{error} <button onClick={() => setError("")}>Dismiss</button></div>}
    <div className="map-legend">{coverage && coverageVisible && <span className="coverage-legend"><span className="coverage-swatch" /> Imported roads · approximate area</span>}<span className="legend-line" /> Calculated route <span className="legend-line amber" /> Blocked segment {props.route && <span className="offset-legend">○ ┄ Click offset · not routed</span>}{coverage && coverageVisible && <small className="coverage-disclaimer">Shading shows road-data presence, not guaranteed routing at every point.</small>}</div>
  </div>;
}
