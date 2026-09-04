"""GTFS timetable playback on imported track shapes; no live-vehicle claims."""
from datetime import datetime,timezone,date
from threading import RLock
from time import monotonic
from uuid import uuid5,NAMESPACE_URL
from bisect import bisect_right
from metro_turnbacks import turnback_snapshot
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from database import supabase
RUN_ID=str(uuid5(NAMESPACE_URL,'aegisgrid:gtfs:schedule-playback-v1'))
SOURCE_ID=str(uuid5(NAMESPACE_URL,'aegisgrid:gtfs:source-20260902'))
router=APIRouter(prefix='/metro',tags=['Metro command'])
lock=RLock();_feed=None;_feed_at=0

def now():return datetime.now(timezone.utc).timestamp()
def feed():
 global _feed,_feed_at
 with lock:
  if _feed is None or monotonic()-_feed_at>300:
   value=supabase.table('data_sources').select('metadata').eq('id',SOURCE_ID).single().execute().data['metadata']
   for shape in value['shapes'].values():
    if any(a[2]>b[2] for a,b in zip(shape,shape[1:])):raise RuntimeError('Non-monotonic shape distances')
   _feed=value;_feed_at=monotonic()
  return _feed

def active_services(data,service_date):
 from metro_network import services_on
 return services_on(data,service_date)

def point_at(shape,distance):
 i=max(0,min(len(shape)-2,bisect_right([p[2] for p in shape],distance)-1))
 a,b=shape[i],shape[i+1];fraction=max(0,min(1,(distance-a[2])/max(.001,b[2]-a[2])))
 return [a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction]

def train_position(trip,seconds,data):
 times=trip['times']
 if not times or seconds<times[0][1] or seconds>=times[-1][2]:return None
 for i,stop in enumerate(times):
  next_stop=times[min(i+1,len(times)-1)]
  if stop[1]<=seconds<stop[2]:
   distance=stop[3];status='DWELLING';remaining=stop[2]-seconds;progress=0
  elif i<len(times)-1 and stop[2]<=seconds<next_stop[1]:
   progress=(seconds-stop[2])/max(1,next_stop[1]-stop[2]);distance=stop[3]+(next_stop[3]-stop[3])*progress;status='IN_TRANSIT';remaining=next_stop[1]-seconds
  else:continue
  return dict(id=trip['id'],block=trip['block'],line_id=trip['route'],headsign=trip['headsign'],status=status,from_station=data['stops'][stop[0]]['name'],to_station=data['stops'][next_stop[0]]['name'],position=point_at(data['shapes'][trip['shape']],distance),progress=round(progress,4),seconds_to_next=round(remaining,1),provenance='DERIVED_SCHEDULE',shape_id=trip['shape'],schedule=[dict(station=data['stops'][item[0]]['name'],arrival=item[1],departure=item[2]) for item in times])
 return None

def advance(state,clock):
 state=dict(state)
 if state['running']:state['sim_seconds']=min(108000,state['sim_seconds']+max(0,clock-state['last_clock'])*state['speed'])
 if state['sim_seconds']>=108000:state['running']=False
 state['last_clock']=clock
 return state
class Control(BaseModel):
 action:str=Field(pattern='^(PLAY|PAUSE|RESET|SPEED|SET_TIME)$')
 speed:int=Field(default=1,ge=1,le=10)
 service_date:date|None=None
 seconds:int|None=Field(default=None,ge=0,le=107999)

def read(action=None):
 with lock:
  data=feed()
  import scenario_runtime as shared
  snapshot=shared.snapshot()
  if action is not None:
   if action.action not in ('PLAY','PAUSE','SPEED'):raise ValueError('Use the central shared scenario controls; rewinding would invalidate passenger and rainfall history')
   shared.commit(shared.Command(action=action.action,request_id=str(__import__('uuid').uuid4()),speed=action.speed))
  runtime=shared.current['state'];row={'version':shared.current['version']}
  if 'metro_v3' in runtime:
   from metro_projection import view
   return dict(**view(runtime),version=row['version'])
  state=dict(running=runtime['running'],speed=runtime['speed'],sim_seconds=runtime['start_seconds']+runtime['seconds'],service_date=runtime['service_date'],last_clock=runtime['last_wall'])
  services=active_services(data,state['service_date'])
  trains=[t for trip in data['trips'] if trip['service'] in services for t in [train_position(trip,state['sim_seconds'],data)] if t]
  seconds=int(state['sim_seconds']);clock=f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'
  return dict(**turnback_snapshot(data,services,state['sim_seconds']),trains=trains,state=state,clock=clock,version=row['version'],source=data['source_file'],service_ids=sorted(services),station_count=sum(s['type']=='1' for s in data['stops'].values()),trip_count=len(data['trips']),note='Positions interpolated along GTFS shapes using scheduled arrival/departure times. Shared scenario clock; not live GPS. Passenger counts are generated from stored demand profiles.',provenance='DERIVED_SCHEDULE')
