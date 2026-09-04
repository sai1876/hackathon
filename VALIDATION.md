> Historical record of the previous routing/demo interface. The current operational redesign and its verification are documented in [OPERATIONAL_REDESIGN.md](OPERATIONAL_REDESIGN.md).

# Implementation and verification — 2026-09-03

## Road expansion and presentation coverage — latest follow-up

- Added 16,859 REAL OSM directed segments around Mallampet/Bachupally (374,988 total). Downloaded 23,859 candidate edges; 6,927 matched the local overlap, and a further 73 existing external IDs were ignored by the database unique constraint. Original records were not updated or deleted; no schema changes.
- Full-table preservation audit: original 358,129 rows had fingerprint `6878ab21c1e4e58605643a1dabd108f5` before import; excluding the new import batch gives the identical fingerprint afterward. Fingerprint: MD5 of ID-ordered concatenated per-row MD5 of `to_jsonb(row)::text`.
- Prepared graph joined existing roads at 146 matching OSM junctions. Checked directed geometries and connectivity before insertion; read-back validated the persisted graph and original overlap fingerprint. A transient HTTP/2 disconnect during read-back was recovered using the read-only `--verify-only` command; no duplicate insert attempt was needed.
- Exact screenshot points now return HTTP 200: A (17.55795, 78.36348), B (17.54157, 78.36377); distance 1,895.84 m, free-flow ETA 2.84 min; endpoint offsets 3.70 m and 7.60 m. No arbitrary connector lines or enlarged snap tolerance.
- Added `backend/import_roads.py`, separate `requirements-import.txt`, and read-only `coverage_snapshot.sql`. Import artifacts are ignored; the small public GeoJSON snapshot is retained for the frontend.
- Green overlay derives from occupied 0.0025-degree cells intersecting stored geometries, unioned with holes retained. Metadata includes source/license, snapshot timestamp and count. It explicitly labels approximate data presence rather than guaranteed routing. Coverage toggle and View all coverage preserve route/incident layers and existing layout. Loading and failure states are explicit.
- Unit tests: 17 passed. Next production build/TypeScript and ESLint passed. Coverage browser checks verify visible rendered features, on/off behavior, framing without selecting a route point, and a graceful download-failure state. Existing route/incident/reset regressions retained.
- Database service-key configuration unchanged and never included in the overlay. Backend restarted on 8001 with zero active incidents to clear stale graphs; frontend remains on 3000. No cloud deployment.

Earlier sections below describe prior implementation stages; their no-insert statements predate this explicitly requested expansion.

## Endpoint gap fix — follow-up

- Added `backend/endpoint_snapping.py` and `backend/test_endpoint_snapping.py`.
- Endpoints now project onto the nearest road segment within 100 m. Request-local partial edges preserve direction, closures, geometry and proportional distance/ETA. The immutable spatial index is cached with the base graph.
- Added `snapping` metadata and `endpoint_snap_ms`; retained old fields. Markers A/B use snapped coordinates. Hollow original-click points and dashed non-routed offsets explain the selection displacement; offset lengths are excluded from route metrics.
- Changed graph manager, route engine, frontend types, TrafficMap, RoutePanel, shared CSS, browser tests and README. No database writes/schema changes or new dependencies.
- Direction audit around (17.468, 78.448): all 12,024 sampled real directed edges match their node coordinates; no reversed/inconsistent geometries found in that sample. Exact screenshot click coordinates were not available.
- `python -m unittest test_api test_endpoint_snapping -v`: 17 passed, including long-edge interiors, one-way/reverse geometry, closed edges, same-point rejection, >100 m rejection, explicit offsets, curved/multi-edge routes and cached cost isolation.
- Production build and lint passed. Both browser tests passed (40.7 s cold run), now asserting marker coordinates equal reported snapped positions and returned route endpoints. Real route rendering and incident lifecycle still pass. The first checked route reported A offset 9.6 m / B offset 39.2 m; both A/B markers sit at the line endpoints.
- Earlier results below document the original implementation; nearest-node endpoint behavior has been superseded by this fix.

## Running services

- Frontend: http://127.0.0.1:3000/traffic (production build)
- Updated backend: http://127.0.0.1:8001
- Health: http://127.0.0.1:8001/health
- Backend API docs: http://127.0.0.1:8001/docs
- The older process on port 8000 was not stopped: Windows denied permission. No existing tables, road data, or secrets were modified. The new runtime has zero active test incidents after cleanup.

## Files created

