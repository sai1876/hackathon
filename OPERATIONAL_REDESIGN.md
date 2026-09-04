# AegisGrid operational redesign — 3 September 2026

Implemented in `D:\aegisgrid`. Local frontend: http://127.0.0.1:3000. Its existing local configuration uses API http://127.0.0.1:8001. The unrelated/protected service on port 8000 was not changed. No deployment, database migration, road-record edit, package installation or paid API integration was performed.

## Inspection: what was real and what was fake

| Area | Before this change | Current operational surface |
| --- | --- | --- |
| Road geometry | Imported OpenStreetMap in Supabase/PostGIS | Retained, with the dated coverage snapshot explicitly labeled |
| Routing | Backend NetworkX, directed road snapping, free-flow costs | Retained; used for corridor requests and re-evaluation |
| Runtime incidents | Actual process-local records, but injected exercises were synthetic observations | Retained, visible with origin, severity, location, time and graph-match evidence |
| Dashboard traffic, flood, weather and power numbers | Deterministic local fixtures from `lib/operations.ts` | Removed from the active pages; unavailable telemetry is stated explicitly |
| Hospitals, signals, transformers, sectors and vehicle markers | Invented demo locations | Removed from the operational map |
| Simulation controls | Local React ticks and scenario switches; no causal backend effect | Replaced by server commands that create incidents, re-evaluate corridors and advance approved synthetic vehicles |
| Recommendations | Mix of incident-derived advisories and static department templates | Backend-derived pending-review and incident-resolution recommendations with evidence and consequences |
| Approvals and ambulance requests | No shared workflow | Backend records, versioned decisions, reasons, positions and event journal |

The previous demo components remain as unused source files; the current traffic/ambulance component tree does not import or display them. There is no claim that operator-entered facts are independently verified.

## Delivered workflow

- `/traffic` has no pickup/destination planner. It shows incoming corridor requests, priorities, status, route evidence, incident consequences and decisions.
- `/ambulance` owns pickup/destination map selection, vehicle/destination inputs and corridor submission. Requests are idempotent by request key for retries. The page also shows status/decision history and supports manually reported location updates.
- Traffic reviews, approves or rejects a pending request with an operator identifier and reason. Completion closes an approved corridor. Invalid transitions and stale versions return HTTP 409; invalid input returns 422.
- Approved corridors expose an initially-off map toggle for the selected ambulance. It controls both route and current reported/synthetic location. Pending, rejected and completed requests do not appear as approved traffic overlays. Multiple requests are retained; operators select one corridor at a time for map viewing.
- A route change or route failure revokes approval and pauses exercise movement. Old route geometry is removed on calculation failure. Changing a reported position also requires review again.
- Polling reads shared backend state every three seconds when idle. It never creates events or moves vehicles. Snapshot ordering prevents older responses from overwriting newer ones; errors and stale connection status are visible.
- Decision entry is tied to the reviewed version. A changed request while writing a reason disables the decision until the operator reviews and updates it.
- The event journal records creation, route evaluations, unavailability, approvals/rejections/completion, position reports, simulation steps and incident resolution, with timestamps, actor labels, evidence IDs and provenance.

## Event simulation and causal consequences

The operator chooses a type and a map point, then injects a backend event. That creates a SYNTHETIC incident through the existing incident engine, re-evaluates every active corridor under the shared runtime lock, and records an exercise awaiting action. Changed routes return to PENDING. Resolving the incident removes its closure, re-evaluates corridors, and transitions the exercise to RESOLVED.

For ambulance exercises, create a synthetic corridor on `/ambulance`, approve it on `/traffic`, enable the overlay, and advance it in 15-second increments. Each command advances server-owned position along the approved GeoJSON line using a uniform-speed fraction of free-flow ETA. It trims remaining geometry/distance/ETA and completes the exercise on arrival. Unapproved, closed or operator-reported vehicles cannot be advanced by the simulation endpoint. No browser timer, canned path, fake GPS or automatic infrastructure action is involved.

