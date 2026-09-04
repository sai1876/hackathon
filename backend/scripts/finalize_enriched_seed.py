import hashlib,json
from collections import Counter
from pathlib import Path
root=Path(r'D:\aegisgrid\generated\shared-v1');manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
assert manifest.get('road_coverage')==374988,'Full road replacement must finish before merging'
for table,extra in [('aegis_sim_assets','enrichment-assets'),('aegis_sim_state','enrichment-state'),('aegis_sim_profiles','enrichment-profiles')]:
 path=root/(table+'.jsonl');data={r['id']:r for r in map(json.loads,path.read_text(encoding='utf-8').splitlines())}
 if table=='aegis_sim_profiles':data={key:r for key,r in data.items() if r['kind']!='passengers_per_minute'}
 data.update({r['id']:r for r in map(json.loads,(root/(extra+'.jsonl')).read_text(encoding='utf-8').splitlines())})
 path.write_text(''.join(json.dumps(r,separators=(',',':'),ensure_ascii=False)+'\n' for r in data.values()),encoding='utf-8');manifest['counts'][table]=len(data);manifest['checksums'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
 if table=='aegis_sim_assets':manifest['asset_counts']=dict(Counter(r['kind'] for r in data.values()))
manifest['bytes']=sum((root/name).stat().st_size for name in manifest['checksums']);manifest['enrichment']=json.loads((root/'enrichment-report.json').read_text(encoding='utf-8'));manifest['limitations']=[line for line in manifest['limitations'] if '5,000-road sample' not in line];manifest['limitations'].append('Full road traffic state is stored in compact blocks; traffic measurements are simulated, not Google observations.')
(root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps({'counts':manifest['counts'],'road_coverage':manifest['road_coverage'],'bytes':manifest['bytes']},indent=2))
