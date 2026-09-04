# AegisGrid portal and shared simulation plan

Status: agreed scope recorded for implementation. The application currently has `/traffic` and `/ambulance`; the other portals below are planned, not yet built.

## Portal structure

| Portal | Proposed route | Main responsibility | Actions in the simulator |
| --- | --- | --- | --- |
| Traffic | `/traffic` | Monitor road conditions, closures, queues, diversions and corridor status | Inspect roads and incident evidence; switch live-reference/synthetic views |
| Ambulance | `/ambulance` | Request a corridor and follow the assigned journey | Submit request; report location/status; receive approval or revised route |
| Electric Command | `/electric-command` | Monitor modeled feeders, transformers, outages and dependent assets | Review faults; assign crews; approve modeled restoration; track affected signals/stations |
| Lineman | `/lineman` | Field response to assigned electrical work | Accept task; report en route/on site; submit assessment; report repair completion |
| Traffic Command | `/traffic-command` | Decide traffic interventions and coordinate emergency priority | Approve/reject corridors; assign police; approve modeled signal plans/diversions; restore plans |
| Traffic Police | `/traffic-police` | Field response to traffic incidents | Accept deployment; report arrival; confirm diversion setup or clearance; request further support |
| Metro Command Center | `/metro-command` | Monitor train positions, headways, station demand and service disruptions | Review service changes; hold/release services in simulation; issue instructions to pilots |
| Metro Pilot | `/metro-pilot` | Operate an assigned simulated train under command instructions | Acknowledge instructions; report readiness, delay or fault; request departure and update trip status |
| AegisGrid Command Center | `/command` | Observe and simulate the entire system on one map | Create scenarios, control the simulation clock, follow causal consequences and coordinate departments |

“Traffic” is interpreted as a monitoring portal; “Traffic Command” is the decision desk; “Traffic Police” is the field portal. Metro Command and Metro Pilot are separate interfaces.

## One shared world

All portals subscribe to the same server-owned world, clock, incidents, assets, requests, decisions and event journal. No portal owns an independent fake dataset or private simulation timer. A command in one portal updates the same records displayed by all affected portals.

Core records:
- Assets with stable IDs, geometry, domain, provenance and dependency links.
- Road traffic state: admitted demand, vehicle stock, queues, speed, occupancy, capacity and signal state.
- Ambulance missions and route versions, preserving the existing approval and blockage rules.
- Electrical asset state and dependent signal/station power availability.
- Crew assignments, acknowledgements, location reports and repair verification.
- Metro trips, train positions, station queues, capacity, service instructions and pilot acknowledgements.
- Incidents and departmental tasks, each linked to its cause and outcome.
- Operator decisions with evidence version, rationale and actor; backend role checks when identity is added.
- Simulation run ID, seed, model configuration, clock and replayable event log.

Asset relationships must be explicit. A power fault affects only signals or stations connected to that modeled feeder, not arbitrary nearby assets. A road closure affects matched physical road segments in both directions unless a future explicitly supported directional restriction is selected. Geography alone is not proof of electrical or metro dependencies.

## AegisGrid all-in-one map

The central map is the primary working surface in `/command`. Selectable layers:
- Google live traffic reference, where configured and available.
- Synthetic road speeds, occupancy, queues and closures on imported OSM geometry.
- Ambulance routes, positions, upcoming modeled priority junctions and request status.
- Signals, traffic police assignments and reported response locations.
- Modeled electrical assets, outages, dependencies and lineman assignments.
- Metro lines, stations, trains and modeled station crowding.
- Selected incident, affected assets and consequence links.

Use distinct styling and labels for REAL_GEOMETRY, PROVIDER_REFERENCE, SYNTHETIC_STATE, OPERATOR_REPORTED and AI_EXPLANATION. A simulated intervention cannot change Google's live traffic layer. Map inspection opens the same evidence and task IDs used in the departmental portals.

Main command-center controls:
- Select a scenario, affected asset/road, severity, start time and duration.
- Start/pause/resume, step and change simulation speed.
- Observe events, pending decisions, departmental assignments and consequences.
- Inspect before/after model metrics and compare a proposed action with doing nothing.
- Reset a selected synthetic run only; never silently delete operator reports or unrelated work.
- View API usage, provider availability and data provenance.

## Example causal scenario

1. Command center injects a SYNTHETIC fault on a modeled feeder.
2. Only its dependent modeled traffic signals lose normal service; Electric Command receives the fault.
3. Signal capacity changes reduce traffic discharge. Conserved vehicle stock produces growing queues.
4. An ambulance requests a corridor through the affected area. NetworkX evaluates restrictions; the model estimates queue-related delay separately from free-flow ETA.
5. Traffic Command reviews alternatives, approves a feasible corridor and assigns Traffic Police to support the affected junction.
6. Electric Command assigns a lineman. The field portal reports task progress; travel and repair delays use the shared clock.
7. If a connected metro station or traction section is affected by the scenario model, Metro Command receives that specific consequence and issues a modeled hold/service instruction. The pilot acknowledges it.
8. Repair completion is reported, verified in the simulator and approved for restoration. Dependent assets recover; queues drain according to capacity rather than instantly disappearing.
9. The command map and all portals show the same restoration events, outstanding work and measured synthetic outcomes.

## Action and task lifecycles

Department task: PROPOSED → APPROVED/REJECTED → ASSIGNED → ACKNOWLEDGED → EN_ROUTE/IN_PROGRESS → COMPLETION_REPORTED → VERIFIED/CLOSED.

Invalid transitions are rejected by the backend. Stale decisions require renewed review. A field completion report is not automatically a verified recovery. Role-specific pages alone do not constitute access control; authorization must be enforced by backend identity and roles before treating this as a multi-user operational system.

Google supports map/reference data. Groq generates explanations from deterministic evidence, with Gemini verification/fallback. AI output must reference existing asset/incident/action IDs and pass validation. AI never directly actuates infrastructure or overrides routing, conflict or approval rules.

## Implementation order

1. Shared world state, durable run/event storage, synthetic input datasets and continuous backend clock.
2. Portal navigation and shared map/data subscriptions, preserving the working traffic/ambulance functionality.
3. Traffic Command and Traffic Police workflows. Move decision controls out of `/traffic` only after `/traffic-command` is working and tested.
4. Electric Command and Lineman, including modeled dependencies and restoration workflow.
5. Metro Command and Pilot, using supplied transit data if available; clearly label generated geometry or timetables otherwise.
6. Unified `/command` scenario workspace and cross-domain consequence visualization.
7. Connect configured Google/Groq/Gemini providers, validate fallbacks and enforce usage budgets.
8. End-to-end tests across portals: event → decision → assignment → response → recovery; verify shared state, blocked-road exclusion, role restrictions, conservation, pause/replay and restart behavior.

## Data and integration boundaries

Available confirmed data: existing OSM/Supabase road geometry, Hyderabad exports, and the Mallampet/Bachupally import. Verified electrical topology, crew rosters, metro telemetry and passenger demand have not been located. Create reproducible, labeled synthetic datasets for missing domains; do not represent generated infrastructure as surveyed or official. New provider integrations await locally configured keys.

No real signal control, power switching, emergency dispatch or train operation is connected. Department actions operate the simulator. Cloud hosting, production authentication and account-wide billing telemetry must be evaluated separately from local demo behavior.

## Electrical dataset and map detail

See [ELECTRIC_NETWORK_PLAN.md](ELECTRIC_NETWORK_PLAN.md) for verified utility-wide counts, synthetic topology generation, map detail by zoom, and causal electrical dependencies.
