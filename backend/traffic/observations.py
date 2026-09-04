"""Only fresh, non-simulation measured traffic affects operational routing."""
from datetime import datetime,timedelta,timezone
from threading import RLock
from time import monotonic
from database import supabase
_cache={};_at=0;_lock=RLock();_status='UNAVAILABLE'
def current():
 global _cache,_at,_status
 with _lock:
  if monotonic()-_at<15:return _cache,_status
  try:
   cutoff=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat();records=[]
   for offset in range(0,10000,1000):
    batch=supabase.table('traffic_state').select('road_segments(external_id),avg_speed_kmph,blocked,observed_at,capacity_percent').is_('simulation_id','null').eq('provenance','REAL').gte('observed_at',cutoff).order('road_segment_id').range(offset,offset+999).execute().data
    records.extend(batch)
    if len(batch)<1000:break
   _cache={r['road_segments']['external_id']:r for r in records if r.get('road_segments')};_status='FRESH_OBSERVATIONS' if records else 'NO_FRESH_OBSERVATIONS'
  except Exception:_cache={};_status='UNAVAILABLE'
  _at=monotonic();return _cache,_status

def apply(graph):
 records,status=current()
 for _,_,_,edge in graph.edges(keys=True,data=True):
  row=records.get(edge.get('external_id'))
  if row:
   edge.update(traffic_speed_kph=row['avg_speed_kmph'],blocked=row['blocked'],traffic_provenance='REAL',traffic_observed_at=row['observed_at'])
 return status
