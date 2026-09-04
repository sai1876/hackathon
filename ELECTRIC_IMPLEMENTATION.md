# Electrical pilot delivered — 2026-09-03

**Update:** Realtime load controls, automatic overload protection, polygon rainfall, road-routing effects and a metro-demand index are now implemented. See [REALTIME_RAINFALL_IMPLEMENTATION.md](REALTIME_RAINFALL_IMPLEMENTATION.md). The original manual-only limitations below describe the first increment and are superseded where that report specifies new behavior.

## Available locally

- `/electric-command`: explore connected assets, inject a synthetic fault, assign a crew, verify restoration, advance the simulation clock.
- `/lineman`: inspect the same network, start assigned work and submit a repair for verification.
- Both portals are linked from the traffic and ambulance navigation.

## Generated network

20 supply entry points at 33 kV, 20 substations, 38 power transformers, 95 outgoing 11 kV feeders, 6,300 distribution transformers and 95 signal loads: 6,568 records in total.

These are **synthetic pilot counts**, not a Hyderabad allocation of the TGSPDCL totals. The initial geometric grid was replaced by the OSM-constrained v2 layout. Synthetic sites are selected on imported Hyderabad street nodes with irregular spacing; feeder catchments follow road-network distances and feeder paths use imported road polylines. This is not a surveyed electrical inventory or a land-use-calibrated allocation. OpenStreetMap supplies both background geography and constraints for generating the synthetic layout.

Power transformers are children of substations. Each outgoing feeder belongs to a power transformer. Distribution transformers and signal loads have explicit supply parents. Assets never infer connectivity from visual proximity.

The generated dataset is stored once, with stable IDs and coordinates, in `backend/data/electric-world.sqlite3`. Faults, tasks, simulation time, queues and events are committed transactionally in the same local SQLite database. `ELECTRIC_DB_PATH` can configure the database location. The database is ignored by source control. A persistent disk and backups are needed when hosting; this is not a Supabase migration.

## Behavior

- A fault disconnects only the asset and its descendants.
- Independent downstream faults remain effective after an upstream repair.
- Work follows OPEN → ASSIGNED → IN_PROGRESS → AWAITING_VERIFICATION → RESTORED. Only the final verification clears the fault.
- Version checks reject stale or duplicated mutation attempts. Every successful action records operator, reason, wall-clock time and simulation time.
- The clock advances by one explicit simulated minute. Dark signal loads add 12 modeled queued vehicles per minute; powered signals drain up to 18. This is an uncalibrated causal exercise, not measured traffic or a traffic-flow forecast. Restoring power does not instantly clear queues.
- The map requests assets for its viewport and zoom. It shows substations at overview, the selected substation's supply and feeders at neighborhood scale, and its distribution transformers/signals at zoom 14+. Selecting an asset focuses the map. Substations with affected descendants turn orange even when the station itself retains supply.
- Geometry is cached in the browser until viewport/selection changes; three-second state polls update supply coloring. The pilot uses batched GeoJSON, not thousands of DOM markers. A full utility-scale implementation still needs spatial indexing, aggregated tiles and clustering.

## Validation

- 39 backend tests pass, including six electrical tests for generation/connectivity, descendant propagation, persistence/restart, overlapping faults, queue recovery, illegal transitions, stale versions and viewport detail.
- Production frontend build and lint pass.
- Browser integration test uses a disposable real electrical backend, verifies visible map assets, then exercises fault → queue growth → crew assignment → repair → verification → queue recovery across both portals. It does not alter the user's saved world.
- Current traffic corridor and incident records were captured and restored during the local service reload; exact corridor/incident equality and unchanged revision were verified. Existing routing code was not changed.

## Remaining gaps

The pilot has no real electrical inventory, demand telemetry, calibrated equipment capacities, electrical load-flow/protection model, authentication or enforced staff roles. Labels make these limitations explicit. Supply entries are independent modeled sources, not an imported upstream transmission network.

Signal queues belong to this electrical exercise. They do not yet change road costs, ambulance routes or traffic dashboard incidents. There is no automatic continuous clock, live GPS, Google/Gemini/Groq integration, full utility-scale asset allocation, metro simulation or unified command map in this increment. Those remain in the broader portal/realtime plans. The current API provider keys remain unconfigured.

## Files

- `backend/electric_engine.py`: persisted graph/state and `/electric` endpoints.
- `backend/test_electric.py`: isolated domain regression tests.
- `web/src/components/electric/ElectricWorkspace.tsx` and `electric.css`: shared command/field UI and MapLibre map.
- `web/src/app/electric-command/page.tsx`, `web/src/app/lineman/page.tsx`: portal entry points.
- `web/tests/electric.spec.ts`: end-to-end workflow against an isolated backend on port 8002.

## Road-based layout refinement

The v2 generator uses the largest connected eligible local-road component within the study bounds: 48,199 road nodes and 64,085 undirected connections from the supplied `hyderabad_roads.geojson`. It excludes motorway/trunk classes, marked bridges/tunnels and explicitly restricted roads. Road availability does not establish whether a real utility site or underground cable is feasible.

The generated layout is frozen in `backend/data/electric-road-layout.json`. All 6,300 distribution transformers have unique street-node positions. The 20 substations have irregular coordinates; feeder paths have intermediate road vertices rather than straight spokes. IDs, supply parents and live simulation state were preserved during migration, with an SQLite backup of the previous layout. City overview markers scale with zoom; internal assets are hidden until closer inspection.

Validation additionally checks unique positions, irregular coordinates and every feeder/transformer connection endpoint. The browser workflow passes with both neighborhood and city overview rendering. The current saved electrical state was verified unchanged after migration.
