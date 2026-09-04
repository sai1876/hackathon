# AegisGrid route realism and GTFS metro implementation

Recorded 2026-09-03T18:30:18.651863+00:00. Repository: D:/aegisgrid. Local services: frontend 3000, backend 8001. Existing corridor state was preserved during service reloads. No deployment to Render was performed.

## What is now working

The permanent routing architecture remains OSM → Supabase/PostGIS → NetworkX. The audited road count is 374,988 directed records, not the older count in the brief. Routing uses directed-edge-state Dijkstra over the NetworkX graph so incoming direction affects turn cost. It returns up to three distinct routes and preserves the existing route, route_segments, snapping and corridor response fields.

Metro Command at /metro-command displays geographic GTFS tracks, 57 stations and moving timetable-derived trips. The same layer is on /command. All playback setup remains in /command. Playback was left running at 5× after browser verification. These are schedule-derived positions, never live GPS. The PDF schematic remains a source reference; GTFS replaced the provisional fixed-timing schematic playback.

## Current routing model and new costs

Previously: base travel time, closures, and an optional rainfall multiplier; one shortest path.

Now: length / effective speed plus queue delay, modeled signal delay, incoming-direction turn costs, road-class preference, access penalty. Known closures and prohibited/private access are impassable. Existing synthetic rainfall is translated once. Fresh REAL traffic_state readings (non-simulation, within five minutes) can supply speed/blockage; there were no fresh readings at verification. Missing traffic is explicitly unavailable and uses base speed, not fabricated congestion.

Road-class preference is seconds per kilometre, avoiding a fixed charge for every tiny OSM edge. Turn penalties cover straight, slight, left, right, sharp and U-turn movements, with service/minor-road transitions and junction branching. Modeled ETA includes travel, queue, signal and turn time; hierarchy/access preferences affect the route score separately. Capacity metadata is not applied again as an extra speed penalty when congestion is represented by speed.

Known OSM signal-node matches can incur a configured delay. This is a CALIBRATED assumption, not a live signal phase. Road geometry and signal location provenance remain separate from cost provenance. Initial configuration is labelled INITIAL_UNVALIDATED_PRIORS, not validated driver behavior.

Alternative generation is bounded (up to six additional searches), rejects looping candidate alternatives and highly overlapping edge sets, and caps excessive detours. It may return fewer than three alternatives. The primary route minimizes the modeled score, not distance alone.

GraphManager reuses a containing cached operational area and keeps up to six cached graphs. Each request modifies a graph copy. Timings exposed include graph_load_ms, cost_prepare_ms, nearest_node_ms, route_compute_ms, alternatives_ms, google_reference_ms, calibration_analysis_ms and total_ms. Google timings are zero on ordinary routing.

## Test OD pairs and Aegis results

24 representative area pairs are in backend/traffic/calibration_pairs.json. Coordinates are actual supplied OSM nodes selected near named areas, not verified POI/hospital entrances. Two were evaluated on actual Supabase road graphs, then repeated using the RAM cache. The other 22 are prepared, not claimed as tested.

| Pair | Old distance / base ETA | New distance / modeled ETA | Turns | Cold total | Warm total |
|---|---|---|---|---|---|---|
| HITEC City → Gachibowli | 5.63 km / 5.87 min | 6.14 km / 6.96 min | 6 | 11.66 s | 0.96 s |
| Madhapur → Kondapur | 4.42 km / 6.10 min | 4.55 km / 7.37 min | 8 | 15.15 s | 1.63 s |

Both returned three distinct alternatives. HITEC City–Gachibowli's recommended route used 86.59% primary roads by length; Madhapur–Kondapur used 55.59%. These are Aegis road-class metrics. No claim about Google's preferred road classes is made. Full coordinates, route alternatives and measured timings: backend/route-realism-results.json. Evaluation script: backend/evaluate_route_realism.py.

## Google reference results and mismatch diagnostics

Actual Google API calls made: **0**. The backend key is empty and GOOGLE_REFERENCE_ENABLED defaults to false. Provider tests used mocks. No Google reference results or real Google mismatch classifications are claimed.

