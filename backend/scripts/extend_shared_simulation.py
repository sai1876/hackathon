"""Add missing domain seed records without changing imported real datasets."""
import csv,hashlib,io,json,math,random,zipfile
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from collections import Counter
root=Path(r'D:\aegisgrid\generated\shared-v1');seed=20260904;rng=random.Random(seed+1)
uid=lambda key:str(uuid5(NAMESPACE_URL,f'aegisgrid:shared:v1:{seed}:{key}'))
tables=['aegis_sim_runs','aegis_sim_assets','aegis_sim_profiles','aegis_sim_state','aegis_sim_events']
rows={t:[json.loads(line) for line in (root/(t+'.jsonl')).read_text(encoding='utf-8').splitlines()] for t in tables}
assets=rows[tables[1]];states=rows[tables[3]];profiles=rows[tables[2]];events=rows[tables[4]];run=rows[tables[0]][0]['id'];known={a['id'] for a in assets}
def add(key,kind,name,x,y,values,parent=None,provenance='SIMULATED',**spec):
 id=uid(key)
 if id in known:return id
 known.add(id);zone=f'Z-{min(5,max(0,int((x-78.25)/.4*6)))}-{min(3,max(0,int((y-17.25)/.35*4)))}'
 assets.append(dict(id=id,kind=kind,name=name,longitude=x,latitude=y,parent_id=parent,zone_id=zone,provenance=provenance,spec=spec))
 states.append(dict(id=uid('state:'+id),run_id=run,asset_id=id,version=0,sim_seconds=0,provenance='SIMULATED',values=values));return id
for a in list(assets):
 if a['kind']=='TRAFFIC_SIGNAL':
  for phase in range(2):add(a['id']+f':group:{phase}','SIGNAL_GROUP',a['name']+f' modelled phase {phase+1}',a['longitude'],a['latitude'],dict(phase='RED',remaining_seconds=3,queue_vehicles=0,controller_mode='SIMULATED_ALL_RED_START'),parent=a['id'],cycle_seconds=90,green_seconds=39,amber_seconds=3,all_red_seconds=3,offset_seconds=phase*45,geometry_status='Approaches not surveyed; abstract mutually exclusive phases')
 if a['kind']=='METRO_STATION':
  add(a['id']+':queue','METRO_PASSENGER_QUEUE',a['name']+' passenger queue',a['longitude'],a['latitude'],dict(waiting=0,arrived=0,boarded=0,abandoned=0,initial_time='05:00'),parent=a['id'],profile_asset_id=a['id'],conservation_rule='waiting = arrived - boarded - abandoned')
  add(a['id']+':turnback','METRO_SERVICE_RESOURCE',a['name']+' service assumptions',a['longitude'],a['latitude'],dict(available=True),parent=a['id'],minimum_headway_seconds=120,turnback_seconds=180,provenance_note='Unvalidated operational assumptions; not a dispatch authority')
