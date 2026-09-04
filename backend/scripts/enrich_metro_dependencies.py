"""Historically anchored, explicitly modelled metro demand and cross-domain links."""
import csv,hashlib,json,math,random
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from collections import Counter
root=Path(r'D:\aegisgrid\generated\shared-v1');seed=20260904;uid=lambda key:str(uuid5(NAMESPACE_URL,f'aegisgrid:shared:v1:{seed}:{key}'));rng=random.Random(seed+2)
assets=[json.loads(l) for l in (root/'aegis_sim_assets.jsonl').read_text(encoding='utf-8').splitlines()];stations=sorted([a for a in assets if a['kind']=='METRO_STATION'],key=lambda a:a['id']);run=json.loads((root/'aegis_sim_runs.jsonl').read_text())['id'];newassets=[];newstates=[];profiles=[]
source_url='https://www.ltmetro.in/investors/annual-reports';anchor=443000
reference=dict(url=source_url,document='L&T Metro Rail Hyderabad Annual Report 2024-25',pdf_page=31,reported_average_daily_journeys=anchor,interpretation='Historical system-wide anchor, not observed station counts or live demand')
interchanges={'AME','MGB','PRG','JBS'};jobs={'RDG','HTC','DGC','MAD','BEG','PUN'}
def add(key,kind,name,source,target=None,**spec):
 id=uid(key);newassets.append(dict(id=id,kind=kind,name=name,longitude=source['longitude'],latitude=source['latitude'],parent_id=source['id'],zone_id=source['zone_id'],provenance='SIMULATED',spec=dict(source_asset_id=source['id'],target_asset_id=target['id'] if target else None,**spec)));newstates.append(dict(id=uid('state:'+id),run_id=run,asset_id=id,version=0,sim_seconds=0,provenance='SIMULATED',values={'enabled':True}));return id
# Allocate integer entry counts jointly so the daily totals match the historical anchor.
# Transfers must be accounted for separately from entries by the future passenger engine.
daily={}
for day,factor in [('weekday',1.1),('weekend',.75)]:
 raw=[]
 for station in stations:
  code=station['spec']['gtfs_stop_id'];weight=(2.2 if code in interchanges else 1.0)*(1.6 if code in jobs else 1.0);station_rng=random.Random(seed+int(station['id'].replace('-','')[:8],16));weight*=station_rng.uniform(.8,1.2)
  for slot in range(96):
   hour=slot/4
   morning=math.exp(-((hour-(9 if day=='weekday' else 11))/1.7)**2);evening=math.exp(-((hour-18)/2.2)**2)
   shape=.15+(morning*.7+evening*1.3 if code in jobs else morning*1.3+evening*.8)
   if day=='weekend':shape=.3+.55*math.exp(-((hour-15)/4)**2)
   raw.append(weight*shape if 6<=hour<23 else 0)
 total=round(anchor*factor);scaled=[v/sum(raw)*total for v in raw];counts=[math.floor(v) for v in scaled]
 for index in sorted(range(len(raw)),key=lambda i:scaled[i]-counts[i],reverse=True)[:total-sum(counts)]:counts[index]+=1
 assert sum(counts)==total
 daily[day]=total
 for i,station in enumerate(stations):
  values=counts[i*96:(i+1)*96];profiles.append(dict(id=uid('demand-v2:'+day+':'+station['id']),asset_id=station['id'],kind='passenger_entries_per_15min_'+day,interval_seconds=900,provenance='SIMULATED_HISTORICALLY_ANCHORED',values=values))
  if day=='weekday':
   weights=[]
   for target in stations:
    if target['id']==station['id']:continue
    distance=111*math.sqrt(((target['longitude']-station['longitude'])*.955)**2+(target['latitude']-station['latitude'])**2);attraction=2 if target['spec']['gtfs_stop_id'] in jobs|interchanges else 1
    weights.append((target['id'],attraction*math.exp(-distance/12)))
   total_weight=sum(w for _,w in weights)
   add('od:'+station['id'],'METRO_OD_MODEL',station['name']+' destination model',station,destinations=[{'station_id':id,'probability':w/total_weight} for id,w in weights],reference=reference,origin_weekday_entries=sum(values),note='Generated gravity model. No station-level survey claims. Transfer demand is separate from entry counts.')
