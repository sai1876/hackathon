# Shared simulation implementation and continuation

The previously disabled central controls are now connected to the generated Supabase dataset. The current user run remains paused at its saved time. No observed-data tables were overwritten.

## Implemented
- Main command alone provides polygon selection, rainfall/flood injection, electrical/metro demand multipliers, traffic disruption, signal failure, input end, play/pause/speed.
- One version-checked database row (aegis_sim_runs.configuration.runtime) is the live scenario authority. Seed asset/state/profile tables remain initial conditions. A transactional outbox in that row records events; idempotent archive writes populate aegis_sim_events.
- Water integrates rainfall minus drainage; ending rain leaves water to drain. At 150 mm, intersecting route edges become impassable. Existing closures are preserved. Shared routing changes trigger corridor reevaluation.
- Stored electrical load profiles drive DT load totals; polygon demand changes and approved drainage pumping alter the totals.
- Stored metro entry profiles, train capacities, GTFS departures and downstream destination weights drive queues, boarding, alighting and occupancy. Train movement and all portals use the shared clock.
- Signal phase display uses stored cycle parameters and the shared clock; polygon failure inputs extinguish the modelled signal.
- Main, Electric, Traffic and Metro show shared scenario state. Main dashboard legacy empty-table messages have been replaced with the generated inventory/current model values; reference counts remain separately available.
- Road coloring remains street-zoom only, uses viewport queries, and labels scenario slow/blocked conditions.

## Verification
42 tests passed: test_shared_scenario, test_metro_gtfs, test_blockages, test_endpoint_snapping, test_route_realism. Production build and TypeScript passed.
Live database validation passed in separate run 2855e783-54e2-43eb-8dc9-43c3de1de117: duplicate injection prevented, rain accumulated, pause persisted, four events archived, baseline unchanged. Another labelled validation run exists from an earlier floating-point equality check; neither is the user run.
Browser verified: real inventory displays 60 substations, 240 feeders, 4800 distribution transformers and 120 power transformers; drawing a polygon enables injection. No rainfall was injected into the user baseline during verification.

## Honest limitations / next work
- This is modelled operating data, not live traffic/weather/passenger/controller telemetry. GTFS and OSM are reference sources. Generated electricity locations are not surveyed utility locations.
- Power loading is aggregated from DT profiles. Feeder protection trips, physical load-flow, dependency outages, backup timers and restoration workflows are not yet implemented in this new runtime.
- Metro uses scheduled trips; no dynamic dispatch/headway approval, crew allocation, turnback movement or transfer-aware passenger itinerary is implemented. OD weights are projected onto downstream stations of each train. Road-to-metro mode shift is a bounded modelled uplift, not a conserved road-passenger flow model.
- Drainage dispatch is a rule-triggered simulation recommendation, not a live crew dispatch or a Groq call. Weather drainage thresholds are uncalibrated assumptions.
- All seeded signals currently share the stored initial cycle offset; no surveyed coordination plan exists.
- Legacy corridor/incident operator state remains process-local; the existing restart snapshot wrapper preserves its last captured state. The new scenario state itself is durable in Supabase.
- No additional paid Google/Groq requests were made in this implementation.
- Baseline starts 05:00. Before first timetable service, no trains/boarding is expected. Use the shared speed control to advance; no independent metro clock or rewind.
- Run capped to one service day and 50 scenario areas. Run archive/reset UI is still needed for repeated long sessions.

## Local services / resume
Repository D:/aegisgrid. Frontend port 3000, backend port 8001. A shutdown stops both services; Supabase scenario state survives.
Python D:/aegisgrid/.venv/Scripts/python.exe. Frontend npm run build then Next start from web.
Backend is currently launched using the existing workspace resume-electric-runtime.py wrapper and electric-restart-state.json. Capture /operations before an intentional restart to preserve current legacy corridor state; never overwrite live state with an older capture.
Secrets remain only in backend/.env, backend/.env.simulation and web/.env.local. Never print them.
New database project xaxackeuukwgishxihqc holds simulation state; original project remains reference source. Do not reimport/reset the seed after a run advances.

## Main files
backend/scenario_runtime.py, weather_effects.py, command_data.py, metro_engine.py, operations_engine.py, main.py.
web/src/components/command/ScenarioControls.tsx and MainCommand.tsx; TrafficSignals.tsx; MetroCommand.tsx and MetroOperations.tsx.

## Portal regression fixes
Electric/Lineman maps now load 5,220 generated electrical assets with distinct S/P/F/T symbols and selectable downstream connections; traffic/metro overlays removed from those maps. Co-located assets remain separately selectable. Shared clock started at GTFS first service (06:00); 22 moving trips verified. Added forward simulation-time picker, pause at target, speed controls, and a pre-run first-service button. Rewinding existing state is rejected. 15 focused tests and production build passed. New ElectricLayer.tsx and /command/scenario/electric-network endpoint.
