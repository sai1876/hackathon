# AegisGrid functional audit — 4 September 2026

## Conclusion

The current application is a partially integrated simulation prototype. Real road and metro source data, persisted generated inputs, several working scenario transitions, and emergency approval controls exist. It is not yet the realistic, citywide, cross-department operating simulation requested.

Adding more rows or forcing station counts above 200 would not fix the main defects. The passenger, road, electrical, and operational models must be connected and calibrated first.

This audit traces the active frontend routes, backend entry points, state engines, generation/import scripts, provider boundaries, and the approved workflow documents. It includes browser inspection of Command, Metro, Traffic, and Field Operations, plus live API/database reads. It is not a claim that every historical file or every possible scenario has been exhaustively tested.

## Evidence captured from the running system

| Check | Observed result |
|---|---|
| Ameerpet at shared clock 13:07, service date 2026-09-03 | 12 waiting, 8,806 cumulative entries, 8,794 boarded; a 2× station-demand input was active |
| Subsequent Metro browser observation | Ameerpet fell to 1 waiting while that input was active |
| Direct read of Ameerpet's database weekday profile | 16,528 entries/day; only 69 entries in the 13:00–13:15 slot; provenance `SIMULATED_HISTORICALLY_ANCHORED` |
| Direct read of weekend profile | 11,292 entries/day; 229 in the same quarter-hour slot |
| Command road query near Ameerpet | 900 geometry features, all `traffic_status=UNKNOWN`; no truncation |
| Metro decision endpoint | `MONITORING`, `pending_decisions=[]`, `schedule_changes_enabled=false` |
| Shared runtime asset counts | 57 metro stations, 70 train blocks, 112 signals, 224 signal groups, 60 substations, 120 power transformers, 240 feeders, 4,800 distribution transformers |
| Shared seed inventory | 7,283 assets and 163 profiles; includes 169 infrastructure dependencies, 75 cross-domain rules, 57 service-resource records, and 3 agent configurations |
| Signal endpoint | 112 mapped nodes; 60 named references still awaiting verified coordinates |
| Imported active-service timetable | 327 overlapping consecutive trip pairs sharing a block; one live snapshot showed `WK_31801` twice simultaneously |
| Traffic browser | Emergency workspace; map requires “Connect operational map”; older incident/corridor workspace is a separate collapsed section |
| Field Operations browser | Generic command dashboard and equipment finder; no crew job acceptance, en-route, repair, or completion controls |

Counts are observations at the time of the audit, not permanent UI targets. The simulation continued while inspected. The earlier Ameerpet 2× input subsequently reached its configured expiry; it was not removed by this audit.

## Why Ameerpet looks empty

The stored midday profile produces about 4.6 new entries per minute, or 9.2/minute with the active 2× input. There is one queue for the whole station. Each departing Red or Blue train, in either direction, can board everyone in that queue up to its available capacity. Destinations are allocated **after** boarding and only among that particular train's remaining stations.

Consequently, people who should wait for a different line or direction are taken away by the next train. Interchange passengers are not transferred into a second platform queue. Walking, concourse occupancy, boarding throughput, and interchange dwell are missing. The count represents this simplified boarding queue, not everybody present at Ameerpet.

Evidence: [passenger engine](D:/aegisgrid/backend/scenario_runtime.py:228), [profile generation](D:/aegisgrid/backend/scripts/enrich_metro_dependencies.py:19), [station panel](D:/aegisgrid/web/src/components/metro/MetroOperations.tsx:10).

The proper replacement should model station → line → direction/platform queues, choose destinations before boarding, include transfers/walking time, limit boarding by train space and door/dwell throughput, and validate time-of-day occupancy against plausible or supplied observations. “At least 200 at every moment” should not be used as an artificial floor.

## Missing and partial requirements

### Metro passengers and operations

