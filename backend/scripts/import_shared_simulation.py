"""Import only verified seed files to the explicitly configured new project.
Run after CREATE_TABLES.sql. Existing rows are preserved, never reset.
"""
import hashlib,json,sys
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

def main():
 config=dotenv_values(Path(__file__).resolve().parents[1]/'.env.simulation')
 root=Path(config['SIMULATION_DATA_DIR']);manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
 url=config['SIMULATION_SUPABASE_URL'];key=config['SIMULATION_SUPABASE_SERVICE_ROLE_KEY']
 original=dotenv_values(Path(__file__).resolve().parents[1]/'.env').get('SUPABASE_URL','')
 if url.rstrip('/')==original.rstrip('/'):raise RuntimeError('Refusing to import into the existing operational project')
 tables=['aegis_sim_runs','aegis_sim_assets','aegis_sim_profiles','aegis_sim_state','aegis_sim_events'];data={}
 for table in tables:
  path=root/(table+'.jsonl')
  if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['checksums'][path.name]:raise RuntimeError('Dataset checksum mismatch: '+table)
  data[table]=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
 db=create_client(url,key)
 # Preflight every table before any writes.
 for table in tables:db.table(table).select('id').limit(1).execute()
 run=data[tables[0]][0];existing=db.table(tables[0]).select('version,status').eq('id',run['id']).execute().data
 if existing and (existing[0]['version']!=0 or existing[0]['status'] not in ['IMPORTING','PAUSED']):raise RuntimeError('Run has advanced; refusing seed import')
 for table in tables:
  records=data[table]
  if table==tables[0]:records=[dict(run,status='IMPORTING')]
  # Insert-only retry semantics preserve operational state and avoid resets.
  for i in range(0,len(records),100):db.table(table).upsert(records[i:i+100],on_conflict='id',ignore_duplicates=True).execute()
  expected={r['id'] for r in records};found=set()
  for i in range(0,len(records),100):
   found.update(r['id'] for r in db.table(table).select('id').in_('id',[r['id'] for r in records[i:i+100]]).execute().data)
  if found!=expected:raise RuntimeError('Import verification failed: '+table)
  print(table,len(found),'verified',flush=True)
 db.table(tables[0]).update({'status':'PAUSED'}).eq('id',run['id']).eq('version',0).execute()
 (root/'import-result.json').write_text(json.dumps({'project_url':url,'counts':manifest['counts'],'status':'VERIFIED_PAUSED'},indent=2),encoding='utf-8')
 print('Import complete. Simulation and portals were not started or switched.')
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('Import stopped:',type(error).__name__,'— check table setup, credentials and dataset checksums. No secrets printed.');sys.exit(1)
