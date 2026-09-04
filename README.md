# AegisGrid

## Current local architecture (2026-09-05)

`D:\aegisgrid` is the only application source tree. FastAPI serves the backend, Next.js serves the portals, and the current multi-domain simulation is stored in one versioned Supabase run. Start the local app with `restart-local.ps1` when an existing local instance is running. The script captures compatibility state for older endpoints and launches both processes from this repository.

Active portals include Command Center, Traffic Command, Ambulance, Electric Command, Lineman, Metro Command, Metro Pilot and Google Operations. The Metro operating model, directional signal registry, emergency workflow and shared scenario clock are documented in `METRO_OPERATIONS_V3.md`, `EMERGENCY_WORKFLOW_IMPLEMENTATION.md`, and `SHARED_SIMULATION_HANDOFF.md`.

Data labels are strict: imported geometry and schedules remain source data; generated demand, queues, asset topology, motion and controller phases are simulation state; Google Weather and Google traffic overlays are observations. Generated values are stored and read back from the shared runtime rather than embedded as dashboard constants.

The detailed history below includes earlier stages of the prototype. Where it conflicts with this section or the dated implementation reports, this section describes the current app.

---


The operational workflow is now split between `/ambulance` and `/traffic`. See [OPERATIONAL_REDESIGN.md](OPERATIONAL_REDESIGN.md) for the current architecture, provenance audit, validation and known limitations. Older visual-redesign notes describe the superseded demo dashboard.

Next.js App Router / TypeScript / Tailwind / MapLibre dashboard backed by the existing FastAPI, NetworkX and Supabase/PostGIS road graph. No database schema or base road records were changed. No AI provider, paid API, or simulated route animation is used.

## Coverage overlay and northwest expansion

Coverage is on by default: translucent green shows approximate imported road-data presence, mint shows the calculated route, and amber shows a blocked segment. Use **Coverage ON/OFF** to hide the shading and **View all coverage** to frame it for a presentation. The existing dashboard layout is preserved.

The snapshot is generated from actual stored road geometries, not a rectangular or administrative boundary. Each shaded cell is 0.0025 degrees (about 265 × 278 m) and intersects at least one imported road. Shading does not guarantee every point is drivable, connected, or within the 100 m snap limit. Unshaded basemap roads may lack imported routing data. This is a dated snapshot, not a live coverage feed.

On 2026-09-03, an append-only OpenStreetMap drive-network import added **16,859 directed segments** around Mallampet/Bachupally; all **358,129 original records remain unchanged**, for **374,988 total**. Requested bounds: west 78.32, south 17.50, east 78.405, north 17.585. OSMnx retains some boundary-crossing roads. Existing external IDs are ignored, never overwritten. Geometry provenance is REAL; free-flow speeds are DERIVED routing baselines using OSM maxspeed where available and documented class defaults otherwise. This is not live traffic or guaranteed speed-limit data.

Maintenance tooling (not installed on the API runtime):

```powershell
cd D:\aegisgrid\backend
..\.venv\Scripts\python.exe -m pip install -r requirements-import.txt
..\.venv\Scripts\python.exe import_roads.py
# Review data/imports/mallampet-bachupally-2026-09-03/report.json before applying.
..\.venv\Scripts\python.exe import_roads.py --apply
# If read-back was interrupted, resume without inserting again:
..\.venv\Scripts\python.exe import_roads.py --verify-only
```

The importer is scoped to this expansion and source record, not a general-purpose worldwide importer. It validates shared junction coordinates, directed geometry, and the sample route before writing. GraphML, prepared rows, original overlap snapshot, inserted IDs and reports remain in ignored `backend/data/imports/`. Keep these artifacts for audit; no automatic rollback/delete is provided.

After a future import, run the read-only `backend/coverage_snapshot.sql` in trusted database tooling and save its returned `coverage` object as `web/public/data/road-coverage.geojson`. Regenerate/redeploy this public snapshot whenever the underlying dataset changes. It contains no database credentials. Safely restart the backend to clear stale cached graphs only after accounting for active in-memory incidents.

## Local run

Windows PowerShell, from `D:\aegisgrid`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Use the existing `backend/.env`; see `backend/.env.example`. Never put its service-role key in frontend configuration.

In a second terminal:

```powershell
cd D:\aegisgrid\web
npm.cmd ci
npm.cmd run build
npm.cmd run start
```

Frontend: http://127.0.0.1:3000/traffic. Default backend: http://127.0.0.1:8000.

`prebuild` / `predev` generate same-origin MapLibre 6 worker assets from the pinned npm package, including its license. Keep the generated `public/vendor/maplibre` assets in deployment output; do not substitute a remote worker CDN.

**This verification session uses backend port 8001.** Port 8000 belongs to a protected pre-existing Python process that Windows would not allow us to restart. The ignored `web/.env.local` points at `http://127.0.0.1:8001`; `.env.example` retains port 8000. Stop your old backend yourself if desired, change the local API URL, and rebuild the frontend. `NEXT_PUBLIC_API_URL` is embedded at build time.

## Workflow

