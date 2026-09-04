"""Database-backed scenario controls. One versioned row is the live-state authority.
Seed state tables are immutable starting conditions, never presented as live telemetry.
"""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import RLock, Event, Thread
from time import time, sleep
import random
from uuid import uuid4, uuid5, NAMESPACE_URL
from collections import Counter
import logging

import json
from dotenv import dotenv_values
from supabase import create_client
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon, Point, box

router=APIRouter(prefix='/command/scenario', tags=['Shared simulation'])
RUN_ID=str(uuid5(NAMESPACE_URL,'aegisgrid:shared:v1:20260904:baseline'))
ROOT_RUN_ID=RUN_ID
lock=RLock(); stop=Event(); db=None; assets=[]; profiles=[]; current=None; checked=0; failure='Loading shared database'; seed_loads={}; timetable=None; routing_signature=None; public_cache=None; public_version=-1
_worker_thread = None
_worker_started = False

class ScenarioError(Exception):
    """Base exception for scenario runtime errors."""
    pass

class ScenarioConflict(ScenarioError):
    """Optimistic write revision mismatch. An expected concurrency race."""
    def __init__(self, message: str, run_id: str | None = None, expected_version: int | None = None, actual_version: int | None = None):
        super().__init__(message)
        self.run_id = run_id
        self.expected_version = expected_version
        self.actual_version = actual_version

class PersistenceContention(ScenarioError):
    """Temporary database busy, lock conflict, or contention error."""
    pass

class TransientPersistenceFailure(ScenarioError):
    """Transient network timeout, connection reset, or temporary HTTP 5xx."""
    pass

class DatabaseUnavailable(ScenarioError):
    """Persistent dependency, authentication, schema, or initialization failure."""
    pass


class Command(BaseModel):
 action: str=Field(pattern='^(PLAY|PAUSE|SPEED|SERVICE_START|SET_TIME|RAIN|FLOOD|ELECTRIC|TRAFFIC|METRO|SIGNAL|END|REMOVE|APPROVE|REJECT)$')
 request_id: str=Field(min_length=8,max_length=80)
 speed: int=Field(default=1,ge=1,le=60)
 polygon: list[list[float]]=Field(default_factory=list,max_length=100)
 intensity: float=Field(default=60,ge=0,le=300)
 duration_minutes: float=Field(default=60,gt=0,le=1440)
 multiplier: float=Field(default=1.5,ge=.1,le=4)
 station_ids: list[str]=Field(default_factory=list,max_length=100)
 target_id: str|None=None
 seconds: int|None=Field(default=None,ge=0,le=107999)


def rows(table):
 result=[]
 for offset in range(0,100000,1000):
  batch=db.table(table).select('*').order('id').range(offset,offset+999).execute().data
  result.extend(batch)
  if len(batch)<1000:return result
 raise RuntimeError('Database paging limit')


def validate_polygon(points):
 if len(points)<3 or any(len(p)!=2 or not(78.05<=p[0]<=78.95 and 17.05<=p[1]<=17.85) for p in points):
  raise ValueError('Draw at least three points inside Hyderabad')
 poly=Polygon(points)
 if not poly.is_valid or poly.area<.000001 or poly.area>.12:raise ValueError('Choose a non-crossing area between a small junction and a city district')
 return poly


def event(s,kind,payload,parent=None):
 e=dict(id=str(uuid4()),run_id=RUN_ID,sim_seconds=s['seconds'],kind=kind,zone_id=None,parent_event_id=parent,provenance='SIMULATED',payload=payload)
 s['events'].append(e);s['outbox'].append(e)
 s['events']=s['events'][-100:]
 return e['id']


def initial(row):
 return dict(seconds=float(row['sim_seconds']),running=False,speed=1,last_wall=time(),scenarios=[],events=[],outbox=[],requests=[],recommendations=[],service_date=row['configuration'].get('service_date','2026-09-03'),start_seconds=18000,assumptions=dict(block_depth_mm=150,pumping_max_load_fraction=.15,drainage_dispatch_multiplier=2,model_version='shared-runtime-v1'))


