"use client";
import { useEffect } from "react";
import * as maplibregl from "maplibre-gl";
import type { MapSelection, SimulationState } from "@/types/operations";
import type { MapMode } from "@/types/aegis";
import { demoAssets, demoFlood, demoRoads, demoState, demoZones, selectionForDemo } from "@/lib/operations";
export type LayerState = { zones: boolean; traffic: boolean; flood: boolean; signal: boolean; transformer: boolean; hospital: boolean; ambulance: boolean };
export const defaultLayers: LayerState = { zones: true, traffic: true, flood: true, signal: true, transformer: true, hospital: true, ambulance: true };
const empty = { type: "FeatureCollection" as const, features: [] };
export function useOperationalLayers(map: maplibregl.Map | null, ready: boolean, simulation: SimulationState, layers: LayerState, mode: MapMode, selected: MapSelection | null, onSelect: (selection: MapSelection) => void) {
  useEffect(() => {
    if (!map || !ready) return;
    const definitions: [string, maplibregl.LayerSpecification][] = [
      ["demo-zones", { id: "demo-zone-fill", type: "fill", source: "demo-zones", paint: { "fill-color": ["get", "color"], "fill-opacity": .07 } }],
      ["demo-zones", { id: "demo-zone-outline", type: "line", source: "demo-zones", paint: { "line-color": ["get", "color"], "line-width": 1.4, "line-opacity": .75, "line-dasharray": [4,2] } }],
      ["demo-flood", { id: "demo-flood-fill", type: "fill", source: "demo-flood", paint: { "fill-color": "#228bdb", "fill-opacity": .28 } }],
      ["demo-flood", { id: "demo-flood-outline", type: "line", source: "demo-flood", paint: { "line-color": "#3abdf1", "line-width": 1.5, "line-dasharray": [2,2] } }],
      ["demo-roads", { id: "demo-road-lines", type: "line", source: "demo-roads", paint: { "line-color": ["match", ["get","state"], "normal", "#5abf89", "slow", "#edc54c", "congested", "#f18645", "#c383ef"], "line-width": 3, "line-opacity": .8, "line-dasharray": [5,2] } }],
      ["selected-feature", { id: "selected-road-line", type: "line", source: "selected-feature", paint: { "line-color": "#eff7ff", "line-width": 7, "line-opacity": .6 } }],
    ];
    for (const [source, layer] of definitions) { if (!map.getSource(source)) map.addSource(source, { type: "geojson", data: empty }); if (!map.getLayer(layer.id)) map.addLayer(layer, "endpoint-offset-lines"); }
    (map.getSource("demo-zones") as maplibregl.GeoJSONSource).setData(layers.zones ? demoZones : empty);
    (map.getSource("demo-roads") as maplibregl.GeoJSONSource).setData(layers.traffic ? demoRoads(simulation) : empty);
    (map.getSource("demo-flood") as maplibregl.GeoJSONSource).setData(layers.flood && simulation.scenario === "WATERLOGGING" ? demoFlood : empty);
    (map.getSource("selected-feature") as maplibregl.GeoJSONSource).setData(selected?.feature ?? empty);
    const assets = [...demoAssets, ...demoState(simulation).vehicles.map(v => ({ id: v.id, name: `${v.id} ambulance`, kind: "ambulance" as const, symbol: "✚", coordinate: v.coordinate, provenance: v.provenance }))];
    const markers: maplibregl.Marker[] = [];
    for (const asset of assets) {
      if (!layers[asset.kind]) continue;
      const element = document.createElement("button"); element.className = `demo-asset asset-${asset.kind}`; element.textContent = asset.symbol; element.title = `${asset.name} · SYNTHETIC DEMO`; element.setAttribute("aria-label", element.title);
      element.onclick = event => { if (mode !== "inspect") return; event.stopPropagation(); onSelect(selectionForDemo(asset.id, asset.name, asset.kind, "exercise", simulation)); };
      markers.push(new maplibregl.Marker({element}).setLngLat(asset.coordinate).addTo(map));
    }
    if (layers.zones) for (const [name, lon, lat, tone] of [["NORTH",78.459,17.482,"#65c5f2"],["EAST",78.533,17.434,"#c396ed"],["WEST",78.422,17.414,"#7dd49e"],["SOUTH",78.482,17.371,"#e9c35b"]] as const) {
      const el = document.createElement("div"); el.className = "zone-map-label"; el.style.color = tone; el.textContent = name; const note=document.createElement("small"); note.textContent="DEMO SECTOR"; el.append(note);
      markers.push(new maplibregl.Marker({element:el}).setLngLat([lon,lat]).addTo(map));
    }
    return () => markers.forEach(marker => marker.remove());
  }, [map, ready, simulation, layers, mode, selected, onSelect]);
}