1. **Broken realism: one station queue serves incompatible directions and lines.** Passenger destinations must determine which train can board them. This is the main Ameerpet defect. [Engine](D:/aegisgrid/backend/scenario_runtime.py:228)
2. **Missing interchange circulation and occupancy.** No transfer queues, concourse/walking occupancy, platform density, or station capacity percentage. `occupancy_percent` remains null. [Station endpoint](D:/aegisgrid/backend/metro_engine.py:98)
3. **Uncalibrated station demand.** A historical system-wide ridership anchor is distributed through assumed station weights and smooth weekday/weekend curves. It is not station-level footfall evidence. The Ameerpet midday trough needs calibration; station-specific workday, event, access, and transfer patterns are absent. [Generator](D:/aegisgrid/backend/scripts/enrich_metro_dependencies.py:8)
4. **Missing physical boarding constraints.** Whole queues can board at a scheduled departure; no door throughput, platform crowding limit, train crowding-dependent dwell, or missed-boarding behavior. Generated train capacity is uniformly assumed to be 1,000. [Boarding](D:/aegisgrid/backend/scenario_runtime.py:252), [train seed](D:/aegisgrid/backend/scripts/extend_shared_simulation.py:47)
5. **Metro decision agent is not executable.** The UI always says there are no executable recommendations. No demand-triggered extra service, hold, short-turn, headway adjustment, approval/rejection, or command execution changes the timetable. [Endpoint](D:/aegisgrid/backend/metro_engine.py:116), [UI](D:/aegisgrid/web/src/components/metro/MetroOperations.tsx:10)
6. **Fleet scheduling is not validated.** Overlapping trips can show the same scheduled vehicle in two places. Import checks timing within a trip, but not conflicts across trips sharing a block. These assignments must be reviewed before fleet-aware scheduling is credible. [Import](D:/aegisgrid/backend/scripts/import_metro_gtfs.py:23), [playback](D:/aegisgrid/backend/metro_engine.py:61)
7. **Train motion ignores operational consequences.** Positions and dwell follow the imported timetable. Crowding, rainfall, power failure, blocked station access, and dispatch decisions do not hold or delay trains. Geographic markers update with snapshots; the schematic interpolates time but does not model acceleration, braking, or controlled reversing. [Position calculation](D:/aegisgrid/backend/metro_engine.py:35), [geographic layer](D:/aegisgrid/web/src/components/metro/MetroMap.tsx:30)
8. **Turnback is only partially operational.** This turn adds verified same-block layover timers in both schematic views and a countdown panel. It does not create surveyed sidings, reversing trajectories, bay occupancy conflicts, driver cab-change tasks, or operational release approval. See the implementation note below. [Turnback derivation](D:/aegisgrid/backend/metro_turnbacks.py:9)
9. **No Metro Pilot portal or command acknowledgement.** There is no separate pilot page receiving and applying departure/hold instructions. [Available routes](D:/aegisgrid/web/src/app/metro-command/page.tsx)
10. **Service-day controls are incomplete.** Import/playback use regular calendar rows, without calendar exception handling. The shared run stops at midnight and has no operator workflow for a new service day, branch/replay, or rewind. [Calendar](D:/aegisgrid/backend/metro_engine.py:27), [clock](D:/aegisgrid/backend/scenario_runtime.py:68)

### Traffic, roads, signals, and map

