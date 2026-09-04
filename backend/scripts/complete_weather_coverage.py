import hashlib,json,math
from collections import defaultdict
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from dotenv import dotenv_values
from supabase import create_client
root=Path(r'D:\aegisgrid\generated\shared-v1');manifest=json.loads((root/'manifest.json').read_text());assert manifest.get('road_coverage')==374988
seed=20260904;uid=lambda key:str(uuid5(NAMESPACE_URL,f'aegisgrid:shared:v1:{seed}:{key}'));run=json.loads((root/'aegis_sim_runs.jsonl').read_text())['id'];rows=[json.loads(l) for l in (root/'road-block-assets.jsonl').read_text().splitlines()];groups=defaultdict(list)
for row in rows:
 if row['zone_id']=='OUTSIDE_WEATHER_GRID':groups[(math.floor((row['longitude']-78.25)/(.4/6)),math.floor((row['latitude']-17.25)/(.35/4)))].append(row)
a=[];s=[];profiles=[]
for (col,row),blocks in groups.items():
 x=78.25+col*.4/6;y=17.25+row*.35/4;zone=f'Z-{col}-{row}';id=uid(f'zone:{col}:{row}')
 def asset(key,kind,name,parent,**spec):
  item=dict(id=uid(key),kind=kind,name=name,longitude=x+.4/12,latitude=y+.35/8,parent_id=parent,zone_id=zone,provenance='SIMULATED',spec=spec);a.append(item);return item
 area=asset(f'zone:{col}:{row}','WEATHER_AREA','Simulation area '+zone,None,polygon=[[x,y],[x+.4/6,y],[x+.4/6,y+.35/4],[x,y+.35/4],[x,y]],drainage_mm_hour=15,rainfall_traffic_sensitivity=.6,mode_shift_max_fraction=.3,assumption_status='UNCALIBRATED')
 water=asset(id+':water','WATERLOGGING_POINT',zone+' modelled drainage point',id,drainage_mm_hour=15,road_block_threshold_mm=150)
 for item,values in [(area,dict(rainfall_mm_hour=0,water_depth_mm=0,road_capacity_factor=1,metro_demand_factor=1,electric_load_factor=1)),(water,dict(depth_mm=0,blocked=False))]:s.append(dict(id=uid('state:'+item['id']),run_id=run,asset_id=item['id'],version=0,sim_seconds=0,provenance='SIMULATED',values=values))
 for domain in ['TRAFFIC','METRO','ELECTRIC']:
  rule=asset('weather-link:'+id+domain,'CROSS_DOMAIN_RULE',zone+' affects '+domain,id,source_asset_id=id,target_asset_id=None,domain=domain,shared_zone_id=zone,requires_same_event_id=True,mode='SIMULATION_ASSUMPTION');s.append(dict(id=uid('state:'+rule['id']),run_id=run,asset_id=rule['id'],version=0,sim_seconds=0,provenance='SIMULATED',values={'enabled':True}))
 profiles.append(dict(id=uid('electric-demand:'+id),asset_id=id,kind='electric_load_factor',interval_seconds=900,provenance='SIMULATED_UNCALIBRATED',values=[round(.55+.22*math.exp(-((i/4-10)/3)**2)+.4*math.exp(-((i/4-19)/2.8)**2),4) for i in range(96)]))
 for block in blocks:block['zone_id']=zone
c=dotenv_values(Path(__file__).resolve().parents[1]/'.env.simulation');db=create_client(c['SIMULATION_SUPABASE_URL'],c['SIMULATION_SUPABASE_SERVICE_ROLE_KEY']);current=db.table('aegis_sim_runs').select('status,version').eq('id',run).single().execute().data;assert current['status']=='PAUSED' and current['version']==0
for table,extra,data in [('aegis_sim_assets','enrichment-assets',a),('aegis_sim_state','enrichment-state',s),('aegis_sim_profiles','enrichment-profiles',profiles)]:
 if data:db.table(table).upsert(data,on_conflict='id',ignore_duplicates=True).execute()
 path=root/(extra+'.jsonl');existing={r['id']:r for r in map(json.loads,path.read_text(encoding='utf-8').splitlines())};existing.update({r['id']:r for r in data});path.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in existing.values()),encoding='utf-8')
for blocks in groups.values():db.table('aegis_sim_assets').update({'zone_id':blocks[0]['zone_id']}).in_('id',[b['id'] for b in blocks]).execute()
for filename in ['road-block-assets.jsonl','aegis_sim_assets.jsonl']:
 path=root/filename;data=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()];zones={b['id']:b['zone_id'] for blocks in groups.values() for b in blocks}
 for r in data:
  if r['id'] in zones:r['zone_id']=zones[r['id']]
 path.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
print('Extended weather coverage:',len(groups),'cells;',sum(len(b) for b in groups.values()),'road blocks reassigned.')
