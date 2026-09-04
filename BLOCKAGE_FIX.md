# Physical-road blockage fix — 3 September 2026

## Cause

The original incident matcher set infinite cost on only one directed OSM edge. On a bidirectional street the reverse edge remained drivable. The reported corridor used OSM:3598253469:6528302161:0 while the incident closed OSM:6528302161:3598253469:0, so the route crossed the same physical blocked road.

The upper marker also matched a short side street about 5.1 m from its click; the pictured corridor was about 14.4 m away. A large marker concealed that distinction. Existing incidents were preserved rather than silently relocated.

## Correction

- Close every directed/duplicate representation of the matched physical segment, requiring the same endpoints and equivalent geometry. Distinct parallel roads and crossing streets remain independent.
- Pin a match after its first evaluation so a different routing area cannot relocate the incident to another road.
- Return per-edge route geometry. Clicking the displayed route in event-selection mode carries the exact road edge ID to the backend; explicit selection takes precedence over nearest-road matching.
- Surface both-direction closure scope, match source and click-to-road distance in incident cards.
- Preserve old endpoints and routing costs; endpoint splits still cannot reopen a closed edge.
- Re-evaluate current corridors after the service restart, preserving requests, decisions, events and all three incident records.

## Verified result

The reported request was recalculated in the running service: 1,170.04 m before the fix → 1,689.88 m afterward, with a 147.94-second free-flow estimate. Its route has zero overlap with blocked directed edges. It remains PENDING for traffic review, now at version 4 at verification time.

Validation: 33 backend tests pass, including six new physical-closure regressions. Five browser scenarios passed on the first run; a sixth had an ambiguous error-banner selector (it also selected Next.js's route announcer), which was corrected and passed on rerun. The browser test explicitly clicks the displayed route and verifies that its edge ID reaches the event request. Frontend production build and lint pass.

Changed: backend/route_engine.py, models.py, incident_engine.py, operations_engine.py, test_blockages.py; web/src/types/aegis.ts, components/traffic/TrafficMap.tsx, OperationsWorkspace.tsx, tests/command.spec.ts.

A brief Supabase fetch failure occurred during startup revalidation. A subsequent real route request and corridor re-evaluation succeeded; the stale route was not displayed while unavailable. Base road records were not edited. Runtime storage remains process-local; restoration was performed explicitly for this restart.