- `.gitignore`, `README.md`, `VALIDATION.md`, `render.yaml`
- `backend/.env.example`, `backend/requirements.txt`, `backend/test_api.py`
- `web/.env.example`, ignored `web/.env.local` (local port-8001 override)
- `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`, generated `web/next-env.d.ts`
- `web/postcss.config.mjs`, `web/eslint.config.mjs`, `web/playwright.config.ts`
- `web/scripts/prepare-maplibre.mjs`, `web/tests/traffic.spec.ts`
- `web/src/app/layout.tsx`, `web/src/app/page.tsx`, `web/src/app/globals.css`, `web/src/app/traffic/page.tsx`
- `web/src/components/traffic/TrafficDashboard.tsx`, `TrafficMap.tsx`, `RoutePanel.tsx`, `IncidentPanel.tsx`
- `web/src/lib/api.ts`, `web/src/types/aegis.ts`
- Ignored generated output: `.venv`, `web/node_modules`, `web/.next`, `web/public/vendor/maplibre`, `web/test-results`

## Existing files changed

- `backend/graph_manager.py`: per-response cache-hit metadata; existing paging/cache preserved.
- `backend/route_engine.py`: additive timings, incident snapshot in response, segment-distance snapping with 150 m limit, affected geometry, same-node validation.
- `backend/models.py`: coordinate validation and explicit incident provenance.
- `backend/incident_engine.py`: retain incident provenance.
- `backend/main.py`: configurable local CORS, runtime serialization, sanitized unexpected errors.
- `backend/database.py` and the existing `backend/.env` are unchanged.

## Commands run

Read-only repository/file inspection used PowerShell `Get-Content`, `Get-ChildItem`, and `rg`. Official Next.js, MapLibre, Supabase, OSM and Render docs were checked. Main implementation/verification commands:

```text
<bundled-python> -m venv .venv
.venv\Scripts\python.exe -m pip install fastapi uvicorn supabase networkx shapely python-dotenv httpx
npm.cmd install --save-exact next react react-dom maplibre-gl
npm.cmd install --save-dev --save-exact typescript @types/node @types/react @types/react-dom @types/geojson tailwindcss @tailwindcss/postcss eslint eslint-config-next @playwright/test
..\.venv\Scripts\python.exe -c "import main; print('Backend import OK')"
..\.venv\Scripts\python.exe -m unittest test_api -v
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
npm.cmd run build
npm.cmd run lint
npm.cmd run start -- --hostname 127.0.0.1
npx.cmd playwright test
```

`Invoke-RestMethod` tested GET /health, POST /route twice (cold/warm), and GET /incidents. Browser tests exercised POST/DELETE incidents and automatic rerouting. A value-based PowerShell scan compared the actual backend service key against frontend source, compiled browser bundles and public assets, printing only pass/fail. No key was printed or copied.

## Results

| Check | Result |
| --- | --- |
| Backend import | PASS |
| Uvicorn startup, GET /health | PASS on 8001 |
| Unit tests | 6 PASS |
| Next production build / TypeScript | PASS |
| ESLint | PASS, no warnings after excluding generated vendor code |
| Browser integration tests | 2 PASS; final run 11.5 s |
| Map rendering | PASS: nonzero rendered route features asserted; desktop/mobile screenshots inspected |
| Real incident lifecycle | PASS: create, automatic route call, marker, resolve, recalculation, cleanup |
| Deterministic detour and restoration | PASS on isolated SYNTHETIC graph; base cost unchanged |
| Stale request/reset and API errors | PASS |
| Mobile horizontal overflow at 390 px | PASS |
| Secret leakage scan | PASS: actual secret absent from frontend source, bundles and public assets |
| Final active incidents | Zero |

Real Hyderabad route: start (17.385, 78.4867), destination (17.4399, 78.4983), 7.81 km, ETA 8.21 min. Loaded graph: 45,397 directed edges, 17,927 nodes.

| Timing | Cold | Cached |
| --- | ---: | ---: |
| graph_load_ms | 56330.40 | 212.62 |
| nearest_node_ms | 27.69 | 26.64 |
| route_compute_ms | 32.55 | 32.19 |
| total_ms | 56390.66 | 271.47 |
| cache_hit | false | true |

## Issues found and addressed

- First build failed because MapLibre 6 has named exports, not a default export. Fixed.
- GeoJSON lines initially did not render because the MapLibre module worker was missing after bundling. Added same-origin generated worker/shared-module assets and an actual rendered-feature browser assertion. Fixed.
- Browser sandbox blocked map tile network access. Re-ran visual tests with approved network access; tiles and route verified.
- Initial ESLint findings corrected. Generated dependency files excluded from lint.
- Starting on port 8000 failed because the existing server owns it; attempted approved restart was denied by Windows. New backend and ignored frontend override use 8001.
- Starlette emits a non-fatal test-client HTTPX deprecation warning. Tests pass; no runtime failure observed.

## Remaining limits and next step

No cloud deployment was performed. Render deployment files are provided, not cloud-validated. Incidents and an unbounded graph cache remain process-local; use one worker. Cold requests are slow. ETA is free-flow, not live traffic. Incident snapping affects one directed edge, not a complete bidirectional closure. Fixed-bbox connectivity failures remain possible. No auth/rate limiting yet: use only with trusted operators, not as a public municipal service.

Next: add operator access control and persistent incident/audit identity, then memory-profile and bound the graph cache before public deployment. See README for full setup, deployment and operating limitations.
