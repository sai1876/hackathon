# Main Command Center — 2026-09-03

The supplied images are visual references only. Their sample risk levels, weather, confidence scores, percentages, alerts and vehicle records are not data sources.

## Current interface

- `/command` is the main AegisGrid Command Center and the website's default landing page.
- The reference-inspired layout has a dominant central map, compact left/right operational panels and a bottom scenario-control bar.
- `/electric-command` and `/lineman` now show database-backed department views. Rainfall, demand sliders and exercise injection no longer appear there.
- Traffic's event-injection and exercise-advance controls were removed. Ambulance requests no longer offer a synthetic-exercise checkbox.
- Missing observations display as unavailable. Empty database inventory tables explicitly say there are no imported records; the generated electrical inventory is not used as fallback.

## Verified database audit

Supabase contains 374,988 `road_segments` and one registered source: OpenStreetMap Hyderabad Road Network, provenance REAL.

The audited substation, feeder, transformer, electrical-state, traffic-state, rainfall-state, metro-station, metro-state, incident, system-action, event-log, scenario-control and simulation-run tables are empty. Their schemas exist, but there are no observations or operational assets to read from them.

The main page reads current counts and source metadata from `/command/snapshot`, cached for 15 seconds. It never substitutes a zero count for a query error. The map reads `/command/roads`, which uses the existing Supabase road RPC and parses its `geometry_wkt` output. It requests up to 1,000 records in a small area around the visible map center to avoid costly city-wide queries. The map labels this as a sample, not full coverage. The background map is OpenStreetMap imagery/tiles, not traffic telemetry.

## Simulation status

Scenario controls are centralized but execution is unavailable in database-only mode. Running the earlier generated electrical model would contradict the request for real data. A populated database still needs source provenance, timestamps, verified asset connections/ratings and suitable model inputs before its records can support credible scenarios.

The legacy exercise engine and saved SQLite state were retained for recovery, not relabeled as real. Its clock and mutation endpoint are disabled by default (`AEGIS_DATA_MODE=DATABASE_ONLY`). Explicitly configuring `EXERCISE` restores the legacy engine for development; it is not exposed by the normal department pages.

Existing process-local traffic/ambulance records were preserved through service reloads. Those older operational pages retain their provenance labels and are not yet migrated into the empty Supabase operational tables. They must not be confused with the database-only panels in the new center.

## Remaining required work/data

- Supply/import actual electrical inventory and relationships, equipment ratings and timestamped load readings.
- Connect rainfall, traffic and metro observations and their provenance.
- Adapt and validate cross-system models against those real inputs, and persist scenario runs/actions into the existing database tables.
- Migrate existing process-local corridor/incident persistence if all department workflows must be database-only.

This increment does not claim working real-data scenario execution when the required source tables are empty.

## Validation

Production build and lint pass. The 43 backend regression tests pass. New browser validation checks actual database road rendering and verifies that department pages do not contain rainfall/load injection controls. Earlier exercise UI tests target the retired generated-data pages and are not evidence for the new center.

## Traffic signal map layer — 2026-09-03

Imported 112 nodes tagged highway=traffic_signals from the supplied hyderabad_nodes.geojson into Supabase junctions. Road names provide context only. OSM nodes may represent approaches rather than unique whole junctions. They are mapped records, not live telemetry or an exhaustive city inventory.

Saved all 60 user-supplied junction names separately as TRAFFIC_SIGNAL_REFERENCE records with null locations and DERIVED provenance. Their user-supplied groups are not verified jurisdiction boundaries. They appear in a searchable location-verification list, never at guessed coordinates.

GET /command/signals reads paginated database records and returns mapped points, unresolved names and provenance. Locations refresh every minute. Database query errors are surfaced; no generated coordinates or phases are substituted. Command Center and Traffic maps use a shared traffic-light marker component with visibility controls and source popups. All phases are UNKNOWN. No controller integration, signal timings, failure detection, power dependency or corridor priority actuation is claimed.

Import audit tool: backend/scripts/import_traffic_signals.py. Default run produces a review JSON; --apply performs idempotent upserts with stable IDs. Existing routing and corridor logic was not changed. Local operations were snapshotted and restored during API restart.

Validation: database endpoint returned 112 mapped points and 60 unresolved names; all phases UNKNOWN. Production build and ESLint passed. Two live browser tests passed (command-center.spec.ts and signals.spec.ts), covering marker count, toggle, popup, junction search, traffic map integration and existing command view checks. Inspected test-results/command-signals.png. These are targeted checks, not a full regression-suite claim.
