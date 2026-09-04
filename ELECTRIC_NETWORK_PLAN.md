# Electrical network generation and map plan

## Verified reference, not a geographic inventory

TGSPDCL's About page reports these totals across its 15-district operating area, not Hyderabad city alone:

| Asset | Reported count |
| --- | ---: |
| 33/11 kV substations | 1,733 |
| Power transformers | 3,297 |
| 33 kV feeders | 1,366 |
| 11 kV feeders | 8,248 |
| Distribution transformers | 546,125 |

Source checked 3 September 2026: https://tgsouthernpower.org/about

These totals do not identify coordinates, capacities, feeder paths, district allocations, switching arrangements or connections. Keep them in a separate official-reference record. Generated assets must not be presented as the utility's actual GIS inventory.

## Synthetic network structure

Model 33 kV supply feeders → 33/11 kV substations, with power transformers contained within each substation → 11 kV outgoing feeders → distribution transformers → modeled local loads.

Power transformers and distribution transformers are different asset classes. Power transformers are normally displayed inside their parent substation's detail view or expanded symbol; do not scatter them independently as neighborhood transformers.

Create a graph with permanent IDs, parent relationships and explicit optional normally-open tie links. The default distribution topology is a radial modeled supply tree. Any alternate supply path must be explicitly generated and validated; visual proximity is not electrical connectivity.

Fields: asset_id, asset_type, parent_asset_id, geometry, voltage_class, modeled_capacity, district_or_zone, geometry_provenance, topology_provenance, parameter_provenance, source_reference, generator_seed, dataset_version. Store live simulation fields separately: demand, supplied_load, energized, fault_state, crew_task_id, updated_at, run_id.

Synthetic demo example, not an official Hyderabad allocation: 20 substations, 38 power transformers, 95 outgoing 11 kV feeders and 6,300 distribution transformers. These approximate the reported aggregate ratios for a manageable pilot; they are not calibrated local counts. The selected study area and demand assumptions determine the final pilot size.

## Placement and generation

1. Select an explicit Hyderabad study-area boundary. Use the existing OSM road geometry as geographic context.
2. Generate reproducible substation candidate positions spread across modeled service zones. Label every generated location SYNTHETIC; a road node is not evidence of a real electrical installation.
3. Attach power transformers within each substation. Assign outgoing feeders to the modeled transformer/bus structure.
4. Build connected feeder branches through the road network as a plausible schematic routing assumption, not surveyed cable or overhead-line geometry.
5. Allocate distribution transformers within each feeder's modeled service zone, weighted by supplied building/land-use data if available. Otherwise use explicit synthetic demand weights; do not silently claim population calibration.
6. Assign modeled loads to distribution transformers. Explicitly connect selected traffic signals and other demo assets. Hospitals may have synthetic backup supply; metro traction should use an explicitly modeled independent supply relationship rather than an ordinary street-transformer assignment.
7. Validate unique IDs, valid parents, geometry bounds, connectivity, normal energized paths and consistent load/capacity units. Validate or label overloads as intentional scenarios.
8. Persist the generated dataset with a seed/version. Never regenerate coordinates or connections during polling or page refreshes.

## Map scale and rendering

| View | Display |
| --- | --- |
| Utility overview | Operating-area/zone summaries, outage counts and clusters; no half-million individual markers |
| City view | Substation icons, clustered transformer totals, selected outages |
| Neighborhood view | Selected substation's feeders, feeder status and distribution-transformer clusters |
| Street view | Distribution transformers in the visible area, selected feeder detail and connected modeled loads |
| Selected asset | Parent/upstream path, downstream dependency highlight, capacity/load provenance, current fault and assigned task |

Use spatial viewport queries and zoom-appropriate aggregated tiles or clusters. Fetch only visible detail. Keep full-resolution topology in the backend; the browser does not need the entire regional graph. Load feeder lines on selection or at the appropriate zoom. Use batched map sources/layers instead of one DOM marker per asset. Send status changes for affected assets rather than reloading static geometry each second. Search by stable ID can navigate directly to an asset without rendering every asset first.

Clustering affects presentation only. Hidden assets remain part of the model, and cluster totals must equal their underlying records. Keep 'official utility total' and 'assets in this synthetic run' as separate counters.

## Causal behavior across portals

An outage changes electrical reachability and modeled supply for downstream assets. Only explicitly connected signals/loads change state. Traffic capacity then changes, queues evolve, and corridors are re-evaluated if their constraints change. Electric Command receives a fault; a lineman task progresses through acknowledgement, travel, assessment and completion report. Verified restoration re-energizes connected assets; modeled traffic queues drain over time rather than disappearing instantly.

This is a topology-and-capacity operations model. It is not an engineering-grade load-flow, protection-coordination or switching-authority system. No real electrical equipment is controlled.

## Expansion

Do not place all reported TGSPDCL assets inside Hyderabad. A future full-service-area synthetic model may match published totals, but requires an explicit 15-district study boundary and clearly synthetic regional allocations. Start with the bounded pilot and the same storage/query interfaces; expand without changing portal workflows. Replace synthetic records with verified inventories later while retaining IDs or an audited mapping.