The reference provider requests distance, static duration, traffic-aware duration and route labels only. It does not request polylines. Standard route requests never call Google. /calibration/google/fetch and /calibration/google/fetch/{pair_id} require a backend operator token and explicit approval; batches are limited to five selected pairs. No recurring Google polling was added.

Comparisons compute distance/ETA differences and configurable GOOD_MATCH / MODERATE_MISMATCH / HIGH_MISMATCH bands. Diagnostics refer to Aegis's local/service-road share, turn count, speed estimates and possible topology/restriction problems. They do not invent Google road-class mix or overlap.

Google reference metrics are transient process-memory snapshots, expiring after one hour, and are reused on reads without new calls. **Persistent Google metric snapshots from the brief were not enabled** because standard Google Routes caching restrictions need to be respected; no arbitrary permanent retention is assumed. Restart discards those transient references. No Google geometry or road graph is stored. See https://developers.google.com/maps/documentation/routes/policies .

## Persistent usage guard and current counters

The Supabase api_usage table and aegis_google_budget RPC serialize reservations using a row lock. Each transport attempt makes one reservation, no automatic HTTP retries or redirects. A hard limit or a database error blocks the request and leaves Aegis available. Counter periods use UTC YYYY-MM. Process crashes between reservation and dispatch may conservatively overcount; the application never releases uncertain reservations or risks exceeding the cap.

SAFE <75%; WARNING >=75% and below hard limit; STOPPED at hard limit. Configured soft limits are exposed independently. Limits can be lowered by environment configuration but are never silently raised by another process during the month.

| API | Used/reserved | Effective hard limit | Status |
|---|---|---|---|
| GOOGLE_ROUTES | 0 | 100 | SAFE |
| GOOGLE_GEOCODING | 0 | 50000 | SAFE |
| GOOGLE_PLACES | 0 | 28000 | SAFE |
| GOOGLE_ROADS | 0 | 24000 | SAFE |
| GOOGLE_ELEVATION | 0 | 24000 | SAFE |

Last Google attempt: none. The existing Routes hard limit of 100 was preserved rather than raised to 28,000. These are APPLICATION counters and caps, not billing-provider quotas, individual billable SKU counters, or a guarantee of a free tier. Calls made by other applications on the Google project are not visible here. Other Google API groups are tracked, but no Geocoding/Places/Roads/Elevation transport was added or invoked.

New tables have RLS enabled; anon/authenticated access revoked. Budget/config mutation RPCs are service-role only. The service key and Google key remain on the backend. Configuration example: backend/.env.route-reference.example. AEGIS_OPERATOR_TOKEN is also required before manual calibration actions become available.

## Calibration before/after and approval

Current configuration version: 0; validation status: INITIAL_UNVALIDATED_PRIORS. No live calibration change was applied. Initial before/after values remain unchanged.

/calibration/apply validates allowed parameters and bounds, requires explicit operator approval, token, operator name, evidence and expected configuration version. The database atomically records before/after values. /calibration/revert restores the preceding values with another audit record. Automatic graph rewriting and blind optimization are absent. SQL apply/revert verification used a transaction and rolled back all test changes.

## Metro data and behavior

Source: user supplied Telangana_opendata_gtfs_hmrl_02_September_2026.zip. SHA-256 c35bda6768e71fdef742080d1436a5d751d7b2a64f6882839574d768a6498f2a.

Imported: 3 routes; 57 parent stations; 705 total stops/platforms/entrances; 2,895 trips; 62,759 stop-time records; 2,450 shape points across 6 directional shapes. Station and trip inventory uses existing metro_lines, metro_stations and metro_trips tables. Normalized calendars, stop times and shapes are retained in the GTFS data_sources record. Playback anchors are persisted in simulation_runs with optimistic version checks. The existing simulation tables were used after the migration connector failed; no untracked replacement datastore was introduced.

