from seed_validation import equivalent
import json
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client
root=Path(r'D:\aegisgrid\generated\shared-v1');config=dotenv_values(Path(__file__).resolve().parents[1]/'.env.simulation');db=create_client(config['SIMULATION_SUPABASE_URL'],config['SIMULATION_SUPABASE_SERVICE_ROLE_KEY']);run=json.loads((root/'aegis_sim_runs.jsonl').read_text())['id'];current=db.table('aegis_sim_runs').select('status,version').eq('id',run).single().execute().data
assert current['status']=='PAUSED' and current['version']==0
for table,file in [('aegis_sim_assets','enrichment-assets'),('aegis_sim_state','enrichment-state'),('aegis_sim_profiles','enrichment-profiles')]:
 rows=[json.loads(l) for l in (root/(file+'.jsonl')).read_text(encoding='utf-8').splitlines()]
 for i in range(0,len(rows),50):db.table(table).upsert(rows[i:i+50],on_conflict='id',ignore_duplicates=True).execute()
 for i in range(0,len(rows),50):
  actual=db.table(table).select('*').in_('id',[r['id'] for r in rows[i:i+50]]).execute().data;lookup={r['id']:r for r in actual}
  assert all(equivalent(r,lookup.get(r['id'])) for r in rows[i:i+50])
 print(table,len(rows),'enrichment rows verified',flush=True)
old=[json.loads(l) for l in (root/'aegis_sim_profiles.jsonl').read_text(encoding='utf-8').splitlines()];ids=[r['id'] for r in old if r['kind']=='passengers_per_minute']
if ids:db.table('aegis_sim_profiles').delete().eq('kind','passengers_per_minute').in_('id',ids).execute()
print('Removed obsolete uncalibrated passenger profiles. Local manifest merge deferred until road expansion finishes.',flush=True)