def advance(s, wall, simulation_delta=None):
 # No unseen catch-up through a long backend outage. The committed clock resumes.
 dt=(min(10,max(0,wall-s['last_wall']))*s['speed'] if s['running'] else 0) if simulation_delta is None else max(0,simulation_delta)
 s['last_wall']=wall
 for a in assets:
  if a['kind']=='TRAFFIC_SIGNAL':signal_plan(s,a)
 old_seconds=s['seconds']
 horizon=s.get('metro_v3',{}).get('plan',{}).get('last_seconds',86400)
 remaining=min(dt,max(0,horizon-s['start_seconds']-s['seconds']))
 while remaining>0:
  step=min(1,remaining);before=s['seconds'];s['seconds']+=step;remaining-=step
  for z in s['scenarios']:
   z.setdefault('response_model',dict(cooling_relief_max=.04,cooling_relief_per_mm_h=.0004,modal_shift_max=.3,model_version='rain-response-v2'))
   rain_seconds=max(0,min(s['seconds'],z['end'])-max(before,z['start']))
   rain=z['intensity'] if z['kind']=='RAIN' else 0
   drainage=z['drainage']*(s['assumptions']['drainage_dispatch_multiplier'] if z.get('drainage_approved') else 1)
   z['water_mm']=max(0,z['water_mm']+(rain*rain_seconds-drainage*step)/3600)
   old=z.get('blocked',False);z['blocked']=z['water_mm']>=s['assumptions']['block_depth_mm']
   if z['blocked']!=old:event(s,'ROAD_CLOSURE' if z['blocked'] else 'ROAD_REOPENED',dict(scenario_id=z['id'],water_depth_mm=round(z['water_mm'],2)),z['event_id'])
   if before<z['end']<=s['seconds']:event(s,'INPUT_ENDED',dict(scenario_id=z['id']),z['event_id'])
   if z['water_mm']>=30 and not z.get('recommended'):
    z['recommended']=True;r=dict(id=str(uuid4()),scenario_id=z['id'],status='PENDING',domain='TRAFFIC / ELECTRIC',action='Dispatch drainage pumps',reason='Accumulated water exceeds 30 mm; approval doubles modelled drainage and adds pumping demand.',event_id=z['event_id'])
    s['recommendations'].append(r);event(s,'RECOMMENDATION_CREATED',r,z['event_id'])
  from emergency_model import tick as emergency_tick
  emergency_tick(s,step)
  if 'metro_v3' in s:
   import metro_simulation
   metro_simulation.tick(s,step)
 if 'metro_v3' in s:
  import metro_simulation
  metro_simulation.sync_totals(s)
 elif s['seconds']>old_seconds:passengers(s,old_seconds,s['seconds'])
 if s['seconds']+s['start_seconds']>=horizon:s['running']=False
 return s


def signal_plan(s,asset):
 # A generated timing plan is committed once, never randomly redrawn by a browser.
 from hashlib import sha256
 key=asset['id'];plans=s.setdefault('signal_plans',{})
 if key not in plans:
  seed=int(sha256(key.encode()).hexdigest()[:8],16)
  plans[key]=dict(cycle_seconds=90,offset_seconds=seed%90,green_seconds=39,amber_seconds=3,all_red_seconds=3,provenance='GENERATED_TIMING_PLAN')
 return plans[key]

def effect(z, seconds):
 active=z['start']<=seconds<z['end']
 rain=z['intensity'] if active and z['kind']=='RAIN' else 0
 model=z.get('response_model',dict(cooling_relief_max=.04,cooling_relief_per_mm_h=.0004,modal_shift_max=.3))
 traffic=1/max(.1,z['multiplier']) if active and z['kind']=='TRAFFIC' else 1/(1+rain/100+z['water_mm']/50)
 electric=z['multiplier'] if active and z['kind']=='ELECTRIC' else 1-min(model['cooling_relief_max'],rain*model['cooling_relief_per_mm_h'])
 metro=z['multiplier'] if active and z['kind']=='METRO' else 1+min(model['modal_shift_max'],(1-traffic)*.3)
 return dict(rain_mm_hour=rain,water_mm=z['water_mm'],blocked=z.get('blocked',False),traffic_factor=traffic,electric_factor=electric,metro_factor=metro,signal_failed=active and z['kind']=='SIGNAL')


