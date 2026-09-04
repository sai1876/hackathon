from seed_validation import equivalent
"""Full database road coverage in compact state blocks; no Google requests."""
import concurrent.futures,hashlib,json,math,random,time
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
import httpx
from dotenv import dotenv_values
from supabase import create_client
from shapely import wkb
root=Path(r'D:\aegisgrid\generated\shared-v1');cache=root/'road-index-pages';cache.mkdir(exist_ok=True)
c=dotenv_values(Path(__file__).resolve().parents[1]/'.env');headers={'apikey':c['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+c['SUPABASE_SERVICE_ROLE_KEY']};url=c['SUPABASE_URL'].rstrip('/')+'/rest/v1/road_segments'
records=[];positions={};cursor=None;page_number=0;batch_size=5000
cursor_cache=root/'road-cursor-pages';cursor_cache.mkdir(exist_ok=True)
with httpx.Client(headers=headers,timeout=60) as client:
 r=client.get(url,params={'select':'id','limit':1},headers={'Prefer':'count=exact'});r.raise_for_status();total=int(r.headers['content-range'].split('/')[-1])
 while True:
  path=cursor_cache/f'{page_number:04}.json'
  if path.exists():rows=json.loads(path.read_text(encoding='utf-8'))
  else:
   while True:
    result=client.post(c['SUPABASE_URL'].rstrip('/')+'/rest/v1/rpc/aegis_export_road_index',json={'p_after':cursor,'p_limit':batch_size})
    if result.status_code==500 and batch_size>100:
     batch_size=max(100,batch_size//2);print('Reducing export batch to',batch_size,flush=True);continue
    result.raise_for_status();rows=result.json();break
   path.write_text(json.dumps(rows,separators=(',',':')),encoding='utf-8')
  records.extend(rows);page_number+=1
  if page_number%10==1:print('Road index exported',len(records),'/',total,flush=True)
  if len(records)==total:break
  if not rows:raise RuntimeError("Road export ended before expected count")
  cursor=rows[-1]['id']
 assert len(records)==total and len({r['id'] for r in records})==total
nodes=json.loads(Path(r'D:\aegisgrid-road\data\hyderabad\hyderabad_nodes.geojson').read_text(encoding='utf-8'))['features'];positions={str(n['properties']['osmid']):n['geometry']['coordinates'][:2] for n in nodes};del nodes
missing=[r for r in records if not r.get('anchor') and str(r['osm_u']) not in positions]
print('Unmatched road anchors:',len(missing),flush=True)
with httpx.Client(headers=headers,timeout=60) as client:
 for i in range(0,len(missing),100):
  group=missing[i:i+100];response=client.get(url,params={'select':'id,geometry','id':'in.('+','.join(r['id'] for r in group)+')'});response.raise_for_status();geometries={r['id']:r['geometry'] for r in response.json()}
  for row in group:
   point=wkb.loads(bytes.fromhex(geometries[row['id']])).interpolate(.5,normalized=True);row['anchor']=[point.x,point.y]
seed=20260904;uid=lambda key:str(uuid5(NAMESPACE_URL,f'aegisgrid:shared:v1:{seed}:{key}'));run=json.loads((root/'aegis_sim_runs.jsonl').read_text())['id']
tiles={}
for row in records:
 x,y=row.get('anchor') or positions[str(row['osm_u'])];key=(math.floor(x/.01),math.floor(y/.01));tiles.setdefault(key,[]).append((row,x,y))
assets=[];states=[]
for (gx,gy),roads in sorted(tiles.items()):
 for start in range(0,len(roads),500):
  group=roads[start:start+500];key=f'roads:{gx}:{gy}:{start}';id=uid(key);x=(gx+.5)*.01;y=(gy+.5)*.01
  zone=f'Z-{min(5,max(0,int((x-78.25)/.4*6)))}-{min(3,max(0,int((y-17.25)/.35*4)))}' if 78.25<=x<=78.65 and 17.25<=y<=17.6 else 'OUTSIDE_WEATHER_GRID'
  references=[];traffic=[]
  for row,lon,lat in group:
   speed=float(row['free_flow_speed_kmph'] or 25);length=float(row['length_m'] or 0);rng=random.Random(int(hashlib.sha256(row['id'].encode()).hexdigest()[:12],16));vehicles=rng.randint(0,max(1,int(length/60)))
   references.append([row['id'],row['external_id'],round(lon,7),round(lat,7),round(length,2),speed]);traffic.append([round(speed*(1-min(.6,vehicles*.02)),2),vehicles,0,0,False])
  assets.append(dict(id=id,kind='ROAD_TRAFFIC_BLOCK',name=key,longitude=x,latitude=y,parent_id=None,zone_id=zone,provenance='SOURCE_OSM',spec=dict(road_count=len(group),bbox=[gx*.01,gy*.01,(gx+1)*.01,(gy+1)*.01],columns=['source_road_id','external_id','longitude','latitude','length_m','freeflow_kmph'],roads=references,reference_project='existing operational road_segments',state_provenance='SIMULATED')))
  states.append(dict(id=uid('state:'+id),run_id=run,asset_id=id,version=0,sim_seconds=0,provenance='SIMULATED',values=dict(columns=['speed_kmph','vehicle_count','queue_vehicles','water_depth_mm','blocked'],roads=traffic)))
for name,data in [('road-block-assets',assets),('road-block-state',states)]:
 (root/(name+'.jsonl')).write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in data),encoding='utf-8')
print('Prepared',len(assets),'blocks covering',sum(a['spec']['road_count'] for a in assets),'roads',flush=True)
new=dotenv_values(Path(__file__).resolve().parents[1]/'.env.simulation');db=create_client(new['SIMULATION_SUPABASE_URL'],new['SIMULATION_SUPABASE_SERVICE_ROLE_KEY']);current=db.table('aegis_sim_runs').select('status,version').eq('id',run).single().execute().data
assert current['status']=='PAUSED' and current['version']==0
for table,data in [('aegis_sim_assets',assets),('aegis_sim_state',states)]:
 for i in range(0,len(data),10):
  db.table(table).upsert(data[i:i+10],on_conflict='id',ignore_duplicates=True).execute()
  if i%200==0:print(table,i,'/',len(data),flush=True)
 # Verify coverage and values block-by-block in bounded reads.
 for i in range(0,len(data),20):
  actual=db.table(table).select('*').in_('id',[r['id'] for r in data[i:i+20]]).execute().data;lookup={r['id']:r for r in actual}
  assert all(equivalent(r,lookup.get(r['id'])) for r in data[i:i+20])
print('All road blocks verified. Replacing the previous sample source.',flush=True)
# Retire only the generated five-thousand-road sample after full coverage is verified.
old=[json.loads(l) for l in (root/'aegis_sim_assets.jsonl').read_text(encoding='utf-8').splitlines()];obsolete=[a['id'] for a in old if a['kind']=='ROAD_TRAFFIC']
for i in range(0,len(obsolete),100):
 ids=obsolete[i:i+100];db.table('aegis_sim_state').delete().eq('run_id',run).eq('version',0).in_('asset_id',ids).execute();db.table('aegis_sim_assets').delete().eq('kind','ROAD_TRAFFIC').in_('id',ids).execute()
for table,newrows in [('aegis_sim_assets',assets),('aegis_sim_state',states)]:
 p=root/(table+'.jsonl');original=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines()];newids={r['id'] for r in newrows};original=[r for r in original if r['id'] not in newids and (r.get('asset_id') not in obsolete if table=='aegis_sim_state' else r['id'] not in obsolete)]
 p.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in original+newrows),encoding='utf-8')
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));manifest['road_coverage']=total;manifest['road_blocks']=len(assets)
for table in ['aegis_sim_assets','aegis_sim_state']:
 p=root/(table+'.jsonl');manifest['checksums'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest();manifest['counts'][table]=sum(1 for _ in p.open(encoding='utf-8'))
manifest['asset_counts'].pop('ROAD_TRAFFIC',None);manifest['asset_counts']['ROAD_TRAFFIC_BLOCK']=len(assets);manifest['bytes']=sum((root/name).stat().st_size for name in manifest['checksums']);(root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('FULL_ROAD_COVERAGE',total,'bytes',manifest['bytes'],flush=True)