# Explicit modelled power dependencies. These are not surveyed cable routes.
supplies=[a for a in assets if a['kind']=='DISTRIBUTION_TRANSFORMER'];feeders=[a for a in assets if a['kind']=='FEEDER']
def distance(a,b):return ((a['longitude']-b['longitude'])*.955)**2+(a['latitude']-b['latitude'])**2
for target in [a for a in assets if a['kind'] in ['METRO_STATION','TRAFFIC_SIGNAL']]:
 candidates=feeders if target['kind']=='METRO_STATION' else supplies;source=min(candidates,key=lambda a:distance(a,target))
 add('power-link:'+target['id'],'INFRASTRUCTURE_DEPENDENCY',source['name']+' supplies '+target['name'],source,target,relationship='POWER_SUPPLY',distance_km=round(111*math.sqrt(distance(source,target)),3),backup_seconds=300 if target['kind']=='TRAFFIC_SIGNAL' else 900,assumption='Nearest modelled supply; requires validation before real operations')
for area in [a for a in assets if a['kind']=='WEATHER_AREA']:
 for domain in ['TRAFFIC','METRO','ELECTRIC']:
  add('weather-link:'+area['id']+domain,'CROSS_DOMAIN_RULE',area['name']+' affects '+domain,area,domain=domain,shared_zone_id=area['zone_id'],requires_same_event_id=True,rule={'TRAFFIC':'Rain reduces capacity; water accumulates as rainfall minus drainage; blocked roads exclude routes.','METRO':'Additional entries are a fraction of displaced road passenger trips, capped by access and service availability.','ELECTRIC':'Rain may add pumping demand, lower cooling demand or cause outages; load must not universally increase.'}[domain],mode='SIMULATION_ASSUMPTION')
 # Hourly load-factor profile is shared through the zone, not independently randomized per portal.
 values=[round(.55+.22*math.exp(-((i/4-10)/3)**2)+.4*math.exp(-((i/4-19)/2.8)**2),4) for i in range(96)]
 profiles.append(dict(id=uid('electric-demand:'+area['id']),asset_id=area['id'],kind='electric_load_factor',interval_seconds=900,provenance='SIMULATED_UNCALIBRATED',values=values))
# Use the supplied real consumption categories as a reference only: do not invent units for its load field.
consumption=Path(r'D:\download chrome\data\consumption_detail_06_2021.csv');categories=Counter();total_rows=0
with consumption.open(encoding='utf-8-sig') as f:
 for row in csv.DictReader(f):categories[row['catdesc']]+=1;total_rows+=1
metadata=dict(historical_ridership_reference=reference,daily_targets=daily,weekly_average=(5*daily['weekday']+2*daily['weekend'])/7,station_count=len(stations),demand_values=114*96,source_consumption_rows=total_rows,consumption_category_row_counts=dict(categories),rainfall_note='No readings inside checked Hyderabad bounds in the supplied 2021-25 rainfall file; not a local observation source.',limitations=['Station allocations, destination choices, day-type factors and capacities are simulated assumptions.','These are profiles and dependency definitions; a simulation engine must apply them to evolve queues and state.'])
assert metadata['weekly_average']==anchor
assert all(len(p['values'])==96 and min(p['values'])>=0 for p in profiles)
for name,data in [('enrichment-assets',newassets),('enrichment-state',newstates),('enrichment-profiles',profiles)]:
 (root/(name+'.jsonl')).write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
(root/'enrichment-report.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8');print(json.dumps({'assets':len(newassets),'profiles':len(profiles),'daily_targets':daily,'weekly_average':metadata['weekly_average']},indent=2))