@router.get('/snapshot')
def snapshot():
 try:return read()
 except Exception:raise HTTPException(503,'Metro database or imported GTFS unavailable')
@router.get('/network')
def network():
 try:
  data=feed();routes={r['route_id']:r for r in data['routes']};shape_routes={t['shape']:t['route'] for t in data['trips']}
  features=[dict(type='Feature',geometry=dict(type='LineString',coordinates=[p[:2] for p in points]),properties=dict(id=id,line_id=shape_routes[id],color='#'+routes[shape_routes[id]]['route_color'],provenance='GTFS_SOURCE')) for id,points in data['shapes'].items()]
  line_stations={}
  for route_id in routes:
   trip=max((t for t in data['trips'] if t['route']==route_id and t['shape'].endswith('1')),key=lambda t:len(t['times']))
   line_stations[route_id]=[dict(id=data['stops'][stop[0]]['parent'] or stop[0],name=data['stops'][stop[0]]['name']) for stop in trip['times']]
  return dict(line_stations=line_stations,routes=data['routes'],stations=[s for s in data['stops'].values() if s['type']=='1'],tracks=dict(type='FeatureCollection',features=features),source=data['source_file'],checksum=data['checksum'])
 except Exception:raise HTTPException(503,'Metro network unavailable')
@router.post('/simulation')
def control(action:Control):
 import scenario_runtime as shared
 try:return read(action)
 except ValueError as error:raise HTTPException(422,str(error))
 except shared.ScenarioConflict:raise HTTPException(409, 'Scenario was updated concurrently. Please retry.')
 except Exception:raise HTTPException(503,'Metro control update failed')



def station_operations(data, state):
 """Scheduled supply only; GTFS does not measure passenger demand."""
 services=active_services(data,state['service_date']);seconds=state['sim_seconds'];arrivals={}
 for trip in data['trips']:
  if trip['service'] not in services:continue
  for stop in trip['times']:
   if stop[1]<seconds or stop[1]>seconds+3600:continue
   station=data['stops'][stop[0]];station_id=station['parent'] or stop[0]
   key=(station_id,trip['route'],trip['headsign'])
   arrivals.setdefault(key,[]).append(dict(trip_id=trip['id'],arrival_seconds=stop[1],departure_seconds=stop[2]))
 stations=[]
 for station_id,station in data['stops'].items():
  if station['type']!='1':continue
  services_at_station=[]
  for (sid,line,headsign),upcoming in arrivals.items():
   if sid!=station_id:continue
   upcoming=sorted(upcoming,key=lambda a:a['arrival_seconds'])
   services_at_station.append(dict(line=line,towards=headsign,next_arrival_seconds=upcoming[0]['arrival_seconds'],wait_seconds=round(upcoming[0]['arrival_seconds']-seconds),scheduled_gap_seconds=upcoming[1]['arrival_seconds']-upcoming[0]['arrival_seconds'] if len(upcoming)>1 else None))
  stations.append(dict(id=station_id,name=station['name'],waiting_passengers=None,occupancy_percent=None,passenger_status='UNAVAILABLE',services=services_at_station))
 return dict(stations=sorted(stations,key=lambda s:s['name']),provenance='GTFS_SCHEDULE',clock_seconds=seconds,agent=dict(status='WAITING_FOR_DATA',mode='ADVISORY',pending_decisions=[],reason='Passenger counts, platform capacities, train capacity and operational availability are not connected. Demand-based dispatch decisions cannot be evaluated.',required_inputs=['Timestamped station passenger counts','Platform and train capacities','Available trains and crews','Minimum headways and turnback constraints'],schedule_changes_enabled=False))

@router.get('/station-operations')
def station_operations_endpoint():
 try:
  current=read()
  import scenario_runtime as runtime
  if 'metro_v3' in runtime.current['state']:
   from metro_operations import snapshot as operations_snapshot
   return operations_snapshot()
  result=station_operations(feed(),current['state'])
  import scenario_runtime as shared
  for station in result['stations']:
   q=shared.current['state'].get('queues',{}).get(station['id'],{})
   station.update(waiting_passengers=q.get('waiting',0),passenger_status='SIMULATED',boarded=q.get('boarded',0),arrived=q.get('arrived',0))
  result['agent'].update(status='MONITORING',reason='Reading the shared scenario clock and generated passenger queues. Automatic train dispatch is not enabled; the timetable remains authoritative for train movement.',required_inputs=[])
  return result
 except Exception:raise HTTPException(503,'Metro station operations unavailable')