def act(s,c):
 if c.request_id in s['requests']:return
 if c.action=='SIGNAL_CREATE':
  from signal_operations import apply as signal_apply
  signal_apply(s,c.payload)
 elif c.action=='METRO_OPERATION':
  from metro_operations import apply as metro_apply
  metro_apply(s,c.payload)
 elif c.action=='EMERGENCY':
  from emergency_model import apply as emergency_apply
  emergency_apply(s,c.payload)
 elif c.action=='PLAY':s['running']=True
 elif c.action=='PAUSE':s['running']=False
 elif c.action=='SPEED':s['speed']=c.speed
 elif c.action=='SET_TIME':
  if c.seconds is None:raise ValueError('Choose a simulation time')
  delta=c.seconds-s['start_seconds']-s['seconds']
  if delta<0:raise ValueError('Cannot rewind an active run. Choose a later time so recorded events and passengers remain consistent.')
  advance(s,time(),simulation_delta=delta);s['running']=False
 elif c.action=='SERVICE_START':
  if s['seconds'] or s['scenarios'] or s.get('queues'):raise ValueError('Service start can only be selected before this scenario has advanced')
  from metro_engine import active_services
  services=active_services(timetable,s['service_date'])
  starts=[t['times'][0][1] for t in timetable['trips'] if t['service'] in services and t['times']]
  if not starts:raise ValueError('No timetable service on this date')
  s['start_seconds']=min(starts);s['running']=True
 elif c.action in ('APPROVE','REJECT'):
  r=next((r for r in s['recommendations'] if r['id']==c.target_id),None)
  if not r or r['status']!='PENDING':raise ValueError('Recommendation is no longer pending')
  r['status']='APPROVED' if c.action=='APPROVE' else 'REJECTED'
  if c.action=='APPROVE':
   target=next(z for z in s['scenarios'] if z['id']==r['scenario_id'])
   if target['water_mm']<=.1:raise ValueError('Water has already drained; this recommendation is no longer applicable')
   target['drainage_approved']=True
 elif c.action=='METRO':
  ids=list(dict.fromkeys(c.station_ids))
  known={a['id']:a for a in assets if a['kind']=='METRO_STATION'}
  if not ids:raise ValueError('Select at least one metro station')
  if any(i not in known for i in ids):raise ValueError('A selected station is unavailable; refresh the station list')
  if len(s['scenarios'])>=50:raise ValueError('This run has reached 50 inputs; remove unused inputs first')
  z=dict(id=str(uuid4()),kind='METRO',polygon=[],station_ids=ids,station_targets=[dict(id=i,name=known[i]['name'],position=[known[i]['longitude'],known[i]['latitude']]) for i in ids],start=s['seconds'],end=s['seconds']+c.duration_minutes*60,intensity=0,multiplier=c.multiplier,water_mm=0,drainage=0,blocked=False)
  z['event_id']=event(s,'SCENARIO_INJECTED',deepcopy(z))
  s['scenarios'].append(z)
 elif c.action=='REMOVE':
  z=next((z for z in s['scenarios'] if z['id']==c.target_id),None)
  if not z:raise ValueError('Scenario not found; refresh the area list')
  # Archive the exact input and residual effects before removing its influence.
  # Historical trips, queues and actions remain causal history, not rewound state.
  event(s,'SCENARIO_REMOVED',dict(scenario=deepcopy(z),reason='Operator removed simulation area'),z.get('event_id'))
  for recommendation in s['recommendations']:
   if recommendation.get('scenario_id')==z['id'] and recommendation['status']=='PENDING':
    recommendation['status']='CANCELLED'
    event(s,'RECOMMENDATION_CANCELLED',dict(recommendation_id=recommendation['id'],scenario_id=z['id']),z.get('event_id'))
  s['scenarios']=[area for area in s['scenarios'] if area['id']!=z['id']]
 elif c.action=='END':
  z=next((z for z in s['scenarios'] if z['id']==c.target_id),None)
  if not z:raise ValueError('Scenario not found')
  z['end']=s['seconds']
 else:
  if len(s['scenarios'])>=50:raise ValueError('This run has reached 50 areas; pause before archiving this run')
  poly=validate_polygon(c.polygon)
  weather=[a for a in assets if a['kind']=='WEATHER_AREA' and poly.intersects(Polygon(a['spec']['polygon']))]
  if not weather:raise ValueError('Area is outside the imported simulation coverage')
  drainage=sum(a['spec']['drainage_mm_hour'] for a in weather)/len(weather)
  z=dict(id=str(uuid4()),kind=c.action,polygon=list(map(list,poly.exterior.coords)),start=s['seconds'],end=s['seconds']+c.duration_minutes*60,intensity=c.intensity,multiplier=c.multiplier,water_mm=c.intensity if c.action=='FLOOD' else 0,drainage=drainage,blocked=c.action=='FLOOD' and c.intensity>=s['assumptions']['block_depth_mm'])
  z['event_id']=event(s,'SCENARIO_INJECTED',dict(**z,weather_asset_ids=[a['id'] for a in weather]))
  s['scenarios'].append(z)
 event(s,'OPERATOR_'+c.action,dict(request_id=c.request_id,target_id=c.target_id,speed=s['speed']))
 s['requests']=(s['requests']+[c.request_id])[-500:]


