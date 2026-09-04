import weather_effects
from math import (
    radians,
    sin,
    cos,
    sqrt,
    atan2
)

import networkx as nx
from time import perf_counter
from shapely.geometry import Point, mapping

from graph_manager import graph_manager
from incident_engine import incident_engine
from endpoint_snapping import snap_to_road, attach_endpoints, directed_geometry


class RouteEngine:

    def haversine(
        self,
        lat1,
        lon1,
        lat2,
        lon2
    ):

        earth_radius = 6371000

        phi1 = radians(lat1)
        phi2 = radians(lat2)

        delta_phi = radians(
            lat2 - lat1
        )

        delta_lambda = radians(
            lon2 - lon1
        )

        a = (
            sin(delta_phi / 2) ** 2
            +
            cos(phi1)
            * cos(phi2)
            * sin(delta_lambda / 2) ** 2
        )

        c = 2 * atan2(
            sqrt(a),
            sqrt(1 - a)
        )

        return earth_radius * c

    def nearest_node(
        self,
        graph,
        lat,
        lon
    ):

        best_node = None
        best_distance = float("inf")

        for node, data in graph.nodes(
            data=True
        ):

            node_lon = data.get("x")
            node_lat = data.get("y")

            if (
                node_lon is None
                or node_lat is None
            ):
                continue

            distance = self.haversine(
                lat,
                lon,
                node_lat,
                node_lon
            )

            if distance < best_distance:
                best_distance = distance
                best_node = node

        if best_node is None:
            raise RuntimeError(
                "Could not find nearest road node."
            )

        return best_node

    def apply_incidents(self, graph):
        """Close both directed representations of one physical road, never nearby roads.

        A map-selected route edge takes precedence over nearest-road inference.
        Persist the initial match so another route's bbox cannot move the incident.
        """
        for incident in incident_engine.list_incidents():
            incident["affected_edges"] = []
            incident["affected_geometry"] = None
            incident["closure_scope"] = "BOTH_DIRECTIONS"
            incident["matching_status"] = "OUTSIDE_LOADED_GRAPH"
            best_edge, best_distance = None, float("inf")
            target = incident.get("target_edge_id") or incident.get("matched_edge_id")
            point = Point(incident["lon"], incident["lat"])
            for u, v, key, data in graph.edges(keys=True, data=True):
                geometry = data.get("geometry")
                if geometry is None or (target and data.get("external_id") != target):
                    continue
                nearest = geometry.interpolate(geometry.project(point))
                distance = self.haversine(incident["lat"], incident["lon"], nearest.y, nearest.x)
                rank = (round(distance, 6), str(data.get("external_id", key)))
                if best_edge is None or rank < best_rank:
                    best_edge, best_distance, best_rank = (u, v, key, data), distance, rank
            if best_edge is None or best_distance > 150:
                continue
            u, v, key, data = best_edge
            raw = data["geometry"]
            # Same endpoints AND equivalent geometry: exclude separate carriageways,
            # crossing streets and distinct parallel edges, even with the same name.
            for a, b in {(u, v), (v, u)}:
                for k, candidate in (graph.get_edge_data(a, b) or {}).items():
                    geometry = candidate.get("geometry")
                    if geometry is not None and geometry.equals(raw):
                        graph[a][b][k]["current_cost"] = float("inf")
                        incident["affected_edges"].append(candidate.get("external_id"))
            incident["affected_edges"] = sorted(set(incident["affected_edges"]))
            incident["affected_geometry"] = mapping(raw)
            incident["matched_edge_id"] = data.get("external_id")
            incident["matching_status"] = "MATCHED"
            incident["match_source"] = "SELECTED_ROUTE_EDGE" if incident.get("target_edge_id") else "NEAREST_ROAD"
            incident["match_distance_m"] = round(best_distance, 2)
        return graph


    def calculate_route(self, request):
        from traffic.routing_config import config_store
        from traffic.cost_engine import prepare_edge
        from traffic.observations import apply as apply_observations
        from traffic.turn_costs import prepare_bearings, turn_cost
        from traffic.route_search import alternatives
        started=perf_counter()
        configuration=config_store.snapshot(); config=configuration['parameters']
        loaded=perf_counter()
        graph=graph_manager.get_graph(request.start.lat,request.start.lon,request.end.lat,request.end.lon)
        graph_load_ms=(perf_counter()-loaded)*1000
        graph=self.apply_incidents(graph)
        weather_impact=weather_effects.apply(graph)
        snapped=perf_counter()
        start_snap=snap_to_road(graph,request.start,'Start'); end_snap=snap_to_road(graph,request.end,'Destination')
        start_node,end_node=attach_endpoints(graph,start_snap,end_snap)
        nearest_ms=(perf_counter()-snapped)*1000
        prepared=perf_counter()
        traffic_status=apply_observations(graph)
        for _,_,_,edge in graph.edges(keys=True,data=True): prepare_edge(edge,config)
        prepare_bearings(graph)
        prepare_ms=(perf_counter()-prepared)*1000
        computed=perf_counter()
        paths=alternatives(graph,start_node,end_node,config,getattr(request,'alternatives',3))
        compute_ms=(perf_counter()-computed)*1000
        results=[]
        for index,path in enumerate(paths):
            coords=[]; segments=[]; edges=[]; distance=eta=score=signals=0.; turns=0; mix={}; congestion=0.; incident=environment=0.
            for i,edge in enumerate(path):
                u,v,k=edge; data=graph.edges[edge]
                delay,kind=turn_cost(graph,path[i-1] if i else None,edge,config)
                if i and kind!='straight': turns+=1
                distance+=data['length_m']; eta+=data['modeled_eta_sec']+delay; score+=data['current_cost_sec']+delay
                signals+=data['signal_delay_sec']; mix[data['road_class']]=mix.get(data['road_class'],0)+data['length_m']
                if data['traffic_speed_kph'] is not None: congestion+=max(0,1-data['traffic_speed_kph']/max(.1,data['base_speed_kph']))*data['length_m']
                incident+=(1-data['incident_factor'])*data['length_m']; environment+=(1-data['environment_factor'])*data['length_m']
                geom=directed_geometry(graph,u,v,data['geometry']); points=[list(c) for c in geom.coords]
                if coords and self.haversine(coords[-1][1],coords[-1][0],points[0][1],points[0][0])>2: raise RuntimeError('Road geometry has a gap. This route needs data review.')
                coords.extend(points[1:] if coords else points)
                properties={key:data.get(key) for key in ('external_id','road_name','road_class','current_cost_sec','travel_time_sec','signal_delay_sec','road_class_penalty_sec','provenance')}
                properties['turn_penalty_sec']=delay
                segments.append(dict(type='Feature',properties=properties,geometry=mapping(geom)))
                edges.append(dict(external_id=data.get('external_id'),road_name=data.get('road_name')))
            geometry=dict(type='LineString',coordinates=coords)
            mix={k:round(v/max(distance,1)*100,2) for k,v in mix.items()}
            results.append(dict(route_id=f'AEGIS-{index+1}',geometry=geometry,distance_m=round(distance,2),distance_km=round(distance/1000,2),eta_seconds=round(eta,2),eta_minutes=round(eta/60,2),eta_min=round(eta/60,2),road_class_mix=mix,turn_count=turns,signal_delay_sec=round(signals,2),congestion_exposure=None if all(graph.edges[e]['traffic_speed_kph'] is None for e in path) else round(congestion/max(distance,1),3),incident_exposure=round(incident/max(distance,1),3),environment_risk=round(environment/max(distance,1),3),overall_score=round(score,2),reason='Lowest modeled travel plus road hierarchy and turn cost' if index==0 else 'Distinct drivable alternative; preference score includes road hierarchy',route_edges=edges,route_segments=dict(type='FeatureCollection',features=segments),route=dict(type='Feature',properties=dict(engine='NetworkX edge-state Dijkstra',source='OpenStreetMap',cost_provenance='CALIBRATED'),geometry=geometry)))
        result=dict(results[0])
        result.update(traffic_observation_status=traffic_status,alternatives=results,configuration=configuration,weather_impact=weather_impact,snapping={'method':'ROAD_SEGMENT','max_distance_m':100,'start':start_snap.metadata(),'end':end_snap.metadata()},start_node=start_node,end_node=end_node,endpoint_snap_ms=round(nearest_ms,2),nearest_node_ms=round(nearest_ms,2),graph_load_ms=round(graph_load_ms,2),cost_prepare_ms=round(prepare_ms,2),route_compute_ms=round(graph.graph.get("route_compute_ms",compute_ms),2),alternatives_ms=round(graph.graph.get("alternatives_ms",0),2),google_reference_ms=0,calibration_analysis_ms=0,total_ms=round((perf_counter()-started)*1000,2),cache_hit=graph.graph.get('cache_hit',False),incidents=incident_engine.list_incidents(),limitations=['Modeled ETA, not live traffic unless an edge has a verified reading','Turn restrictions not present in the imported topology','Up to three distinct alternatives; fewer if candidates overlap','Google is never called by route computation'])
        return result

route_engine = RouteEngine()
