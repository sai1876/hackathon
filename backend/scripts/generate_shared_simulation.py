"""Reproducible offline simulation seed. Does not connect to or change any database."""
import argparse,csv,hashlib,io,json,math,random,zipfile
from collections import Counter
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL

def generate(source,roads,out,seed):
 rng=random.Random(seed);out.mkdir(parents=True,exist_ok=True)
 uid=lambda key:str(uuid5(NAMESPACE_URL,f"aegisgrid:shared:v1:{seed}:{key}"))
 rows={name:[] for name in ['aegis_sim_runs','aegis_sim_assets','aegis_sim_profiles','aegis_sim_state','aegis_sim_events']}
 run=uid('baseline');assets=rows['aegis_sim_assets'];profiles=rows['aegis_sim_profiles'];states=rows['aegis_sim_state']
 def zone(lon,lat):return f"Z-{min(5,max(0,int((lon-78.25)/.4*6)))}-{min(3,max(0,int((lat-17.25)/.35*4)))}"
 def asset(key,kind,name,lon,lat,parent=None,provenance='SIMULATED',**spec):
  item=dict(id=uid(key),kind=kind,name=name,longitude=lon,latitude=lat,parent_id=parent,zone_id=zone(lon,lat),provenance=provenance,spec=spec)
  assets.append(item);return item
 def state(a,**values):states.append(dict(id=uid('state:'+a['id']),run_id=run,asset_id=a['id'],version=0,sim_seconds=0,provenance='SIMULATED',values=values))
 def profile(a,kind,base):
  values=[]
  for slot in range(96):
   hour=slot/4
   peak=math.exp(-((hour-8.5)/1.6)**2)+1.15*math.exp(-((hour-18)/2.0)**2)
   value=base*(.18+.6*peak)*(1+rng.uniform(-.12,.12))
   if kind=='passengers_per_minute' and (hour<6 or hour>=23):value=0
   values.append(round(value,3))
  profiles.append(dict(id=uid('profile:'+a['id']),asset_id=a['id'],kind=kind,interval_seconds=900,provenance='SIMULATED',values=values))
 features=json.loads(roads.read_text(encoding='utf-8'))['features']
 candidates=[f for f in features if 78.25<float(f['geometry']['coordinates'][0])<78.65 and 17.25<float(f['geometry']['coordinates'][1])<17.60]
 candidates.sort(key=lambda f:str(f['properties']['osmid']));rng.shuffle(candidates)
 sites=[]
 for f in candidates:
  x,y=f['geometry']['coordinates'][:2]
  if all(((x-a['longitude'])*.955)**2+(y-a['latitude'])**2>.018**2 for a in sites):
   sites.append(asset('sub:'+str(len(sites)),'SUBSTATION',f"Simulation substation {len(sites)+1}",x,y,capacity_kva=40000,osm_node=str(f['properties']['osmid']),location_basis='Road-node anchor; not surveyed infrastructure'))
  if len(sites)==60:break
 assert len(sites)==60
 transformers={};feeders={}
 for sub in sites:
  pts=[asset(sub['id']+':pt:'+str(i),'POWER_TRANSFORMER',sub['name']+f" power transformer {i+1}",sub['longitude'],sub['latitude'],sub['id'],capacity_kva=20000) for i in range(2)]
  transformers[sub['id']]=pts
  feeders[sub['id']]=[asset(sub['id']+':f:'+str(i),'FEEDER',sub['name']+f" feeder {i+1}",sub['longitude'],sub['latitude'],pts[i//2]['id'],capacity_kva=10000) for i in range(4)]
 for i,f in enumerate(candidates[:4800]):
  x,y=f['geometry']['coordinates'][:2];sub=min(sites,key=lambda a:((x-a['longitude'])*.955)**2+(y-a['latitude'])**2)
  angle=math.atan2(y-sub['latitude'],x-sub['longitude']);sector=int((angle+math.pi)/(2*math.pi)*4)%4
  capacity=rng.choice([100,160,250,315,500]);a=asset('dt:'+str(i),'DISTRIBUTION_TRANSFORMER',f"Simulation DT {i+1:05}",x,y,feeders[sub['id']][sector]['id'],capacity_kva=capacity,osm_node=str(f['properties']['osmid']))
  state(a,load_kva=round(capacity*rng.uniform(.25,.5),2),status='ENERGIZED')
 # Parent loads are derived from children, never separately randomized.
 loads={s['asset_id']:s['values']['load_kva'] for s in states}
 for kind in ['FEEDER','POWER_TRANSFORMER','SUBSTATION']:
  for a in [v for v in assets if v['kind']==kind]:
   load=round(sum(loads.get(c['id'],0) for c in assets if c['parent_id']==a['id']),2);loads[a['id']]=load;state(a,load_kva=load,status='OVERLOADED' if load>a['spec']['capacity_kva'] else 'ENERGIZED')
 gtfs=source/'Telangana_opendata_gtfs_hmrl_02_September_2026.zip'
 with zipfile.ZipFile(gtfs) as z:stops=list(csv.DictReader(io.StringIO(z.read('stops.txt').decode('utf-8-sig'))))
 for stop in stops:
  if stop['location_type']!='1':continue
  a=asset('metro:'+stop['stop_id'],'METRO_STATION',stop['stop_name'],float(stop['stop_lon']),float(stop['stop_lat']),provenance='SOURCE_GTFS',gtfs_stop_id=stop['stop_id'],platform_capacity_assumption=rng.choice([500,700,900]),capacity_provenance='SIMULATED',source_file=gtfs.name)
  state(a,status='OPEN');profile(a,'passengers_per_minute',rng.uniform(8,45))
 for f in candidates:
  if f['properties'].get('highway')!='traffic_signals':continue
  x,y=f['geometry']['coordinates'][:2];a=asset('signal:'+str(f['properties']['osmid']),'TRAFFIC_SIGNAL','OSM signal '+str(f['properties']['osmid']),x,y,provenance='SOURCE_OSM',osm_node=str(f['properties']['osmid']))
  state(a,controller_phase='UNKNOWN',queue_vehicles=0,observation_status='NO_LIVE_FEED')
 for col in range(6):
  for row in range(4):
   x=78.25+col*.4/6;y=17.25+row*.35/4
   a=asset(f'zone:{col}:{row}','WEATHER_AREA',f'Simulation area Z-{col}-{row}',x+.4/12,y+.35/8,polygon=[[x,y],[x+.4/6,y],[x+.4/6,y+.35/4],[x,y+.35/4],[x,y]],drainage_mm_hour=rng.uniform(8,25),rainfall_traffic_sensitivity=.6,mode_shift_max_fraction=.3,assumption_status='UNCALIBRATED')
   state(a,rainfall_mm_hour=0,water_depth_mm=0,road_capacity_factor=1,metro_demand_factor=1,electric_load_factor=1)
   profile(a,'vehicles_per_minute',rng.uniform(100,400))
 rows['aegis_sim_runs'].append(dict(id=run,name='Hyderabad shared baseline',seed=seed,status='PAUSED',sim_seconds=0,version=0,configuration=dict(service_date='2026-09-03',start_time='05:00:00',timezone='Asia/Kolkata',clock_owner='BACKEND',rules_version='shared-v1',generated_data=True,note='Baseline only; a simulation engine must evolve state and apply shared causal events.')))
 ids={a['id'] for a in assets};assert len(ids)==len(assets)
 assert all(a['parent_id'] is None or a['parent_id'] in ids for a in assets)
 assert all(s['asset_id'] in ids for s in states)
 assert len({s['asset_id'] for s in states})==len(states)==len(assets)
 assert all(len(p['values'])==96 and min(p['values'])>=0 for p in profiles)
 checks={}
 for table,data in rows.items():
  path=out/(table+'.jsonl');path.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in data),encoding='utf-8');checks[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
 manifest=dict(seed=seed,counts={k:len(v) for k,v in rows.items()},asset_counts=dict(Counter(a['kind'] for a in assets)),bytes=sum((out/k).stat().st_size for k in checks),checksums=checks,sources={roads.name:hashlib.sha256(roads.read_bytes()).hexdigest(),gtfs.name:hashlib.sha256(gtfs.read_bytes()).hexdigest()},limitations=['Generated electrical locations and capacities are not surveyed assets.','Rainfall/drainage/mode-shift coefficients and demand profiles are uncalibrated assumptions.','Historical consumption and rainfall files discovered but not used without unit and spatial validation.','Breakdown coordinates conflict; excluded from asset placement.','No fabricated official station, train timetable, signal phase or live passenger observation.','No simulation engine or portal switch is performed by this generator.','Counts are a city simulation sample, not statewide utility totals.'])
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps(manifest,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(r'D:\download chrome\data'));p.add_argument('--roads',type=Path,default=Path(r'D:\aegisgrid-road\data\hyderabad\hyderabad_nodes.geojson'));p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=20260904);a=p.parse_args();generate(a.source,a.roads,a.out,a.seed)