def load_state():
    """Load latest scenario row and unpacked state from database."""
    global db, RUN_ID
    if db is None:
        raise DatabaseUnavailable('Database client is not initialized')
    try:
        row = db.table('aegis_sim_runs').select('*').eq('id', RUN_ID).single().execute().data
    except Exception as exc:
        err_msg = str(exc).lower()
        if 'timeout' in err_msg or 'reset' in err_msg or '502' in err_msg or '503' in err_msg or '504' in err_msg:
            raise TransientPersistenceFailure(f'Transient error loading state: {exc}') from exc
        raise DatabaseUnavailable(f'Database unavailable: {exc}') from exc

    if not row:
        raise DatabaseUnavailable(f'Simulation run {RUN_ID} not found')

    from metro_simulation import unpack_state
    s = unpack_state(deepcopy(row['configuration'].get('runtime') or initial(row)))
    import metro_simulation
    needs_metro = metro_simulation.network is not None and 'metro_v3' not in s
    if needs_metro:
        metro_simulation.ensure(s)
    return row, s


def flush_outbox(outbox_events, config, expected_version):
    """Independently flush outbox events to aegis_sim_events without failing state commit."""
    global db, RUN_ID
    if not outbox_events or db is None:
        return
    try:
        db.table('aegis_sim_events').upsert(outbox_events, on_conflict='id').execute()
        clean = deepcopy(config)
        clean['runtime']['outbox'] = []
        db.table('aegis_sim_runs').update(dict(configuration=clean)).eq('id', RUN_ID).eq('version', expected_version).execute()
    except Exception as exc:
        logging.warning('Scenario event archive pending; committed outbox retained: %s', exc)


def commit_revision(s, expected_version, config=None):
    """Commit one expected revision. Strictly performs an atomic conditional update.
    Never silently retries with stale mutations.
    """
    global current, checked, failure, db, RUN_ID
    from metro_simulation import pack_state

    if len(s.get('outbox', [])) > 1000:
        raise RuntimeError('Event archive unavailable; simulation paused until persistence recovers')

    if config is None:
        row = db.table('aegis_sim_runs').select('configuration').eq('id', RUN_ID).single().execute().data
        base_config = row['configuration'] if row else {}
    else:
        base_config = config

    updated_config = {
        **base_config,
        'runtime': pack_state(s),
        'runtime_authority': 'configuration.runtime; seed state tables are initial conditions'
    }

    try:
        new_version = expected_version + 1
        updated = db.table('aegis_sim_runs').update(dict(
            configuration=updated_config,
            sim_seconds=s['seconds'],
            version=new_version,
            status='RUNNING' if s['running'] else 'PAUSED'
        )).eq('id', RUN_ID).eq('version', expected_version).execute().data
    except Exception as exc:
        err_msg = str(exc).lower()
        if 'busy' in err_msg or 'lock' in err_msg:
            raise PersistenceContention(f'Database lock contention: {exc}') from exc
        if 'timeout' in err_msg or 'reset' in err_msg or '502' in err_msg or '503' in err_msg or '504' in err_msg:
            raise TransientPersistenceFailure(f'Transient network error: {exc}') from exc
        raise DatabaseUnavailable(f'Database error: {exc}') from exc

    if not updated:
        actual_version = None
        try:
            curr_row = db.table('aegis_sim_runs').select('version').eq('id', RUN_ID).single().execute().data
            if curr_row:
                actual_version = curr_row.get('version')
        except Exception:
            pass
        raise ScenarioConflict(
            f"Scenario revision conflict on run {RUN_ID} (expected {expected_version}, actual {actual_version})",
            run_id=RUN_ID,
            expected_version=expected_version,
            actual_version=actual_version
        )

    current = dict(state=s, version=new_version)
    checked = time()
    failure = ''
    publish(s)

    if s.get('outbox'):
        flush_outbox(s['outbox'], updated_config, new_version)

    return snapshot()


