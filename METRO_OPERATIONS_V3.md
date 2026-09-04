# Metro operating model v3

Implemented on 2026-09-05 in the shared Supabase-backed scenario runtime.

## Implemented behavior

- Passengers select an origin and destination before entering a platform queue. Queues are separated by line and direction, and only compatible downstream passengers board.
- Walking, interchange transfers, exits, platform density, platform limits, missed boarding opportunities, and conservation are exposed by station.
- Demand uses stored 15-minute profiles with adjustable station/day overrides. It is generated model input, never labelled as measured footfall and has no forced minimum.
- Boarding respects 965-passenger train capacity, modeled door flow, setup time, crowd-sensitive dwell, and platform capacity.
- The rule agent creates reviewable service changes. Commands require approval, pilot acknowledgement, and Apply before they change the run.
- One generated physical fleet of 57 vehicles is assigned across the GTFS service. The source's 327 same-block overlaps are retained as quality evidence; 477 source trips are retimed in the generated assignment to preserve vehicle continuity.
- Motion follows committed acceleration, braking, speed, dwell, occupancy, rainfall, station access, power state, headway, section occupancy, and operator holds.
- Turnbacks have modeled bay capacity, entry, cab-change and return phases, timers, pilot readiness, and release interlocks. Bay geometry and crew durations remain explicit simulation assumptions.
- `/metro-pilot` provides train claim, acknowledgement, cab readiness and Apply controls.
- Calendar exceptions are supported when present. Whole-world checkpoints, new service days, branches, and replay are database-backed and non-destructive.
- Agent requests are consolidated by executable action. Each request names affected stations, direction, queue, platform waiting time, and shared causal events.

## Validation

- 9 focused operating-model tests passed: conservation, direction-specific boarding, door throughput, capacity, finite-fleet continuity, approval/acknowledgement/Apply, pilot turnback release, power backup/recovery, calendar exceptions, and section uniqueness.
- 49 existing backend regression tests passed.
- The production frontend build passed TypeScript and static-page generation for all 9 routes.
- Live checks showed zero passenger-accounting error, 57 physical trains, one consolidated Metro request, working service-day listing, and Ameerpet split into platform, walking/concourse and exiting populations.

## Precision boundary

GTFS supplies schedules and geometry, not passenger measurements, surveyed platform areas, live train positions, crew rosters, signal interlocking, or station-specific footfall. Those values are stored, adjustable model assumptions. They must be calibrated with operator data before operational use. Published rolling-stock capacity, speed and fleet references are documented in the model configuration.
