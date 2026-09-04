"""Generate a reproducible synthetic electrical layout constrained to imported OSM roads."""
import json, math, random, sys
from pathlib import Path
import networkx as nx

sys.path.insert(0, r'D:\aegisgrid\backend')
from electric_engine import generate

rng = random.Random(3297)
source = Path(r'D:\aegisgrid-road\data\hyderabad\hyderabad_roads.geojson')
features = json.loads(source.read_text(encoding='utf-8'))['features']
graph = nx.Graph()
for feature in features:
    p, geom = feature['properties'], feature['geometry']
    if geom['type'] != 'LineString': continue
    if p.get('highway') not in ('residential','tertiary','secondary','unclassified','living_street','service','primary'): continue
    if p.get('bridge') not in (None,'no','False') or p.get('tunnel') not in (None,'no','False'): continue
    if p.get('access') in ('private','no'): continue
    coords = geom['coordinates']
    if not all(78.30 < x < 78.61 and 17.30 < y < 17.56 for x,y in coords): continue
    u,v = str(p['u']),str(p['v'])
    length = float(p.get('length') or 1)
    if u == v or (graph.has_edge(u,v) and graph[u][v]['weight'] <= length): continue
    graph.add_node(u, pos=coords[0]); graph.add_node(v,pos=coords[-1])
    graph.add_edge(u,v,weight=length,coords=coords,u=u,name=p.get('name') or 'Unnamed local road',osm_id=str(p['osmid']))
del features
graph = graph.subgraph(max(nx.connected_components(graph),key=len)).copy()
nodes = sorted(graph)
print('Eligible connected road graph:',len(graph),graph.number_of_edges(),flush=True)

def dist(a,b):
    x,y=graph.nodes[a]['pos']; xx,yy=graph.nodes[b]['pos']
    return ((x-xx)*0.955)**2+(y-yy)**2

# Road-node density naturally gives developed neighborhoods more candidates.
# Seeded rejection spacing avoids both a lattice and randomly overlapping sites.
candidates = [n for n in nodes if graph.degree(n) >= 3]
rng.shuffle(candidates)
sites=[]
for n in candidates:
    if all(dist(n,s) > 0.023**2 for s in sites): sites.append(n)
    if len(sites)==20: break
assert len(sites)==20
_, paths = nx.multi_source_dijkstra(graph,sites,weight='weight')
zones={s:[] for s in sites}
for n,path in paths.items(): zones[path[0]].append(n)
del paths
assets=generate()
used=set(sites)

def route(path):
    points=[]
    for u,v in zip(path,path[1:]):
        edge=graph[u][v]
        coords=edge['coords'] if edge['u']==u else edge['coords'][::-1]
        points.extend(coords if not points else coords[1:])
    if not points: points=[graph.nodes[path[0]]['pos']]*2
    return points

def locate(asset_id,node,path=None):
    a=assets[asset_id]
    a['lon'],a['lat']=graph.nodes[node]['pos']
    a['layout_version']='osm-constrained-v2'
    a['road_node_id']=node
    a['location_basis']='SYNTHETIC placement on imported OSM road network; not a surveyed utility site'
    a['road_context']=next(iter(graph[node].values()))['name']
    if path: a['connection_geometry']={'type':'LineString','coordinates':route(path)}

feeder_index=0; dt_index=0
for index,site in enumerate(sites):
    sid=f'SS-{index+1:03}'
    zone=graph.subgraph(zones[site]).copy()
    lengths, station_paths=nx.single_source_dijkstra(zone,site,weight='weight')
    locate(sid,site)
    supply=min((n for n in zone if n!=site),key=lambda n:abs(lengths[n]-200))
    locate(f'IN-{index+1:03}',supply)
    assets[sid]['connection_geometry']={'type':'LineString','coordinates':route(station_paths[supply][::-1])}
    for a in assets.values():
        if a['station']==sid and a['kind']=='POWER_TRANSFORMER': locate(a['id'],site)
    count=5 if index<15 else 4
    pool=[n for n in zone if n not in used]
    # Spatial k-means within the road-distance catchment forms irregular feeder areas.
    centers=[graph.nodes[n]['pos'] for n in rng.sample(pool,count)]
    for _ in range(15):
        groups=[[] for _ in centers]
        for n in pool:
            x,y=graph.nodes[n]['pos']
            k=min(range(count),key=lambda k:(x-centers[k][0])**2+(y-centers[k][1])**2)
            groups[k].append(n)
        for k,g in enumerate(groups):
            if g: centers[k]=[sum(graph.nodes[n]['pos'][i] for n in g)/len(g) for i in (0,1)]
    for f in range(count):
        feeder_index+=1; fid=f'F-{feeder_index:03}'
        group=groups[f]
        if not group: group=pool
        cx,cy=centers[f]
        anchor=min(group,key=lambda n:(graph.nodes[n]['pos'][0]-cx)**2+(graph.nodes[n]['pos'][1]-cy)**2)
        locate(fid,anchor,station_paths[anchor])
        _, branch_paths=nx.single_source_dijkstra(zone,anchor,weight='weight')
        available=[n for n in group if n not in used and n!=anchor]
        need=67 if feeder_index<=30 else 66
        if len(available)<need:
            extras=sorted((n for n in pool if n not in used and n not in available and n!=anchor),key=lambda n:dist(n,anchor))
            available+=extras[:need-len(available)]
        assert len(available)>=need,(sid,f,len(available))
        # Spread transformers over existing street nodes without duplicate positions.
        chosen=rng.sample(available,need)
        used.update(chosen)
        for d,node in enumerate(chosen):
            dt_index+=1; did=f'DT-{dt_index:05}'
            locate(did,node,branch_paths[node])
            if d==0:
                sig=f'SIG-{feeder_index:03}'
                locate(sig,node)
    print(sid,'road nodes',len(zone),flush=True)
assert dt_index==6300
out=Path('electric-road-layout.json')
out.write_text(json.dumps(assets,separators=(',',':')),encoding='utf-8')
print('Saved',len(assets),'assets;',out.stat().st_size,'bytes',flush=True)