11. **No continuously evolving city road-traffic state on the command map.** The viewport endpoint loads geometry and applies scenario penalties. It does not read a changing vehicle stock, density, speed, flow, or queue per road. [Road endpoint](D:/aegisgrid/backend/command_data.py:45)
12. **No normal/free-flow traffic color category.** Current map statuses are UNKNOWN, SLOW, CONGESTED, and BLOCKED, based on scenario factors. Without an applicable input, roads remain UNKNOWN/grey. The 900-road check confirms this is a data-path gap. [Status logic](D:/aegisgrid/backend/command_data.py:114), [map styling](D:/aegisgrid/web/src/components/command/MainCommand.tsx:57)
13. **Zoom behavior exists, but does not create traffic observations.** Road queries use the visible bounding box at zoom 15+, as previously requested. Hiding road colors while zoomed out is intentional. What is missing is a meaningful traffic-state source and explanation of which layer is displayed. [Viewport handling](D:/aegisgrid/web/src/components/command/MainCommand.tsx:59)
14. **Google traffic display is isolated.** `TrafficLayer` is instantiated in Google Operations. The primary Traffic workspace declares its type but does not attach the layer; Command uses MapLibre/OSM. A unified, explicitly labelled live-versus-simulation traffic viewing workflow is missing. [Google layer](D:/aegisgrid/web/src/components/command/GoogleOperations.tsx:27), [Traffic map loader](D:/aegisgrid/web/src/components/emergency/EmergencyWorkspace.tsx:24)
15. **Signal queues are not linked to the road network.** Emergency controllers use generated fixed arrival rates and local four-approach queues. No upstream/downstream vehicle conservation, spillback, calibrated turning flows, or network congestion propagation connects these queues to road colors. [Controller model](D:/aegisgrid/backend/emergency_model.py:65)
16. **Signal coverage and movement geometry remain incomplete.** Sixty named junction references lack verified coordinates. OSM signal nodes can represent approaches rather than whole junctions. Nearby signals are associated with routes by distance and approximate compass approach; full lane, turn, pedestrian, and conflict-group geometry is missing. [Signal inventory](D:/aegisgrid/backend/command_data.py:78), [corridor plan](D:/aegisgrid/backend/emergency_model.py:46)
17. **General traffic monitoring is secondary to emergency dispatch.** The main `/traffic` screen lacks citywide speed/queue/throughput trends and a unified incident/action worklist. Its older incident/routing workspace remains separately collapsed, reading different state. [Traffic entry](D:/aegisgrid/web/src/components/traffic/TrafficDashboard.tsx)
18. **No distinct Traffic Police field workflow.** Manual Apply exists inside Traffic Command, but there is no separate police assignment/acknowledgement/arrival/execution portal as specified. [Current role UI](D:/aegisgrid/web/src/components/emergency/EmergencyWorkspace.tsx:12)

### Electricity and field response

19. **Electrical geography is generated, not verified utility topology.** The 60/240/4,800 model inventory is not proof of citywide coverage or a geolocated version of the utility-wide counts previously provided. Coordinates, capacities, and parent relationships need validation or explicit scenario assumptions. [Network endpoint](D:/aegisgrid/backend/scenario_runtime.py:342)
20. **Map shows asset identity/capacity, not changing asset condition.** The current equipment endpoint omits per-asset load, voltage, temperature, energized status, fault, and overload history. Icons are colored by equipment type. The aggregate load can change without the selected transformer showing why. [Network properties](D:/aegisgrid/backend/scenario_runtime.py:348), [inspector](D:/aegisgrid/web/src/components/command/ElectricLayer.tsx:36)
21. **No asset-targeted electrical operating controls in the current portal.** The shared power-demand input is an area multiplier. The equipment inspector cannot adjust a selected feeder/transformer's demand, isolate a fault, transfer supply, or restore equipment. Legacy electrical controls exist elsewhere but are not integrated with this shared view. [Area controls](D:/aegisgrid/backend/scenario_runtime.py:163), [legacy actions](D:/aegisgrid/backend/electric_engine.py:227)
22. **No shared electrical protection or power-flow model.** The shared summary sums modeled distribution-transformer demand. It does not propagate loading through feeder/substation ratings, calculate voltage/losses, trip protection after sustained overload, or simulate restoration consequences. [Summary](D:/aegisgrid/backend/scenario_runtime.py:273)
23. **Stored power dependencies are unused by the shared runtime.** The seed contains 169 supply-dependency records, but startup does not load them. Therefore a generated feeder failure does not drive signal backup exhaustion, station power loss, or metro service suspension through those records. [Dependency generation](D:/aegisgrid/backend/scripts/enrich_metro_dependencies.py:49), [runtime load list](D:/aegisgrid/backend/scenario_runtime.py:311)
24. **Lineman/field work is missing from the active page.** `/lineman` renders a generic department variant of MainCommand. No shared work-order lifecycle, crew assignment, en-route tracking, site assessment, repair report, or supervisor verification is exposed. [Page](D:/aegisgrid/web/src/app/lineman/page.tsx), [department component](D:/aegisgrid/web/src/components/command/MainCommand.tsx:85)

