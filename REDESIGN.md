> Historical record of the previous routing/demo interface. The current operational redesign and its verification are documented in [OPERATIONAL_REDESIGN.md](OPERATIONAL_REDESIGN.md).

# Hyderabad urban operations redesign

## Delivered

Three-column command center with a dominant interactive MapLibre surface, compact route planner, selected-feature inspector, system clock (IST), backend health, city metrics, rainfall chart, alert feed, six department status entries, zone risk, traffic distribution, power summary, emergency vehicles, runtime incident controls and reusable recommendation cards. Bottom controls provide seven scenarios, play/pause/step, 1x/2x/5x and demo reset.

The reference images informed information density, hierarchy, color semantics and spatial layering. They were not embedded as backgrounds or copied pixel-for-pixel. The Sites skill guided reuse of the existing Next.js application and component structure; no hosting migration or cloud deployment was performed.

## Functional / real-backed

- Existing `/traffic` route, FastAPI endpoints, MapLibre renderer, local workers, NetworkX and Supabase/PostGIS integration retained.
- Start/destination selection, backend route GeoJSON, distance, free-flow ETA, route-edge count, graph/cache/timing diagnostics and road names retained.
- Road-interior endpoint snapping, original-click offsets and coverage snapshot retained. Coverage shading is lighter so operational overlays remain legible; its toggle and full-coverage view remain available.
- Inject Incident posts a SYNTHETIC exercise incident to the real backend runtime; it is not a field observation. The backend applies closure costs and recalculates the selected route. Resolve performs DELETE and recalculation.
- Runtime incidents populate the alert feed, selectable inspector and evidence-linked Traffic Police advisory. Resolving an incident removes its advisory. No automatic municipal actions occur.
- Route and incident geometry can be selected in Inspect mode. The route inspector describes a corridor, not an individual database edge. Route reset removes its selected geometry.
- Missing speed/congestion/water measurements are shown as unreported rather than inferred from unrelated demo values.

## Synthetic / illustrative

Weather, trend/forecast, risk metrics, traffic distribution, power inventory, emergency vehicles/ETAs, exercise sectors, traffic-condition linework, waterlogging footprint, hospital/signal/transformer locations, agent status and department templates are SYNTHETIC. Their positions and values are demonstration fixtures, not verified municipal assets or telemetry. Dashed demo corridors are schematic and not road-aligned routing outputs.

Demo controls affect only local React state. They never POST a route, inject/resolve a backend incident, dispatch a vehicle, operate a signal, or change a database record. Demo reset does not resolve runtime incidents. No AI model is connected; confidence is explicitly unscored and benefits are not presented as measured results. DERIVED incident advisories identify the provenance of their backend incident evidence.

## Changed files

Modified:

- `web/src/app/layout.tsx` — stylesheet and page metadata.
- `web/src/components/traffic/TrafficDashboard.tsx` — composition and shared selection state; existing request/cancellation/mutation workflow preserved.
- `web/src/components/traffic/TrafficMap.tsx` — operational layers, inspection, live map-center readout and lighter coverage.
- `web/src/components/traffic/RoutePanel.tsx` — compact planner and expandable diagnostics.
- `web/src/components/traffic/IncidentPanel.tsx` — runtime labeling and inspection.
- `web/tests/traffic.spec.ts` — adapted coverage assertion, incident-linked recommendations and demo-reset isolation.

Added:

- `web/src/types/operations.ts` — provenance-bearing operational contracts.
- `web/src/lib/operations.ts` — deterministic demo fixtures, map geometry and advisory construction.
- `web/src/app/command.css` — command-center layout, visual system and responsive treatment.
- `web/src/components/command/CommandHeader.tsx`, `Panel.tsx`, `OverviewPanels.tsx`, `EmergencyVehicles.tsx`, `RecommendationCard.tsx`, `SelectedRoadPanel.tsx`, `SimulationControls.tsx`, `useSimulation.ts`.
- `web/src/components/map/OperationalLayers.tsx`, `LayerControls.tsx`, `MapLegend.tsx`.
- `web/tests/command.spec.ts` — synthetic controls, layers, inspection, no mutation requests, desktop/mobile layout and screenshots.
- `REDESIGN.md` — this handoff.

Next.js also generated `web/AGENTS.md` and `web/CLAUDE.md` on development startup. No application dependency or backend source/schema change was required.

## Validation

- `npm.cmd run build` — production build and TypeScript pass.
- `npm.cmd run lint` — pass.
- `npx.cmd playwright test` — five browser scenarios: command controls/inspection, coverage toggle, coverage failure, real routing/inject/resolve, and delayed-request reset/error handling.
- Verified horizontal fit at 1440 px desktop and 390 px mobile; inspected screenshots. Small-screen panels stack; desktop columns scroll independently for detailed department information.
- Actual service-role key value checked against frontend source, public assets and compiled browser bundles: absent. No key printed.
- Screenshots: `web/test-results/command-center-1440.png`, `command-center-mobile.png`, `traffic-desktop.png`, `traffic-coverage.png` (generated/ignored).

## Remaining gaps and next implementation

No live weather/flood/traffic/power/vehicle feeds, AI coordination, satellite/3D model, official administrative boundaries, surveyed asset registry, per-road inspection API or validated impact/confidence model exists. The reference's live CCTV, moving vehicles and predicted queue reductions are intentionally not fabricated. First graph loads can still be slow; incidents remain process-local and unauthenticated as documented in README.

**Next:** add a read-only, provenance-bearing road/asset inspection API (road ID, directed geometry, class, baseline speed and source timestamp). Then replace the schematic demo corridors with actual road-edge geometry while keeping synthetic condition values separately labeled. This is a separate backend change, not part of this frontend redesign.
