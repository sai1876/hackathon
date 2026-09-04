import json
from time import perf_counter
from pathlib import Path
import networkx as nx
from traffic.route_calibration import PAIRS
from models import RouteRequest,Coordinate
from route_engine import route_engine
from graph_manager import graph_manager
from endpoint_snapping import snap_to_road,attach_endpoints
results=[]
for pair in PAIRS[:2]:
 req=RouteRequest(start=Coordinate(**pair['origin']),end=Coordinate(**pair['destination']))
 result=route_engine.calculate_route(req)
 warm=route_engine.calculate_route(req)
 g=graph_manager.get_graph(req.start.lat,req.start.lon,req.end.lat,req.end.lon)
 a=snap_to_road(g,req.start,'Start');b=snap_to_road(g,req.end,'End');u,v=attach_endpoints(g,a,b)
 path=nx.shortest_path(g,u,v,weight='base_travel_time_sec')
 old=[min(g[x][y].values(),key=lambda d:d['base_travel_time_sec']) for x,y in zip(path,path[1:])]
 results.append({'pair':pair,'old_distance_m':round(sum(d['length_m'] for d in old),2),'old_eta_sec':round(sum(d['base_travel_time_sec'] for d in old),2),'warm_total_ms':warm['total_ms'],'warm_cache_hit':warm['cache_hit'],'new':{k:result[k] for k in ['distance_m','eta_seconds','turn_count','road_class_mix','overall_score','graph_load_ms','cost_prepare_ms','route_compute_ms','total_ms','cache_hit']},'alternatives':[{'distance_m':a['distance_m'],'eta_seconds':a['eta_seconds'],'overall_score':a['overall_score']} for a in result['alternatives']]})
 Path('route-realism-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