Road blockage, accident, waterlogging and signal failure are selectable events, but all deliberately retain the existing backend's **single-directed-edge closure model**. They are not calibrated traffic-flow, flood or signal models. Route evaluations that include synthetic incidents carry an explicit warning and per-incident input evidence. Incident graph matches are labeled as belonging to the evaluated graph, not a citywide closure inventory.

## Backend compatibility and files

Unchanged routing implementation: `route_engine.py`, `endpoint_snapping.py`, `graph_manager.py`, `incident_engine.py`, `models.py`, database access, schema and stored road data.

`main.py` retains `/health`, `/route`, `/incidents` and incident delete contracts. The legacy incident create/delete handlers now additionally notify the operational engine and re-evaluate active corridors under the existing runtime lock.

Added endpoints:

- `GET /operations`
- `POST /corridors`
- `POST /corridors/{id}/decision`
- `POST /corridors/{id}/reevaluate`
- `POST /corridors/{id}/position`
- `POST /simulation/events`
- `POST /simulation/corridors/{id}/advance`

Added `backend/operations_engine.py` and `backend/test_operations.py`. Added the shared `OperationsWorkspace.tsx`, its `dispatch.css`, `/ambulance/page.tsx`, `lib/dispatch.ts` and `types/dispatch.ts`. Replaced the traffic dashboard composition, removed demo layers from `TrafficMap.tsx`, and exported the existing API request helper. Updated frontend workflow specifications while preserving coverage tests. Updated README and marked prior redesign/validation reports as historical.

## Verification performed

- **27 backend tests passed**: 17 existing API/endpoint-snapping tests and 10 new workflow tests. Coverage includes route preservation, directionality, snapping, immutable cached graph, incident detours/restoration, stale and concurrent decisions, idempotent creation, unavailable-route retry, simulation lifecycle, reported-position review, simulation provenance restrictions, arrival and read-only snapshots. Database calls are patched in these tests; their console messages referring to Supabase describe fixtures, not real database mutations.
- **Production build passed** with TypeScript checking, generating `/traffic` and `/ambulance`.
- **Lint passed**, no warnings.
- Both running local pages returned **HTTP 200** after loading the new production frontend; `GET /operations` returned the new process-local schema.
- A real read-only integration route from `(17.55795, 78.36348)` to `(17.54157, 78.36377)` returned **1,895.84 m, 170.63 s free-flow, 25 directed edges**, source OpenStreetMap. The first uncached evaluation took **13,523.23 ms**. This validates the existing Supabase/NetworkX routing path, not observed traffic speed or ambulance travel time.
- Five Playwright scenarios were updated and successfully discovered with `playwright test --list`: approved overlay visibility, ambulance request submission, stale backend handling, coverage toggle and coverage failure. **They were not browser-executed in this session; no screenshot/visual QA was performed.** The Sites skill limits browser QA to explicitly requested browser testing. Build success is not a substitute for end-to-end UI validation.

The original API on 8001 had zero active incidents before restart. No live operational requests or exercise incidents were seeded by validation. Tests used isolated state, and the live smoke test called only `/route`. Services are running hidden on ports 3000 and 8001.

## Remaining gaps

1. **Persistence:** operational records and incidents remain process-local, reset on restart, and require one worker. The event journal retains the latest 500 events. Durable storage and bounded retention for corridor/exercise records are not implemented.
2. **Identity:** there is no authentication, role enforcement or trusted actor identity. Operator names are entered text. The two pages separate workflows, not security permissions.
3. **Telemetry/actuation:** no live traffic, GPS, weather, power, hospital-capacity, signal-control or dispatch integration. An approved corridor is an operator coordination record, not an actuated green wave. A position timestamp is a last report, not a live tracking guarantee.
4. **Model fidelity:** event types share the original closure semantics; the incident engine matches one nearest directed edge per evaluated graph. Ambulance progression uses uniform exercise speed derived from free-flow cost. Recommendations are deterministic rules, not AI or measured benefit predictions.
5. **Performance:** legacy incident mutations synchronously re-evaluate active corridors under one runtime lock. Cold graph loads can delay all snapshots and decisions. There is no queue/worker infrastructure or load test.
6. **UI verification:** updated browser interaction and map-rendering tests still need execution; responsive and visual behavior have not been screenshot-reviewed in this session.
