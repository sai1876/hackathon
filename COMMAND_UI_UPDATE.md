# Command Center update — 4 September 2026

## Delivered

- Replaced the map-and-form layout with a compact header, two operational side rails, central map, and horizontal event-control dock. Scenario setup, inventory, billing and full workspaces open on demand.
- Palette: charcoal/navy panels, neutral text, restrained blue controls, amber/red for warning states. Per the latest request, all geographic maps use light backgrounds. Google Operations and emergency maps explicitly request LIGHT; metro PDF and schematic views have white backgrounds and readable labels.
- Uniform 🚦 markers retain click-to-inspect controller information and manual actions.
- Repeated Locate creates a fresh camera request and brings the map into view. Metro demand locates selected stations; weather locates its polygon.
- Electrical equipment now appears on the main command map as well as the electrical department. Substations, power transformers, feeders and distribution transformers have distinct symbols and zoom thresholds. Search/type selection and the supply tree navigate actual stored parent relationships. Selected supply links are dashed; no citywide starburst is drawn.
- Metro demand selects one, several, or all 57 database stations. No polygon is required. The backend validates station IDs, persists the target list, changes arrival rates only at those stations, and leaves boarding/queues under the existing timetable and capacity model. Rainfall still affects stations spatially.
- Saved rain areas have a Remove action distinct from Stop input. Stop input leaves residual water to drain. Remove archives the input, removes its ongoing influence, cancels pending recommendations, and republishes routing effects. Historical passengers/actions are not rewound. Repeated identical requests remain idempotent.
- Successful area application clears the temporary drawing, preventing a draft polygon from remaining after its saved scenario is removed.
- Audit feed timestamps now use the same simulation clock as the header.

## Data provenance

- Real external/source data: Google Weather observations and forecasts; imported OSM road geometry; GTFS station locations, tracks and timetable.
- Generated and persisted: electrical inventory/positions/parent connections, initial demand profiles, passenger demand models and controller timing plans.
- Derived simulation: water depth, traffic slowdown and closure effects, power demand, queues, boarding, train positions and recommendations. Panels state this provenance. No reference-image statistics, AI confidence percentages or fake camera feeds were introduced.
- Both previously saved rain areas were removed through the running application while work was underway. Subsequent backend reads confirmed zero affected transformers from those inputs and retained removal audit events. The user subsequently created an Ameerpet station-demand input; it remains part of the active shared run.

## Verification

- Production build and TypeScript checks passed after the layout, behavior and light-theme changes.
- 16 focused test executions passed across `test_station_targets`, `test_area_removal` and `test_command_effects`. Coverage includes station targeting without polygons, rejected unknown/empty station lists, changed arrivals at only selected stations, removal/idempotency/audit retention, removal of power/road/station effects, and existing rainfall response behavior.
- Browser checked at 1536 × 1024 and the compact in-app viewport. Verified white map, station selection and enabled Apply, a real stored substation → power transformer → feeder → distribution transformer path, selected supply links, and Locate after zooming away.
- GET metro-targets returned 57 database stations. State persisted through local service restarts. No credentials were printed or moved.

## Limits

- Electrical connections are modeled topology, not surveyed cable routes. Co-located equipment is accessed in the supply tree. Map icons do not claim live electrical telemetry.
- Passenger data and train positions are simulated from stored models and GTFS, not live AFC/GPS feeds. This work changes station demand targeting, not timetable rescheduling or a physical control system.
- All electrical links are not shown simultaneously: selected upstream and immediate downstream relationships are shown to avoid the previously rejected starburst display.
- A white OSM basemap is not the satellite imagery in the visual reference. Google-backed maps retain Google attribution and their existing loading/budget behavior.
- Existing authentication and operational integrations retain their prior prototype limitations. No schema, credential, billing-limit or physical infrastructure changes were made.

Google color-scheme implementation follows the [Maps JavaScript API color-scheme documentation](https://developers.google.com/maps/documentation/javascript/mapcolorscheme).