1. Open `/ambulance`. Enter the vehicle identifier, destination name and priority. Pick the pickup and destination on imported roads. Check **Synthetic exercise request** only for a demo vehicle; submit the corridor request.
2. On `/traffic`, select the incoming request and review its route evidence, distance, free-flow ETA, location provenance and incident consequences. Enter a traffic operator identifier and decision reason, then approve or reject. A stale version cannot be approved.
3. After approval, enable **Show ambulance route and location on map** for the selected corridor. The toggle is off by default. Pending, rejected and completed corridors cannot appear as approved map overlays.
4. Use **EVENT SIMULATION** to select an event type and map location, then **Inject backend event**. The backend creates a SYNTHETIC incident, recalculates active corridors and requires new approval if an approved route changes or becomes unavailable. All current event types use the existing single-directed-edge closure model.
5. For an approved synthetic corridor, **Advance selected ambulance · 15 s** advances its server-owned position along the approved route. Reaching the end completes the exercise. There is no browser animation or background timer. This is a uniform-speed free-flow exercise model, not GPS or calibrated vehicle dynamics.
6. Resolve incidents when cleared. The backend removes their runtime closures, re-evaluates active corridors and records consequences in the operational event journal. Operator-reported vehicles can submit a new location on `/ambulance`; that triggers fresh route review.

Counts, pending work, recommendations and event history come from `/operations`, polled every three seconds when idle. No weather, power, traffic-load percentages or fictitious asset locations are shown. Runtime state survives page refreshes but **does not survive backend restart**. Run a single backend worker; there is no authentication or durable approval store yet.

## Backend changes

- Additive response fields: `graph_load_ms`, `nearest_node_ms`, `route_compute_ms`, `total_ms`, `cache_hit`, `incidents`, `snapping`, `endpoint_snap_ms`. Existing fields remain intact. `nearest_node_ms` is retained as a compatibility alias for endpoint snapping time. `snapping` reports requested/snapped coordinates and distances for both endpoints; `start_node`/`end_node` can be request-local virtual IDs for road-interior endpoints.
- Road-interior snapping uses a cached spatial index and request-local partial directed edges, with prorated distance/cost. No base edges are edited. Reverse direction geometry is normalized for routing; inconsistent geometry is rejected rather than drawing a false connection. One-way direction, closures and the existing NetworkX path engine remain authoritative.
- Graph timing includes fetch/build or cached graph copy. Total includes incident application; path timing includes path assembly. Values exclude HTTP serialization/network transit.
- Existing paginated RPC and RAM graph cache retained. Incident cost changes occur only on graph copies.
- Incident snapping uses nearest position on segment instead of midpoint, with a 150 m maximum. Coordinate validation and same-node errors prevent invalid map results.
- Runtime operations are serialized in one process so route calculation cannot race incident updates. `/health` remains independent and checks process liveness, not Supabase connectivity.
- CORS defaults to localhost origins and is configurable via `CORS_ORIGINS`. Unexpected backend exceptions return a generic error; details remain server-side.

## Deployment

No cloud deployment has been performed. `render.yaml` defines a **free** FastAPI service using a single Uvicorn worker. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY as server secrets, and CORS_ORIGINS to the exact HTTPS frontend origin. It uses existing tables and RPCs; no migrations are needed. Follow [Render FastAPI deployment](https://render.com/docs/deploy-fastapi).

Deploy `web` to a Next.js-capable host, using `npm ci`, `npm run build`, and `npm start` (or its native Next.js integration). Set NEXT_PUBLIC_API_URL to the HTTPS backend **before building**. Never expose Supabase credentials to the frontend.

This is a trusted-operator prototype: there is no authentication, authorization or rate limiting yet. CORS is not authentication. Do not expose mutation endpoints to untrusted operators/public traffic before adding access controls. No infrastructure action is executed by the app.

The standard OSM raster basemap is darkened with MapLibre styling, uses visible attribution and browser caching, and requires no API key. It is best-effort, not an unlimited production tile service; no prefetch/offline download is implemented. Observe the [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/). [Render free services](https://render.com/docs/free) can spin down after inactivity and have resource/usage limits; do not rely on them for safety-critical operations.

## Validation

```powershell
cd D:\aegisgrid\backend
..\.venv\Scripts\python.exe -c "import main; print('Backend import OK')"
..\.venv\Scripts\python.exe -m unittest test_api -v
cd ..\web
npm.cmd run build
npm.cmd run lint
npx.cmd playwright test
```

Browser tests require both services running, the local port-8001 override, Chrome at the configured Windows path, and network access for map tiles. Isolated unit tests use explicitly SYNTHETIC graph fixtures, never database writes. Browser test incidents are resolved after execution. Screenshots are ignored under `web/test-results/`.

## Known limits / next work

- First bbox loads paginate sequentially and can take a minute or more. RAM cache is unbounded and copies whole graphs; memory/load testing and a bounded cache are the next performance tasks before hosting on a small instance.
- Routes and incident updates serialize. One worker is required while incidents/cache are in RAM. Restarting loses both; no incident persistence or cross-operator push updates yet (refresh/reload to reconcile).
- Incident binding is evaluated against each loaded graph, affects one directed edge, and is not a full bidirectional road closure. A clicked location more than 150 m from loaded edges has no effect. Route errors may require refreshing incidents to inspect the latest binding.
- ETA uses base free-flow costs, not live telemetry. Endpoints snap to the nearest physical segment within 100 m, not the nearest intersection. Reverse representations of the same segment are considered; nearby parallel roads and grade-separated crossings are not artificially connected. Closed or disconnected nearest segments may fail. Fixed bbox padding remains; `search_radius_m` is an existing unused input. Turn restrictions and advanced accessibility are not implemented.
- Runtime incidents are explicitly SYNTHETIC by default. OPERATOR_REPORTED is accepted by the backend but the dashboard does not offer that mode.
- Recommended next step: add operator authentication/authorization and persisted incident identity/audit trail, then bound/cache-profile the graph before a public deployment. Future AI advice must remain separate from deterministic routing and require safety validation plus operator approval.