### Rainfall and shared consequences

25. **Live Google weather is displayed, not consumed as a simulation event.** There is no reviewed observation-to-model ingestion path. The live observation and simulated service date/time can differ; copying weather into a different simulation time without a policy would also be incorrect. [Weather boundary](D:/aegisgrid/backend/google_weather.py:51), [scenario effects](D:/aegisgrid/backend/scenario_runtime.py:102)
26. **Flooding is a uniform polygon bucket model.** Rainfall minus average drainage changes one depth for an entire drawn polygon. Terrain, runoff catchments, infiltration, underpasses, spatially varying depth, drainage capacities, and duration-dependent road accessibility are not modeled. Rain does have delayed effects now; it is not an instant flood animation. [Advance](D:/aegisgrid/backend/scenario_runtime.py:75)
27. **Traffic-to-metro modal shift does not conserve travelers.** Nearby stations get a bounded multiplier from the same polygon effect. No road travelers are removed and reassigned to accessible stations; closed access, walking catchments, interchange load, and available metro capacity do not constrain the shift. Stored cross-domain rules describe more than the engine executes. [Effects](D:/aegisgrid/backend/scenario_runtime.py:102), [station effects](D:/aegisgrid/backend/scenario_runtime.py:215)
28. **Recommendation and response repertoire is very narrow.** The shared engine proposes drainage after 30 mm and approval doubles modeled drainage/adds pumping demand. No pump/crew dispatch journey, availability constraint, measured work progress, or completion verification precedes that effect. Comparable metro/power/traffic agent workflows are missing. [Recommendation creation](D:/aegisgrid/backend/scenario_runtime.py:85), [approval](D:/aegisgrid/backend/scenario_runtime.py:133)
29. **Large time jumps need causal validation.** Rain/emergency state advances in steps, then passenger integration runs once using station effects from the final state. A jump across input start/expiry can apply the final demand factor to the wrong part of the elapsed interval. [Advance and passenger integration](D:/aegisgrid/backend/scenario_runtime.py:68)

### Ambulance and approvals

30. **Intake and hospital selection remain basic.** A registered vehicle, text priority, free-text destination, and map points are supported. Structured dispatch triage, hospital capability/capacity/availability, driver-choice fallback to dispatch, and photo/voice intake are not connected. [Trip form](D:/aegisgrid/web/src/components/emergency/EmergencyWorkspace.tsx:44)
31. **Holding calculations are estimates, not precise city traffic optimization.** Local queues use assumed arrivals/discharge; ETA uses a 40 km/h route average and movement a 50 km/h ceiling with turn/braking reductions. Network-wide delay, route-specific speed limits, downstream queues, and conflicting multiple corridors are not fully optimized. Clearance calculations are produced when priority is sent, not as complete per-junction calculations at initial review readiness. [Priority calculation](D:/aegisgrid/backend/emergency_model.py:91), [movement and ETA](D:/aegisgrid/backend/emergency_model.py:247), [delay comparison](D:/aegisgrid/backend/emergency_model.py:339)
32. **Helpline can record responsibility, but cannot ensure a human response.** Claim/respond/resolve controls exist. Enforced acknowledgement escalation, officer availability/shift coverage, and response deadlines are missing. A button alone does not fulfill “mandatorily responds.” [Urgent workflow](D:/aegisgrid/backend/emergency_model.py:30)
33. **Closure response exists, but realism is incomplete.** The newer workflow invalidates future commands and triggers replanning when the remaining route conflicts. It immediately sets speed to zero; there is no modeled pull-over/safe stopping place. Conflict checks use proximity/polygon geometry, not a complete lane/access model. Wrong-turn recovery is absent. The old reported “route through blockage” is not assumed still broken: closure-aware code is present, but the full current multi-blockage workflow was not replayed during this audit. [Detection](D:/aegisgrid/backend/emergency_model.py:298), [road closure matching](D:/aegisgrid/backend/route_engine.py:98)
34. **The all-in-one central map does not contain the emergency corridor layer.** MainCommand has a summary and a separate emergency workspace dialog, while its primary map mounts scenario roads, signals, metro, and electric layers. Cross-department map overlays and selection state are not truly unified. [Main map composition](D:/aegisgrid/web/src/components/command/MainCommand.tsx:74)