def apply_mutation(mutation_fn, request_id=None, max_retries=5):
    """Execute a state mutation function with clean optimistic concurrency retry semantics:
    reload fresh state -> mutate -> commit_revision -> on conflict: jittered backoff -> reload -> recalculate -> retry.

    If request_id is provided and already recorded in s['requests'], the mutation is
    treated as idempotent and the current state snapshot is returned without duplicate application.
    """
    global current, checked, failure
    import random
    from time import sleep

    with lock:
        if request_id and current and request_id in current['state'].get('requests', []):
            logging.info("Request %s already committed in scenario runtime; returning snapshot", request_id)
            return snapshot()

        for attempt in range(1, max_retries + 1):
            row, s = load_state()

            if request_id and request_id in s.get('requests', []):
                logging.info("Request %s already committed in database run (version %s); returning snapshot", request_id, row['version'])
                current = dict(state=s, version=row['version'])
                checked = time()
                failure = ''
                return snapshot()

            mutation_fn(s)

            try:
                return commit_revision(s, expected_version=row['version'], config=row['configuration'])
            except ScenarioConflict as conflict:
                if attempt < max_retries:
                    backoff = 0.025 * (2 ** (attempt - 1)) + random.uniform(0.005, 0.020)
                    logging.warning(
                        "Scenario revision conflict on run %s (expected %s, actual %s); retrying attempt %d/%d after %.3fs",
                        conflict.run_id, conflict.expected_version, conflict.actual_version, attempt, max_retries, backoff
                    )
                    sleep(backoff)
                    continue
                logging.warning(
                    "Scenario revision conflict on run %s after %d attempts; raising ScenarioConflict",
                    conflict.run_id, max_retries
                )
                raise
            except (PersistenceContention, TransientPersistenceFailure) as transient_err:
                if attempt < max_retries:
                    backoff = 0.050 * (2 ** (attempt - 1)) + random.uniform(0.010, 0.030)
                    logging.warning(
                        "Transient persistence issue on run %s (%s); retrying attempt %d/%d after %.3fs",
                        RUN_ID, type(transient_err).__name__, attempt, max_retries, backoff
                    )
                    sleep(backoff)
                    continue
                raise

        raise ScenarioConflict(f"Scenario revision conflict on run {RUN_ID} after {max_retries} attempts", run_id=RUN_ID)


def commit(command=None, max_retries=5):
    """Helper wrapping apply_mutation for backward compatibility."""
    global current, checked, failure
    req_id = getattr(command, 'request_id', None) if command else None

    if command is None:
        with lock:
            if current and not current['state']['running'] and not current['state'].get('outbox'):
                checked = time()
                return snapshot()
            try:
                row, s = load_state()
                import metro_simulation
                needs_metro = metro_simulation.network is not None and 'metro_v3' not in s
                if not needs_metro and not s['running'] and row['configuration'].get('runtime') and not s.get('outbox'):
                    current = dict(state=s, version=row['version'])
                    checked = time()
                    failure = ''
                    publish(s)
                    return snapshot()
            except Exception:
                pass

    def mutate(s):
        advance(s, time())
        if command:
            act(s, command)

    return apply_mutation(mutate, request_id=req_id, max_retries=max_retries)



def publish(s):
 global routing_signature
 import weather_effects
 from emergency_api import sync as sync_emergency
 sync_emergency(s)
 weather_effects.shared_zones=[dict(id=z['id'],polygon=z['polygon'],factor=1/max(.05,effect(z,s['seconds'])['traffic_factor']),blocked=effect(z,s['seconds'])['blocked']) for z in s['scenarios'] if len(z['polygon'])>=3 and (z['water_mm']>.1 or z['start']<=s['seconds']<z['end'])]
 signature=json.dumps([(z['id'],round(z['factor'],1),z['blocked']) for z in weather_effects.shared_zones])
 if signature!=routing_signature:
  routing_signature=signature;weather_effects.changed.set()


def station_effects(s):
 result={}
 zones=[(Polygon(z['polygon']),z,effect(z,s['seconds'])) for z in s['scenarios']]
 for a in assets:
  if a['kind']!='METRO_STATION':continue
  relevant=[(z,e) for p,z,e in zones if a['id'] in z.get('station_ids',[]) or (not z.get('station_ids') and p.covers(Point(a['longitude'],a['latitude'])))]
  factor=max([e['metro_factor'] for z,e in relevant],default=1)
  # Bounded modal-shift assumption, linked to the same rainfall event.
  shift=0 # Modal shift is already included in effect(); do not apply it twice.
  result[a['spec']['gtfs_stop_id']]=dict(asset=a,factor=factor*(1+shift),cause_ids=[z['event_id'] for z,e in relevant])
 return result


