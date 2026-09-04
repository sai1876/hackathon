# AegisGrid agreed operating model

Status: approved behavior specification. Implementation must be verified separately.

## Shared authority and portals
- Hyderabad is the focus. One shared database and simulation clock serve Command Center, Traffic Command, Electric Command, Metro Command and Ambulance.
- Main Command owns time controls and scenario injection. Normal city view shows zones, traffic and signals; contextual panels expand on selection or emergency.
- All active approved corridors are mandatory on Traffic Command's central map. Other portals have a visibility toggle. Selection emphasizes one corridor without hiding others.
- Emergency vehicles must be registered by Traffic Command. Emergency tickets may be raised by drivers, hospitals or dispatch.
- Driver chooses a hospital; dispatch selects it when the driver has not. Capacity uses labelled database simulation until an observed feed exists.

## Authorization
- Preserve dispatcher/paramedic-assigned priority; AI may flag concerns for later audit, not silently change it. AI explanations summarize evidence, uncertainty and recommendations.
- Critical emergencies receive priority over conflicting less urgent emergencies.
- A red top-right Traffic Command notification opens ticket review: vehicle, assigned priority, situation, submitted evidence, destination, route ETA, junctions, predicted extra traffic delay and countdown.
- The 60-second review timer starts only when a usable route and junction plan are ready. Under simulated limited autonomy, a critical unacknowledged ticket can request priority at the first upcoming junction only.
- Further activation waits for authorization. Helpline requests go to Traffic Command's Urgent section, where an officer takes responsibility.
- Approve authorizes the whole current route plan, with rolling activation. Reject requires a reason; normal navigation continues and helpline appeal is available.
- Approval keeps the corridor on the normal central map and shows calculations. The officer can continue other work.

## Junction control
- Plan the whole corridor; communicate progressively according to ETA, queue clearance, geometry and safe transition time.
- Simulate acknowledgements and distinguish requested, accepted, executing and verified states. Never show requested green as confirmed green.
- Preserve pedestrian clearance, minimum phase time, amber and all-red. No conflicting greens, including during manual control. Free-left movement only proceeds when nonconflicting.
- Clear queued vehicles before the ambulance proceeds; approval cannot teleport it through a queue.
- Optimize average additional ordinary-traffic delay against a two-minute allowance. If the model cannot satisfy it, hold further priority and create an urgent exception request. Finish active safe transitions.
- On failed acknowledgement: bounded retries, unavailable controller, urgent police task; keep the route unless the road is unusable.
- Manual takeover suspends automatic execution. Recommended commands appear in the officer portal; Apply sends each to the simulated controller. Invalidate commands when position, route, or conditions change.
- After passage, release the junction and restore traffic coordination. Corridor completion waits for junction recovery.

## Ambulance motion
- Start from an operator-selected position, move on actual route geometry under the shared clock, including while authorization is pending.
- Use acceleration, braking, road/turn limits, queues, signals and closures. No single fixed ambulance speed or canned animation.
- Red signals without approved priority stop the prototype vehicle. Normal navigation continues after rejection.
- Automatic arrival at destination. Retain trip, decisions and movement history.
- Driver portal shows navigation, destination, ETA, approval status, next junction, cancellation and help; no signal control.
- Destination change recalculates the route and requires revised corridor approval. Driver cancellation request includes a reason and requires operator confirmation.
- Command Center can inject stops, GPS loss, wrong turns, controller failure and road blockage. Short GPS prediction is labelled and bounded; it cannot prove a junction was cleared.

## Mid-corridor blockage
1. Persist the blockage and identify affected remaining route segments.
2. Invalidate unusable future reservations/commands; active junctions recover safely.
3. Decelerate before the blockage. Never drive through it or teleport to a detour.
4. Recalculate from actual current position to the same destination and validate the alternative against every current closure.
5. Show red notification, old/new routes, ETA change and affected junctions for fresh approval.
6. Move under normal signals on the usable alternative while awaiting authorization; no new emergency priority.
7. If no accessible route exists, stop and raise an Urgent task.
8. A blockage already behind a vehicle does not reroute that vehicle merely because it intersects the completed part of its trip.

## Truthfulness and boundaries
- Google weather/traffic estimates, source geometry, generated infrastructure, modelled queues, predicted ETA and simulated GPS have distinct provenance.
- No fabricated live readings, diagnosis from patient images, guaranteed human acknowledgement, or claim that a browser overrides device mute.
- Current controllers are simulation adapters, not connections to Hyderabad signal hardware. Controller deployment requires a supported interface and authority approval.
- Current lack of authentication must not be described as secure role enforcement.
- Replay and reports use committed events; human decisions are evaluation/training examples, not automatic model fine-tuning.
- Demo mode is a separate non-navigation link with shared-clock speed controls and explicit reset semantics.