The backend chooses the service calendar, active trips, station dwell and in-transit progression. Positions interpolate along shape_dist_traveled, including track bends. The browser only renders returned positions. Start, pause, reset, speed and service-date/time controls are centralized in /command. Pause/resume survives API restart through the persisted clock anchor. At the 08:00 test time the feed had 44 active scheduled trips; the count varies with timetable time.

## Tests and verification

- 62 backend unittest tests passed, including existing corridor/blockage/snapping regressions and new road preference, turn, alternative, mocked Google, budget failure, operator approval, no-frontend-secret and GTFS shape/calendar/dwell tests.
- Database transactional guard test passed: first request reserved one slot; the next was blocked at the hard cap without increment. Changes rolled back.
- Database apply/revert test passed and rolled back; live configuration version remained unchanged.
- Aegis search continued after mocked Google blocking.
- Production Next.js build and ESLint passed.
- Three live Playwright checks passed: command-center.spec.ts, signals.spec.ts and metro-gtfs.spec.ts. Verified street-zoom road behavior, map signals, geographic metro markers, movement, pause, layer toggle and manual comparison controls.
- Visually inspected test-results/metro-gtfs.png and test-results/main-command.png. This is not a claim that every historical browser suite passed.

## Files created

backend/core/api_usage_guard.py; backend/providers/google/routes_provider.py; package initializers; backend/traffic/routing_config.py; cost_engine.py; turn_costs.py; route_search.py; route_calibration.py; observations.py; calibration_pairs.json; backend/migrations/20260903_route_realism.sql; 20260903_route_attributes.sql; backend/.env.route-reference.example; backend/evaluate_route_realism.py; route-realism-results.json; test_route_realism.py; test_metro_gtfs.py; backend/metro_engine.py; backend/scripts/import_metro_reference.py; import_metro_gtfs.py; web/src/components/command/ApiBudget.tsx; web/src/components/traffic/RouteCalibration.tsx; web/src/components/metro/MetroMap.tsx; MetroCommand.tsx; metro.css; web/src/app/metro-command/page.tsx; web/tests/metro-gtfs.spec.ts; this report.

## Files modified

backend/route_engine.py; graph_manager.py; endpoint_snapping.py; models.py; main.py; test_api.py; test_blockages.py; test_operations.py. Existing ETA expectations changed where modeled turn delays now apply; closure/reapproval assertions remain.

web/src/components/command/MainCommand.tsx; web/src/components/traffic/OperationsWorkspace.tsx; TrafficMap.tsx. Existing user changes were preserved; no git commit was made (this folder is not a git repository).

## Known limitations and next step

Google reference fetch is untested against a real provider because no key is configured. Configure a restricted backend key, verify actual Google billing allowances and use one explicitly approved pair first. Persistent reference retention requires a suitable policy/licensing decision; current snapshots are transient.

The graph lacks full turn-restriction/access coverage where the imported OSM data omitted it. Initial weights need field or operator validation. Fresh traffic observations are absent. Signal phases remain unknown; configured signal delays are modeled. Route alternatives are bounded heuristics rather than exhaustive k-shortest routes.

GTFS is a supplied schedule, not independently verified live operation. Train delays, cancellations, occupancy, platform control, and cross-effects from power/flooding are not implemented by timetable playback. No GTFS-Realtime vehicle feed is connected. The older rainfall/electrical simulation controls remain disabled in database mode. The main live-train-state table is intentionally not populated with schedule-derived positions that lack an explicit provenance column.

Next recommended step: validate the supplied GTFS against current operating service and connect a provenance-bearing realtime feed if available; separately run one approved Google reference pair once credentials and billing caps are configured.

## Metro schematic and timetable movement update
Metro Command now uses a non-geographic SVG network diagram with station order from imported GTFS data. Active train schedules include arrival/departure times. The diagram advances positions continuously against the backend playback clock, holds trains at stations during scheduled dwell, and stops extrapolation after five seconds without a fresh snapshot. Main Command retains the geographic overlay. Playback speed was set to 1x for real-time timetable pacing. Build, lint, four metro timing unit tests, and the updated browser movement/pause/schematic check passed. This remains scheduled playback, not live GPS telemetry.
