# AegisGrid emergency workflow update — 4 September 2026

This update implements the core ambulance request, Traffic Command review, manual controller command and mid-route blockage workflow. It does not complete every earlier city-wide digital-twin request.

## Available now

- `/traffic`: register a vehicle, receive a red pending-request notification, review the current route and junction list, approve or reject with a reason, claim urgent helpline requests, record a response, inspect controllers and Apply manual commands. Active corridors cannot be hidden here.
- `/ambulance`: select a registered vehicle, enter assigned urgency and situation, choose a destination and map endpoints, and request a trip. The simulated vehicle can navigate under ordinary signal rules while approval is pending or rejected. Destination changes require a fresh route and review. Cancellation requests carry a reason.
- `/command`: expand **Emergency corridors & scenario controls** to stop/resume a simulated vehicle, lose/restore GPS, fail/restore a selected controller, or inject/clear a road blockage. These actions use the existing central simulation clock. Electrical portals get a corridor viewer, not ambulance request controls.
- A critical request reaching its 60-second review deadline can prepare only its next junction. Further priority is held after passage and an urgent request is raised. Officers can claim responsibility and record their response.
- Manual Apply records a request separately from controller acknowledgement and verified priority. Pedestrian clearance, amber and all-red precede priority green. Released priority also passes through amber/all-red before recovery. Failed controllers stop retrying after the bounded attempt sequence until explicitly restored.
- Route changes, stops, passage and cancellation invalidate obsolete commands. Ended trips cannot be restarted by a late routing result.
- Blockages ahead invalidate approval, hold the simulated vehicle, expire affected commands and request a replacement from its current location. Google routes conflicting with local closures are not used operationally; the existing OSM graph supplies the fallback. Both route commitment and approval recheck closures. A blockage behind the remaining journey does not invalidate it.
- The map preserves ambulance markers between responses and interpolates between committed positions along route geometry. It does not animate speculative travel beyond committed movement.
- The selected route fits into the map. Routes without a matching imported signal controller explicitly report that signal priority is unavailable.

## What is real and what is modeled

Real integrations: Supabase persistence, operator actions and audit events, Google route responses and map, imported OSM topology, and the existing GTFS/shared-clock systems. Existing Google weather and API budget integrations are preserved.

Modeled data: ambulance GPS, acceleration/braking, turn slowdown, operating speed, queues, traffic arrivals, controller acknowledgements and phases, and ETA/delay calculations. These values evolve in the backend and are identified as simulation; they are not measured ambulance or road telemetry. Estimated extra delay compares simulated queues with and without priority. It is not a guarantee of a two-minute city-wide limit.

The generated Supabase run's `configuration.runtime.emergency` is the live authority for fleet, trips, controllers, commands, urgent requests and injected closures. Existing compare-and-set versioning and the committed event outbox are used. No new database migration was needed. Seed tables remain starting conditions, not fabricated live readings.

## Verification performed

- Production Next.js build and TypeScript validation passed.
- 37 unittest executions passed across emergency workflow, shared scenario and metro suites. The emergency safety subclass also executes inherited baseline tests. Covered pending/rejected travel, acceleration, red/queue stopping, closure ahead versus behind, commit-time closure checks, one-junction timeout priority, stale manual commands, offline failures, clearance/recovery, arrival and late routing after cancellation.
- Browser registration of `AMB-VALIDATION` was confirmed in the shared database.
- A Google-routed validation trip moved while awaiting approval. The browser approval was committed with actor, reason and plan version. That trip later completed.
- A second Google route had three matched signal controllers. Injecting a temporary blockage changed it from APPROVED to PENDING / REPLANNING and held movement.
- The worker produced an OSM closure-aware replacement with 13 matched controllers and a new review version. This route and its request survived backend restart.
- A manual command was offered, then Apply returned APPLIED / SENT with verified priority false. Subsequent reads observed pedestrian clearance, amber, all-red and finally verified green.
- The second validation trip was cancelled, its temporary blockage cleared, the controller returned to automatic and its urgent request resolved with a recorded response. Audit history and the clearly named validation vehicle remain.
- The final Traffic Command browser check showed the first trip completed, the second cancelled, and no pending urgent validation request.

## Main changes

- `backend/emergency_model.py`: state transitions, controller behavior, movement, queue/delay model and closure checks.
- `backend/emergency_api.py`: validated workflow endpoints, provider selection, shared commits and bounded background rerouting.
- `backend/scenario_runtime.py`: emergency advancement on the shared clock and closure publication.
- `backend/command_data.py`: emergency controller state projected onto the existing signal map.
- `backend/main.py`: emergency routes and worker lifecycle.
- `web/src/components/emergency/EmergencyWorkspace.tsx` and its stylesheet: role-specific request, review, map, urgent and manual-command interface.
- Traffic, ambulance and central-command entrypoints connect to this workspace. Existing backend APIs and the older incident workspace were retained.

## Remaining gaps

1. Signal positions/approaches are not a complete surveyed junction inventory. Matching uses proximity to route geometry. The four-approach controller model does not represent every real junction, turning movement, free-left lane or pedestrian crossing.
2. Driving uses modeled speed limits/route averages and aggregate queues. It is not lane-level vehicle simulation. A blockage calculation conservatively freezes the vehicle; realistic braking before the closure, detailed convoy coordination and wrong-turn recovery need further work.
3. The first cold OSM alternative calculation can be slow. Routing retries now back off, but operational routing latency still needs optimization. A valid fallback can be substantially longer than the Google route.
4. Dedicated dispatch/hospital capacity reservation, photo/voice intake, clinical evidence processing, verified physical GPS/controller links, production role authentication, and replay/report interfaces are not provided by this update. A helpline request and response are auditable, but software cannot guarantee a human response.
5. Full route-preview delay forecasting before approval, road-class-specific speed calibration and a validated network-wide delay objective need further work. Current calculations are explicitly estimates.
6. Google coordinate expiry is recorded on routes, but automated expiry cleanup across retained snapshots/history still needs implementation before long-term operation.
7. The legacy incident/corridor workspace remains available in a collapsed section. Its earlier process-local workflow has not been migrated into this new persisted trip model. Use the new Traffic/Ambulance workflow for these requests.
8. The new workflow map is a dedicated Google map. Cross-portal corridor viewing is available in the emergency panel; a single merged base-map experience and the broader metro/electric visual redesign remain separate work.

## Start using it

Enter an operator name in Traffic Command and register a vehicle. In Ambulance Operations, enter the requester name, choose that vehicle, connect the map, select start and destination, and request the trip. Return to Traffic Command to review it. Central scenario injections are in the Command Center emergency panel. All movement follows the shared play/pause/speed controls.