def passengers(s,start,end):
 if timetable is None:return
 from metro_engine import active_services
 stations=station_effects(s);queues=s.setdefault('queues',{});loads=s.setdefault('trains',{})
 kind='passenger_entries_per_15min_weekend' if datetime.fromisoformat(s['service_date']).weekday()>4 else 'passenger_entries_per_15min_weekday'
 lookup={p['asset_id']:p['values'] for p in profiles if p['kind']==kind}
 services=active_services(timetable,s['service_date']);begin=start+s['start_seconds'];finish=end+s['start_seconds']
 departures=[]
 for trip in timetable['trips']:
  if trip['service'] not in services:continue
  for i,stop in enumerate(trip['times']):
   if begin<stop[2]<=finish:departures.append((stop[2],trip,i))
 cursor=begin
 def arrivals(until):
  nonlocal cursor
  while cursor<until:
   boundary=min(until,(int(cursor)//900+1)*900);index=int(cursor)//900%96
   for sid,info in stations.items():
    q=queues.setdefault(sid,dict(waiting=0,arrived=0,boarded=0,alighted=0,remainder=0))
    n=lookup.get(info['asset']['id'],[0]*96)[index]*(boundary-cursor)/900*info['factor']+q['remainder']
    whole=int(n);q['remainder']=n-whole;q['waiting']+=whole;q['arrived']+=whole
   cursor=boundary
 for when,trip,index in sorted(departures,key=lambda x:(x[0],x[1]['id'])):
  arrivals(when);stop=trip['times'][index];ref=timetable['stops'][stop[0]];sid=ref['parent'] or stop[0]
  if sid not in queues:continue
  q=queues[sid];onboard=loads.setdefault(trip['id'],dict(passengers=0,alight_at={}))
  n=onboard['alight_at'].pop(sid,0);onboard['passengers']-=n;q['alighted']+=n
  targets=list(dict.fromkeys((timetable['stops'][x[0]]['parent'] or x[0]) for x in trip['times'][index+1:]))
  if targets:
   capacity=next((a['spec']['capacity_passengers'] for a in assets if a['kind']=='METRO_TRAIN' and a['spec']['block_id']==trip['block']),0)
   n=min(q['waiting'],max(0,capacity-onboard['passengers']));q['waiting']-=n;q['boarded']+=n;onboard['passengers']+=n
   # Project stored destination weights onto this trip's downstream stations.
   origin=stations.get(sid,{}).get('asset',{}).get('id')
   model=next((a['spec']['destinations'] for a in assets if a['kind']=='METRO_OD_MODEL' and a['parent_id']==origin),[])
   weights={d['station_id']:d['probability'] for d in model}
   ws=[weights.get(stations.get(target,{}).get('asset',{}).get('id'),0) for target in targets]
   total=sum(ws);alloc=[int(n*w/total) if total else n//len(targets) for w in ws]
   for j in range(n-sum(alloc)):alloc[j%len(alloc)]+=1
   for target,count in zip(targets,alloc):onboard['alight_at'][target]=onboard['alight_at'].get(target,0)+count
  if not targets and onboard['passengers']==0:loads.pop(trip['id'],None)
 arrivals(finish)


def electric_summary(s):
 zones=[(Polygon(z['polygon']),z,effect(z,s['seconds'])) for z in s['scenarios']]
 weather={a['zone_id']:a['id'] for a in assets if a['kind']=='WEATHER_AREA'}
 profile={p['asset_id']:p['values'] for p in profiles if p['kind']=='electric_load_factor'}
 total=0;capacity=0;overloaded=0;affected=0;area_loads={z['id']:dict(load_kva=0,baseline_kva=0,transformers=0) for z in s['scenarios']}
 for a in assets:
  if a['kind']!='DISTRIBUTION_TRANSFORMER':continue
  base=seed_loads.get(a['id'])
  if base is None:continue
  curve=profile.get(weather.get(a['zone_id']),[1]*96);factor=curve[int((s['start_seconds']+s['seconds'])//900)%96]/max(.01,curve[20])
  relevant=[(z,e) for p,z,e in zones if p.covers(Point(a['longitude'],a['latitude']))]
  demand=max([e['electric_factor'] for z,e in relevant],default=1);pump=max([s['assumptions']['pumping_max_load_fraction'] for z,e in relevant if z.get('drainage_approved') and z['water_mm']>.1]+[0])
  for z,e in relevant:
   area_loads[z['id']]['baseline_kva']+=base*factor;area_loads[z['id']]['load_kva']+=base*factor*(demand+pump);area_loads[z['id']]['transformers']+=1
  load=base*factor*(demand+pump);cap=a['spec']['capacity_kva'];total+=load;capacity+=cap;overloaded+=load>cap;affected+=demand!=1 or pump>0
 return dict(load_kva=round(total,1),capacity_kva=capacity,load_percent=round(total/max(1,capacity)*100,1),overloaded_transformers=overloaded,affected_transformers=affected,areas={k:{**v,'load_kva':round(v['load_kva'],1),'baseline_kva':round(v['baseline_kva'],1),'delta_kva':round(v['load_kva']-v['baseline_kva'],1)} for k,v in area_loads.items()},provenance='SIMULATED_DATABASE_PROFILES')


def snapshot():
 global public_cache,public_version
 if current is None or time()-checked>20:raise HTTPException(503,'Shared simulation database is loading or unavailable; controls are paused')
 if public_cache is not None and public_version==current['version']:return public_cache
 s=current['state'];scenarios=[];power=electric_summary(s)
 for z in s['scenarios']:
  poly=Polygon(z['polygon']);e=effect(z,s['seconds'])
  affected=Counter(a['kind'] for a in assets if a['kind']!='ROAD_TRAFFIC_BLOCK' and (a['id'] in z.get('station_ids',[]) or (not z.get('station_ids') and a.get('longitude') is not None and poly.covers(Point(a['longitude'],a['latitude'])))))
  scenarios.append({**z,**e,'electrical_impact':power['areas'].get(z['id']),'affected':dict(affected),'status':'ACTIVE' if s['seconds']<z['end'] else 'DRAINING' if z['water_mm']>.1 else 'ENDED'})
 seconds=int(s['start_seconds']+s['seconds'])
 public_cache=dict(ready=True,asset_counts=dict(Counter(a['kind'] for a in assets)),version=current['version'],running=s['running'],speed=s['speed'],seconds=s['seconds'],clock=f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}',service_date=s['service_date'],scenarios=scenarios,events=s['events'],recommendations=s['recommendations'],electric=power,passengers=dict(waiting=sum(q['waiting'] for q in s.get('queues',{}).values()),arrived=sum(q['arrived'] for q in s.get('queues',{}).values()),boarded=sum(q['boarded'] for q in s.get('queues',{}).values()),onboard=sum(t['passengers'] for t in s.get('trains',{}).values())),provenance='SIMULATED_DATABASE_STATE',checked_at=datetime.fromtimestamp(checked,timezone.utc).isoformat(),note='Generated inputs from Supabase; modelled effects, not live observations. One committed clock is shared by all portals.')
 public_version=current['version']
 return public_cache


def check_readiness():
    """Actively verify database reachability and table usability.
    Clears any prior failure flag upon successful verification.
    """
    global db, current, checked, failure, RUN_ID
    if db is None:
        return False
    try:
        row = db.table('aegis_sim_runs').select('id,version,sim_seconds,configuration').eq('id', RUN_ID).single().execute().data
        if not row:
            failure = f'Simulation run {RUN_ID} not found'
            return False
        if current is None:
            from metro_simulation import unpack_state
            s = unpack_state(deepcopy(row['configuration'].get('runtime') or initial(row)))
            current = dict(state=s, version=row['version'])
        checked = time()
        failure = ''
        return True
    except Exception as exc:
        failure = f'Database unreachable: {type(exc).__name__}'
        return False


def start():
    global db, assets, profiles, failure, timetable, RUN_ID, _worker_thread, _worker_started
    if os.getenv("DISABLE_SCENARIO_WORKER", "false").lower() == "true":
        logging.info("Scenario background worker disabled via DISABLE_SCENARIO_WORKER")
        return

    with lock:
        if _worker_started and _worker_thread is not None and _worker_thread.is_alive():
            logging.info("Scenario worker already running; skipping duplicate start")
            return
        stop.clear()
        _worker_started = True

    def work():
        global db, assets, profiles, failure, timetable, RUN_ID
        try:
            c = dotenv_values(Path(__file__).with_name('.env.simulation'))
            simulation_url = os.getenv('SIMULATION_SUPABASE_URL') or c.get('SIMULATION_SUPABASE_URL')
            simulation_key = os.getenv('SIMULATION_SUPABASE_SERVICE_ROLE_KEY') or c.get('SIMULATION_SUPABASE_SERVICE_ROLE_KEY')
            if not simulation_url or not simulation_key:
                raise RuntimeError('Simulation Supabase credentials are missing')
            db = create_client(simulation_url, simulation_key)
            anchor = db.table('aegis_sim_runs').select('configuration').eq('id', ROOT_RUN_ID).single().execute().data
            RUN_ID = anchor['configuration'].get('active_run_id', ROOT_RUN_ID)
            for kind in ['WEATHER_AREA', 'METRO_STATION', 'DISTRIBUTION_TRANSFORMER', 'FEEDER', 'POWER_TRANSFORMER', 'SUBSTATION', 'TRAFFIC_SIGNAL', 'SIGNAL_GROUP', 'METRO_TRAIN', 'METRO_OD_MODEL']:
                for offset in range(0, 10000, 1000):
                    batch = db.table('aegis_sim_assets').select('*').eq('kind', kind).order('id').range(offset, offset + 999).execute().data
                    assets.extend(batch)
                    if len(batch) < 1000:
                        break
            profiles = rows('aegis_sim_profiles')
            for offset in range(0, 10000, 1000):
                batch = db.table('aegis_sim_state').select('asset_id,values->load_kva').eq('run_id', ROOT_RUN_ID).order('id').range(offset, offset + 999).execute().data
                seed_loads.update({r['asset_id']: r['load_kva'] for r in batch if r.get('load_kva') is not None})
                if len(batch) < 1000:
                    break
            from metro_engine import feed
            timetable = feed()
            from metro_network import Network
            import metro_simulation
            metro_simulation.network = Network(timetable, assets, profiles)
            while not stop.is_set():
                try:
                    commit()
                except ScenarioConflict as conflict:
                    logging.warning("Scenario tick skipped due to concurrent revision change: %s; worker remains active", conflict)
                    try:
                        row = db.table('aegis_sim_runs').select('*').eq('id', RUN_ID).single().execute().data
                        if row:
                            from metro_simulation import unpack_state
                            s = unpack_state(deepcopy(row['configuration'].get('runtime') or initial(row)))
                            current = dict(state=s, version=row['version'])
                            checked = time()
                            failure = ''
                    except Exception:
                        pass
                except (PersistenceContention, TransientPersistenceFailure) as transient_err:
                    logging.warning("Scenario tick encountered transient persistence issue: %s", transient_err)
                except Exception as exc:
                    failure = f'Shared simulation persistence unavailable: {type(exc).__name__}'
                    logging.exception('Scenario tick failed due to persistence error')
                stop.wait(2)
        except Exception as exc:
            failure = f'Shared database could not be loaded: {type(exc).__name__}'
            logging.exception('Scenario startup failed')

    _worker_thread = Thread(target=work, daemon=True, name='shared-scenario')
    _worker_thread.start()


@router.get('')
def get_snapshot():
    return snapshot()


@router.post('')
def control(c: Command):
    if db is None or current is None:
        raise HTTPException(503, 'Shared database is still loading')
    try:
        return commit(c)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except ScenarioConflict as e:
        raise HTTPException(409, 'Scenario was updated concurrently. Please retry your command.')
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Scenario command failed")
        raise HTTPException(503, f'Scenario change was not confirmed: {type(exc).__name__}. Refresh before retrying.')


@router.get('/electric-network')
def electric_network():
 snapshot()
 selected=[a for a in assets if a['kind'] in ('SUBSTATION','POWER_TRANSFORMER','FEEDER','DISTRIBUTION_TRANSFORMER')]
 by_id={a['id']:a for a in selected};features=[]
 for a in selected:
  props=dict(id=a['id'],name=a['name'],kind=a['kind'],parent_id=a['parent_id'] or '',capacity_kva=a['spec'].get('capacity_kva'),provenance='SIMULATED',zone_id=a['zone_id'])
  features.append(dict(type='Feature',properties=props,geometry=dict(type='Point',coordinates=[a['longitude'],a['latitude']])))
  parent=by_id.get(a['parent_id'])
  if parent and (a['longitude'],a['latitude'])!=(parent['longitude'],parent['latitude']):
   features.append(dict(type='Feature',properties=dict(**props,connection=True),geometry=dict(type='LineString',coordinates=[[parent['longitude'],parent['latitude']],[a['longitude'],a['latitude']]])))
 return dict(type='FeatureCollection',features=features,metadata=dict(source='Supabase generated electrical assets',note='Connections show stored parent relationships, not surveyed cable routes. Co-located equipment is listed in the asset selector.'))


@router.get('/metro-targets')
def metro_targets():
 snapshot()
 return dict(stations=sorted([dict(id=a['id'],name=a['name'],position=[a['longitude'],a['latitude']]) for a in assets if a['kind']=='METRO_STATION'],key=lambda a:a['name']))
