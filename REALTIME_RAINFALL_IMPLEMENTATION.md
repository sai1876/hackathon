# Realtime load and polygon rainfall — delivered 2026-09-03

Open `/electric-command`. Existing synthetic assets, road geometry, manual faults and repair jobs remain available.

## Controls

1. Select a transformer, feeder or substation. Use its demand slider or presets (0–400% of baseline). Releasing the slider sends a backend command; no operator-name form is required for simulation controls.
2. Press **Run simulation**. Use 1×, 5× or 10× speed, or pause. A backend worker advances the saved world independently of an open browser.
3. Choose **Draw rainfall polygon**, click at least three corners on the map, choose intensity and apply. Each area has intensity, stop-rain and remove-area controls.

The UI polls backend state once per second. Automatic ticks do not advance the operator-command version, so ordinary clock progress cannot invalidate every slider command. SQLite transactions and a shared tick timestamp prevent duplicate advances. A service interruption longer than 15 seconds pauses the clock rather than replaying unattended simulation time; press Run to resume.

## Linked behavior

- Demand multipliers on ancestors and descendants combine. Leaf demand rolls up to its feeder, power transformer and substation. Supply accounting excludes disconnected loads.
- Generated operating limits are 135% of baseline demand, expressed in kW. They are scenario limits, not actual kVA nameplate ratings.
- Ten continuous simulated seconds above the modeled limit trips protection. Downstream protection is considered first, then upstream load is rechecked. A trip disconnects descendants and records a causal event.
- Reduce demand below the selected asset's modeled limit before resetting protection. A trip is distinct from a manually injected equipment fault, which retains the crew/verification workflow.
- A rain polygon affects synthetic local loads inside it. Modeled electricity uplift is `min(35%, intensity × 0.2% + water_proxy_mm × 1%)`.
- Surface-water accumulation uses `intensity − 8 mm/hour` drainage, clamped at zero. This is an accumulated-water proxy, not flood depth or a hydraulic model. Stopping rain allows drainage; removing an area immediately removes its effects.
- Roads intersecting a polygon receive a synthetic delay multiplier `1 + min(1.5, intensity/100 + water_proxy_mm/10)`. The multiplier is rounded to tenths for routing refreshes. Existing infinite-cost closures remain closed. Overlapping road and electrical effects use the strongest area.
- Changes to those rain delay factors asynchronously re-evaluate active ambulance corridors. A changed route uses the existing reapproval behavior. Slow graph loading runs separately from the electrical clock. The traffic page surfaces active synthetic rainfall and calls the ETA a modeled estimate.
- Synthetic signal queues include loss-of-power and local-rain contributions. These signal queue counts are not calibrated measured road queues and do not independently change routing costs; the polygon rain multiplier is the road-routing connection in this increment.
- Each polygon shows a metro-demand index: 100 baseline, increasing with intensity and accumulated water, capped at 180. This is a scenario indicator of road-to-metro demand shift. There is no actual metro station catchment, train movement, passenger inventory or capacity model yet.

## Provenance and limitations

All weather, asset ratings, load factors, protection timing, queues and metro demand are synthetic. The supplied OpenStreetMap dataset constrains asset placement and routes. No Google, Gemini or Groq API calls are needed for this simulation; those integrations remain unconfigured. There is no live electrical telemetry, live weather feed, calibrated grid solver, verified flood model, authenticated staff role enforcement or real infrastructure control.

Polygon validation rejects too few points, self-intersections, out-of-study coordinates, excessively small/large areas and more than ten active areas. Asset membership is based on point inclusion; road delay uses polygon/road intersection. Polygon boundaries do not establish real feeder service territories.

## Verification

- 43 backend tests passed, including sustained overload, load propagation, upstream protection selectivity, reset constraints, pause/speed/interruption handling, polygon locality, drainage, road delay and preservation of road closures.
- Existing browser repair workflow passed with fault injection moved into the Advanced section.
- New browser scenario passed: raise demand → automatic trip → lower demand → reset → draw polygon → observe electrical/road/metro effects → run accumulation → stop rain. It uses a disposable backend and does not alter the operator's saved world.
- Production build and lint passed.

Key implementation: `backend/electric_engine.py`, `backend/weather_effects.py`, routing/operations hooks, and frontend `LoadControls.tsx`, `RainControls.tsx`, `ElectricWorkspace.tsx`.
