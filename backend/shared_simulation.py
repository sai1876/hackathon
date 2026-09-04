"""Read the new project's seed inventory without mixing it with observed measurements."""
from collections import Counter
from pathlib import Path
from threading import Lock
from time import monotonic
from dotenv import dotenv_values
from supabase import create_client
_cache=None
_at=0
_lock=Lock()

def inventory():
 global _cache,_at
 with _lock:
  if _cache is not None and monotonic()-_at<60:return _cache
  try:
   c=dotenv_values(Path(__file__).with_name('.env.simulation'))
   db=create_client(c['SIMULATION_SUPABASE_URL'],c['SIMULATION_SUPABASE_SERVICE_ROLE_KEY'])
   counts={}
   for table in ['aegis_sim_assets','aegis_sim_state','aegis_sim_profiles','aegis_sim_events','aegis_sim_runs']:
    counts[table]=db.table(table).select('id',count='exact').limit(1).execute().count
   kinds=Counter()
   for offset in range(0,counts['aegis_sim_assets'],1000):
    kinds.update(row['kind'] for row in db.table('aegis_sim_assets').select('kind').order('id').range(offset,offset+999).execute().data)
   road_coverage=0
   for offset in range(0,kinds.get('ROAD_TRAFFIC_BLOCK',0),1000):
    road_coverage+=sum(row.get('road_count',0) for row in db.table('aegis_sim_assets').select('spec->road_count').eq('kind','ROAD_TRAFFIC_BLOCK').order('id').range(offset,offset+999).execute().data)
   runs=db.table('aegis_sim_runs').select('name,status,sim_seconds,version').execute().data
   _cache=dict(status='AVAILABLE',source='New simulation Supabase project',provenance='SIMULATED_SEED',tables=counts,kinds=dict(kinds),road_coverage=road_coverage,runs=runs,note='Persisted simulation starting conditions. Live scenario state and clock are committed together in aegis_sim_runs; scenario events are archived in aegis_sim_events. Seed asset-state rows are not live telemetry.')
   _at=monotonic();return _cache
  except Exception:return dict(status='UNAVAILABLE',note='New simulation database inventory could not be read.')