### Architecture, provenance, and usability

35. **Multiple state authorities still coexist.** The newer runtime is a versioned Supabase run. Legacy corridors/incidents/exercises are process-local; the old electrical engine uses SQLite and its own clock. Both legacy and new endpoints remain mounted. The local restart wrapper preserves legacy state manually, which is not a durable single-source architecture. [Legacy snapshot](D:/aegisgrid/backend/operations_engine.py:205), [electrical world](D:/aegisgrid/backend/electric_engine.py:358), [mounts](D:/aegisgrid/backend/main.py:187)
36. **Data-readiness messaging contradicts the active simulation.** `/command/snapshot` hardcodes `scenario_ready=false` and an old “No generated fallback” explanation while `/command/scenario` is ready with generated database assets. Seed inventories and live state must be clearly distinguished and readiness assessed per capability. [Snapshot](D:/aegisgrid/backend/command_data.py:39)
37. **No functioning Groq/Gemini decision integration found in active source paths.** Agent seed configurations and old demo labels exist, but there is no active model request/validated recommendation pipeline in the inspected backend. Google Weather/Routes/Places/etc. integration is separate and does exist. [Agent seed](D:/aegisgrid/backend/scripts/extend_shared_simulation.py:55), [Google endpoints](D:/aegisgrid/backend/google_operations.py:37)
38. **Operator identity and authority are not enforced.** Roles are frontend variants; an entered actor name is not authentication or server-side department authorization. This prevents reliable assignment ownership and authoritative operator audit trails. [Action input](D:/aegisgrid/backend/emergency_api.py:23), [UI role notice](D:/aegisgrid/web/src/components/emergency/EmergencyWorkspace.tsx:40)
39. **Operational scale and recovery need verification.** The full runtime document is repeatedly read/rewritten every two seconds. There is no user-facing run creation/branch/replay workflow, and fixed run/input/trip limits exist. Database outage recovery and large-scale traffic/passenger workloads need measured tests before expanding generated data substantially. This is an engineering risk, not a benchmarked performance failure. [Commit](D:/aegisgrid/backend/scenario_runtime.py:177)
40. **Provider budgets and UI states are incomplete.** Server calls use an atomic usage guard; frontend Dynamic Map loads are not in that guard. Health reports static “healthy.” The map defaults have improved, but department layouts are inconsistent, narrow views require extensive scrolling, modal workflows split the operating picture, some labels expose internal state names, and the Field page still instructs operators to choose events they cannot create. [Budget SKUs](D:/aegisgrid/backend/core/api_usage_guard.py:5), [health](D:/aegisgrid/backend/main.py:54), [main UI](D:/aegisgrid/web/src/components/command/MainCommand.tsx:85)

## Working features that should be preserved

