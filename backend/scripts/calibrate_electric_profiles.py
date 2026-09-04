import csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
from uuid import uuid5,NAMESPACE_URL
root=Path(r'D:\aegisgrid\generated\shared-v1');source=Path(r'D:\download chrome\data\consumption_detail_06_2021.csv');circles={'BANJARA HILLS','CYBERCITY','HABSIGUDA','HYDERABAD CENTRAL','HYDERABAD SOUTH','MEDCHAL','RAJENDRA NAGAR','SAROORNAGAR','SECUNDERABAD'};totals=defaultdict(float);count=0;excluded=0
with source.open(encoding='utf-8-sig') as f:
 for row in csv.DictReader(f):
  if row['circle'] not in circles:continue
  try:value=float(row['units'])
  except ValueError:excluded+=1;continue
  if not math.isfinite(value) or value<0:excluded+=1;continue
  totals[row['catdesc']]+=value;count+=1
shares={category:value/sum(totals.values()) for category,value in totals.items()};curve=[]
for i in range(96):
 hour=i/4;value=0
 for category,share in shares.items():
  if category=='DOMESTIC':shape=.45+.5*math.exp(-((hour-8)/2)**2)+.9*math.exp(-((hour-20)/2.5)**2)
  elif 'COMMERCIAL' in category:shape=.3+.8*math.exp(-((hour-14)/5)**2)
  elif 'STREETLIGHT' in category:shape=1.0 if hour<6 or hour>=18 else .35
  elif 'INDUSTRIAL' in category:shape=.8+.2*math.exp(-((hour-13)/5)**2)
  else:shape=.6+.35*math.exp(-((hour-14)/5)**2)
  value+=share*shape
 curve.append(value)
mean=sum(curve)/96;curve=[round(v/mean,5) for v in curve]
report=dict(source_file=source.name,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),selected_circles=sorted(circles),source_rows=count,excluded_rows=excluded,category_shares=shares,method='Monthly units determine relative category weights only. Daily timing curves are simulation assumptions; units are not converted into instantaneous power.',provenance='SIMULATED_HISTORICALLY_WEIGHTED',reference_period='2021-06')
(root/'electric-demand-calibration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
path=root/'enrichment-profiles.jsonl';profiles=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
for profile in profiles:
 if profile['kind']=='electric_load_factor':profile.update(values=curve,provenance='SIMULATED_HISTORICALLY_WEIGHTED')
path.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in profiles),encoding='utf-8')
c=dotenv_values(Path(__file__).resolve().parents[1]/'.env.simulation');db=create_client(c['SIMULATION_SUPABASE_URL'],c['SIMULATION_SUPABASE_SERVICE_ROLE_KEY']);run=json.loads((root/'aegis_sim_runs.jsonl').read_text())['id'];current=db.table('aegis_sim_runs').select('status,version').eq('id',run).single().execute().data;assert current['status']=='PAUSED' and current['version']==0
changed=db.table('aegis_sim_profiles').update({'values':curve,'provenance':'SIMULATED_HISTORICALLY_WEIGHTED'}).eq('kind','electric_load_factor').execute().data
assert all(r['values']==curve for r in changed)
uid=lambda key:str(uuid5(NAMESPACE_URL,f'aegisgrid:shared:v1:20260904:{key}'));id=uid('electric-demand-model');asset=dict(id=id,kind='ELECTRIC_DEMAND_MODEL',name='Historical electricity category mix',longitude=78.45,latitude=17.425,parent_id=None,zone_id='CITY',provenance='SIMULATED_HISTORICALLY_WEIGHTED',spec=report);state=dict(id=uid('state:'+id),run_id=run,asset_id=id,version=0,sim_seconds=0,provenance='SIMULATED',values={'enabled':True})
for table,name,row in [('aegis_sim_assets','enrichment-assets',asset),('aegis_sim_state','enrichment-state',state)]:
 db.table(table).upsert(row,on_conflict='id',ignore_duplicates=True).execute();p=root/(name+'.jsonl');rows={r['id']:r for r in map(json.loads,p.read_text(encoding='utf-8').splitlines())};rows[row['id']]=row;p.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in rows.values()),encoding='utf-8')
print('Electric profiles updated:',len(changed),'historical rows:',count,'excluded:',excluded,flush=True)