roads=Path(r'D:\aegisgrid-road\data\hyderabad\hyderabad_roads.geojson');features=json.loads(roads.read_text(encoding='utf-8'))['features']
selected=[]
for f in features:
 if f['geometry']['type']!='LineString':continue
 xy=f['geometry']['coordinates'];x,y=xy[len(xy)//2][:2];p=f['properties']
 if not (78.25<x<78.65 and 17.25<y<17.6) or p.get('access') in ['private','no']:continue
 key=f"{p['u']}_{p['v']}_{p.get('key',0)}";selected.append((hashlib.sha256(key.encode()).digest(),key,f,x,y))
selected.sort(key=lambda item:item[0])
for _,key,f,x,y in selected[:5000]:
 p=f['properties'];speed={'motorway':70,'trunk':60,'primary':45,'secondary':40,'tertiary':30,'residential':20,'service':15}.get(str(p.get('highway')),25);count=rng.randint(0,8)
 add('road:'+key,'ROAD_TRAFFIC',str(p.get('name') or key),x,y,dict(vehicle_count=count,queue_vehicles=0,avg_speed_kmph=round(speed*(1-count/40),2),blocked=False,water_depth_mm=0),provenance='SOURCE_OSM',osm_edge=key,length_m=p.get('length'),freeflow_kmph_assumption=speed,geometry=f['geometry'],traffic_provenance='SIMULATED')
del features,selected
source=Path(r'D:\download chrome\data');gtfs=source/'Telangana_opendata_gtfs_hmrl_02_September_2026.zip'
with zipfile.ZipFile(gtfs) as z:
 trips=list(csv.DictReader(io.StringIO(z.read('trips.txt').decode('utf-8-sig'))));stop_times=list(csv.DictReader(io.StringIO(z.read('stop_times.txt').decode('utf-8-sig'))));stops={s['stop_id']:s for s in csv.DictReader(io.StringIO(z.read('stops.txt').decode('utf-8-sig')))}
first={}
for item in stop_times:
 if item['trip_id'] not in first or int(item['stop_sequence'])<int(first[item['trip_id']]['stop_sequence']):first[item['trip_id']]=item
blocks={}
for trip in trips:
 if trip['service_id']!='WK':continue
 start=first[trip['trip_id']];block=trip['block_id'] or trip['trip_id']
 if block not in blocks or start['departure_time']<blocks[block][1]['departure_time']:blocks[block]=(trip,start)
for block,(trip,start) in blocks.items():
 s=stops[start['stop_id']];add('train:'+block,'METRO_TRAIN',block,float(s['stop_lon']),float(s['stop_lat']),dict(status='NOT_IN_SERVICE',passenger_count=0,trip_id=None,next_departure=start['departure_time']),block_id=block,service_id='WK',line_id=trip['route_id'],capacity_passengers=1000,capacity_provenance='SIMULATED',schedule_source=gtfs.name)
add('controls','SCENARIO_CONTROL','Shared simulation controls',78.45,17.425,dict(running=False,speed=1,rain_enabled=False,rain_mm_hour=0,traffic_demand_multiplier=1,metro_demand_multiplier=1,power_demand_multiplier=1),authority='MAIN_COMMAND_ONLY')
# Scenario templates are not active incidents or executed AI actions.
for a in [v for v in assets if v['kind']=='WEATHER_AREA']:
 add(a['id']+':water','WATERLOGGING_POINT',a['name']+' modelled drainage point',a['longitude'],a['latitude'],dict(depth_mm=0,blocked=False),parent=a['id'],drainage_mm_hour=a['spec']['drainage_mm_hour'],road_block_threshold_mm=150)
for key,title,kind in [('rain-flood','Heavy rain and local waterlogging','WEATHER'),('signal-outage','Signal power interruption','TRAFFIC'),('metro-surge','Metro passenger surge','METRO')]:
 add('scenario:'+key,'SCENARIO_TEMPLATE',title,78.45,17.425,dict(status='DRAFT',active=False),scenario_kind=kind,requires_operator_start=True)
for domain in ['TRAFFIC','METRO','ELECTRIC']:
 add('agent:'+domain,'AI_AGENT_CONFIG',domain+' decision agent configuration',78.45,17.425,dict(status='NOT_RUNNING',pending_decisions=0),domain=domain,shared_event_source='aegis_sim_events',requires_approval=True,mode='RULES_WITH_OPTIONAL_GROQ_EXPLANATION')
event_id=uid('event:seed-defined')
if not any(e['id']==event_id for e in events):events.append(dict(id=event_id,run_id=run,sim_seconds=0,kind='SCENARIO_BASELINE_DEFINED',zone_id=None,parent_event_id=None,provenance='SIMULATED',payload=dict(seed=seed,status='PAUSED',message='Generated baseline definition; no incident or AI intervention has been executed.')))
ids={a['id'] for a in assets};assert len(ids)==len(assets);assert all(a['parent_id'] is None or a['parent_id'] in ids for a in assets);assert len(states)==len(assets);assert all(s['asset_id'] in ids for s in states)
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
for t in tables:
 p=root/(t+'.jsonl');p.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in rows[t]),encoding='utf-8');manifest['checksums'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
manifest.update(counts={t:len(rows[t]) for t in tables},asset_counts=dict(Counter(a['kind'] for a in assets)),bytes=sum((root/(t+'.jsonl')).stat().st_size for t in tables))
manifest['limitations']+=['Traffic state covers a deterministic 5,000-road sample, not all 374,988 roads.','Signal phases, train capacities, headway and turnback timings are simulation assumptions.','Incidents, executed actions and AI decisions remain empty until a scenario actually generates them.']
(root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps({'counts':manifest['counts'],'assets':manifest['asset_counts'],'bytes':manifest['bytes']},indent=2))