- OSM-derived road graph/geometry and imported GTFS routes, stops, and timetable are real source records. They are not live road speeds, train GPS, or passenger observations. The 374,988 count describes directed road records; the older 705 metro records are not 705 independent stations.
- The newer shared simulation persists its clock, scenario inputs, passenger counters, emergency state, and events. Version checks and an event outbox are present.
- Station-targeted metro demand no longer requires drawing a polygon. Rain inputs can be ended or removed; removal preserves historical events rather than rewinding the run.
- Rain accumulation, drainage, modeled road delay/closure, pumping demand, and a bounded station-demand response execute in the backend.
- Separate ambulance requests and traffic approve/reject-with-reason, a pending-request notification, manual controller Apply, urgent claim/response, and closure-triggered replan are implemented at prototype level.
- White geographic basemaps, uniform clickable 🚦 symbols, equipment-type icons, equipment search, repeated Locate, selected supply links, PDF/schematic metro toggle, and station dwell highlighting are present.
- Google Weather data was visibly returned in the browser. Server API accounting is persistent and fail-closed. Other provider endpoints were inspected, not billed repeatedly just to conduct this audit.

## Turnback timer added during this audit

The user requested a timer while the audit was underway. A focused implementation now derives terminal layovers from consecutive trips of the **same GTFS block**, on the same line and at the same parent station. It excludes overlapping/unlinked services and does not invent a wait for a train with no known next service.

Both PDF and schematic views show the active block at its schematic bay with a countdown. A panel above the map shows station, block, remaining/total layover, next departure time, and destination. The timer uses the shared simulation clock, follows speed/pause, and ends when the outgoing trip reaches its initial platform interval; platform boarding dwell remains separate.

Browser verification showed Miyapur `WK_10201` counting down from its 3:10 layover (1:21, then 1:02 observed), and MGBS `WK_20101` from its 2:47 layover (1:03, then 0:44 observed). These are timetable-derived layovers, not verified real siding occupancy. The 327 timetable block conflicts are now visible as a quality warning; their underlying assignments were not silently rewritten.

Changed files: [derivation](D:/aegisgrid/backend/metro_turnbacks.py), [endpoint](D:/aegisgrid/backend/metro_engine.py), [map types](D:/aegisgrid/web/src/components/metro/MetroMap.tsx), [schematic/timer UI](D:/aegisgrid/web/src/components/metro/MetroSchematic.tsx), [styles](D:/aegisgrid/web/src/components/metro/metro.css), [tests](D:/aegisgrid/backend/test_metro_turnbacks.py).

Validation this turn: 13 metro timetable/turnback/station-target regression tests passed; frontend production build and TypeScript passed; local servers restarted with captured legacy operational records and the existing shared database run preserved; running API and browser timer verified. No demand profiles, timetable source records, or simulation scenario inputs were rewritten by this audit. No full production/security certification or all-scenario end-to-end test is claimed.

## Recommended implementation order

1. Replace station-only passenger queues with platform/direction/OD/transfer flows; resolve timetable block conflicts; add crowding and waiting-time inspection. Validate morning peak, midday, evening peak, and disruptions without forced minimum counts.
2. Build one conserved road-flow model keyed to imported road IDs and the shared clock. Feed map colors, route costs, signal queues, and spillback from that state, with per-road inspection and history.
3. Consume stored infrastructure dependencies. Propagate overload/outage/backup consequences and connect them to signal/station service availability; expose live per-asset condition and targeted load controls.
4. Add executable metro recommendations and department task lifecycles, then police/pilot/lineman portals with acknowledgement and verified completion.
5. Consolidate legacy authorities and the central map; add replay/run management, permission enforcement, provenance/readiness consistency, and cross-domain acceptance scenarios.

Acceptance should be behavioral: a station surge leaves passengers on the correct platforms; crowding changes a proposed service plan; an approved service actually runs; feeder loss affects its dependent signals/stations; road closures redistribute conserved vehicles and reroute the ambulance; clearing the cause produces a traceable recovery across every portal.
