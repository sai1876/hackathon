"""Import supplied GTFS schedules and shapes; never label playback as live GPS."""
import sys,csv,io,json,zipfile,hashlib,time
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import supabase
path=Path(r'D:\download chrome\data\Telangana_opendata_gtfs_hmrl_02_September_2026.zip')
uid=lambda key:str(uuid5(NAMESPACE_URL,'aegisgrid:gtfs:'+key))
def seconds(value):
 h,m,s=map(int,value.split(':'));return h*3600+m*60+s
with zipfile.ZipFile(path) as z:
 read=lambda n:list(csv.DictReader(io.StringIO(z.read(n+'.txt').decode('utf-8-sig'))))
 stops=read('stops');routes=read('routes');trips=read('trips');times=read('stop_times');shapes=read('shapes');calendar=read('calendar')
 calendar_dates=read('calendar_dates') if 'calendar_dates.txt' in z.namelist() else []
 parents={r['stop_id']:r for r in stops if r['location_type']=='1'}
 stop_lookup={r['stop_id']:r for r in stops}
 shape_data={}
 for r in sorted(shapes,key=lambda r:(r['shape_id'],int(r['shape_pt_sequence']))):shape_data.setdefault(r['shape_id'],[]).append([float(r['shape_pt_lon']),float(r['shape_pt_lat']),float(r['shape_dist_traveled'])])
 timing={}
 for r in sorted(times,key=lambda r:(r['trip_id'],int(r['stop_sequence']))):
  assert r['stop_id'] in stop_lookup
  timing.setdefault(r['trip_id'],[]).append([r['stop_id'],seconds(r['arrival_time']),seconds(r['departure_time']),float(r['shape_dist_traveled'])])
 normalized=[]
 for trip in trips:
  t=timing[trip['trip_id']]
  assert trip['shape_id'] in shape_data and all(a[2]<=b[1] for a,b in zip(t,t[1:]))
  normalized.append(dict(id=trip['trip_id'],route=trip['route_id'],service=trip['service_id'],shape=trip['shape_id'],headsign=trip['trip_headsign'],block=trip['block_id'],times=t))
 metadata=dict(calendar_dates=calendar_dates,stops={r['stop_id']:{'id':r['stop_id'],'name':r['stop_name'],'lat':float(r['stop_lat']),'lon':float(r['stop_lon']),'parent':r['parent_station'],'type':r['location_type']} for r in stops},routes=routes,trips=normalized,shapes=shape_data,calendar=calendar,checksum=hashlib.sha256(path.read_bytes()).hexdigest(),source_file=path.name,note='Static GTFS schedules and shapes. Interpolated train positions are DERIVED, not live telemetry.')
 source_id=uid('source-20260902')
 for r in routes:supabase.table('metro_lines').upsert(dict(id=uid('line:'+r['route_id']),gtfs_route_id=r['route_id'],name=r['route_long_name'],line_code=r['route_id'],provenance='REAL',metadata={'source_id':source_id,'color':r['route_color']})).execute()
 for group in [list(parents.values()),[r for r in stops if r['location_type']!='1']]:
  rows=[dict(id=uid('stop:'+r['stop_id']),gtfs_stop_id=r['stop_id'],name=r['stop_name'],location=f"SRID=4326;POINT({r['stop_lon']} {r['stop_lat']})",parent_station_id=uid('stop:'+r['parent_station']) if r['parent_station'] else None,is_platform=r['location_type']=='0',provenance='REAL',metadata={'source_id':source_id,'location_type':r['location_type'],'platform_code':r.get('platform_code')}) for r in group]
  for i in range(0,len(rows),100):supabase.table('metro_stations').upsert(rows[i:i+100]).execute()
 trip_rows=[dict(id=uid('trip:'+r['trip_id']),gtfs_trip_id=r['trip_id'],line_id=uid('line:'+r['route_id']),service_id=r['service_id'],direction=int(r['direction_id']),provenance='REAL') for r in trips]
 for i in range(0,len(trip_rows),200):supabase.table('metro_trips').upsert(trip_rows[i:i+200]).execute()
 supabase.table('data_sources').upsert(dict(id=source_id,source_name='Telangana HMRL GTFS 02 September 2026',source_type='GTFS',provenance='REAL',provider='User supplied Open Data Telangana feed',metadata=metadata)).execute()
 run_id=uid('schedule-playback-v1')
 if not supabase.table('simulation_runs').select('id').eq('id',run_id).execute().data:
  supabase.table('simulation_runs').insert(dict(id=run_id,name='GTFS metro schedule playback',scenario_type='METRO_GTFS_DERIVED',status='PAUSED',configuration={'version':0,'source_id':source_id,'state':{'running':False,'speed':1,'sim_seconds':28800,'service_date':'2026-09-03','last_clock':time.time()}})).execute()
 print(json.dumps({'parent_stations':len(parents),'stop_records':len(stops),'routes':len(routes),'trips':len(trips),'stop_times':len(times),'shape_points':len(shapes),'shapes':len(shape_data),'checksum':metadata['checksum']}))
