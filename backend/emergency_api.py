"""Shared-clock emergency workflow endpoints and closure-aware route preparation."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from uuid import uuid4
from threading import Thread,Event
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from shapely.geometry import LineString,Point,Polygon
import scenario_runtime as shared
from emergency_model import world,point_at,distance

router=APIRouter(prefix='/emergency',tags=['Database emergency workflow'])
stop=Event()

class Position(BaseModel):
    lat:float=Field(ge=17.05,le=17.85,allow_inf_nan=False)
    lon:float=Field(ge=78.05,le=78.95,allow_inf_nan=False)

class Action(BaseModel):
    action:Literal['REGISTER','APPROVE','REJECT','HELP','CLAIM','MANUAL','AUTO','OFFLINE','ONLINE','APPLY','EXCEPTION','STOP','RESUME','GPS_LOSS','GPS_RESTORE','CANCEL_REQUEST','CANCEL','CLEAR_BLOCKAGE','RESOLVE_HELP']
    actor:str=Field(min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=80)
    vehicle:str=Field(default='',max_length=60)
    trip_id:str|None=None
    plan_version:int|None=None
    target:str|None=None
    reason:str=Field(default='',max_length=500)

class Trip(BaseModel):
    request_id:str=Field(min_length=8,max_length=80)
    vehicle:str=Field(min_length=1,max_length=60)
    actor:str=Field(min_length=1,max_length=80)
    destination:str=Field(min_length=1,max_length=120)
    priority:Literal['CRITICAL','URGENT','TRANSFER']='URGENT'
    description:str=Field(default='',max_length=2000)
    start:Position
    end:Position

class Replan(BaseModel):
    request_id:str=Field(min_length=8,max_length=80)
    trip_id:str
    plan_version:int
    actor:str=Field(min_length=1,max_length=80)
    destination:str|None=None
    end:Position|None=None

class Blockage(Position):
    request_id:str=Field(min_length=8,max_length=80)
    actor:str=Field(min_length=1,max_length=80)
    reason:str=Field(min_length=3,max_length=300)

def commit(payload,request_id):
    if shared.db is None:raise HTTPException(503,'Shared database is still loading')
    from signal_operations import assets
    p={**payload,'_assets':assets(shared.current['state'])}
    c=SimpleNamespace(action='EMERGENCY',payload=p,request_id=request_id,target_id=p.get('trip_id'),speed=1)
    try:
        shared.commit(c)
    except ValueError as e:
        raise HTTPException(409,str(e))
    except shared.ScenarioConflict:
        raise HTTPException(409, 'Scenario was updated concurrently. Please retry with the same request ID.')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503,'Database commit not confirmed. Retry with the same request ID.')
    return snapshot()


def prepare(start,end):
    from google_operations import compute,RouteInput,Location
    from route_engine import route_engine
    from models import RouteRequest,Coordinate
    g=compute(RouteInput(origin=Location(lat=start['lat'],lng=start['lon']),destination=Location(lat=end['lat'],lng=end['lon'])))
    if g.get('operationallyUsable'):
        return dict(coordinates=g['coordinates'],source='GOOGLE_ROUTES',expires_at=(datetime.now(timezone.utc)+timedelta(days=29)).isoformat())
    # Google does not accept arbitrary local closures. Existing local graph excludes them.
    try:
        r=route_engine.calculate_route(RouteRequest(start=Coordinate(**start),end=Coordinate(**end)))
        return dict(coordinates=r['route']['geometry']['coordinates'],source='AEGIS_OSM_CLOSURE_AWARE',expires_at=None)
    except Exception:raise HTTPException(409,'No accessible route. Request urgent assistance.')

@router.get('')
def snapshot():
    shared.snapshot()
    s=shared.current['state'];w=deepcopy(world(s))
    return dict(**w,seconds=s['seconds'],running=s['running'],speed=s['speed'],version=shared.current['version'],events=[e for e in s['events'] if e['kind'].startswith(('EMERGENCY','AMBULANCE','CONTROLLER','COMMAND','PRIORITY','URGENT','MANUAL','JUNCTION','VEHICLE'))],source='SUPABASE_SHARED_RUNTIME',mode='SIMULATED')

@router.post('/action')
def action(p:Action):return commit(p.model_dump(),p.request_id)

@router.post('/trips')
def create(p:Trip):
    shared.snapshot();w=world(shared.current['state'])
    if p.request_id in shared.current['state']['requests']:return snapshot()
    if p.vehicle not in w['fleet']:raise HTTPException(409,'Register the vehicle in Traffic Command first')
    route=prepare(p.start.model_dump(),p.end.model_dump())
    return commit(dict(**p.model_dump(),action='CREATE',id=str(uuid4()),route=route),p.request_id)

@router.post('/replan')
def replan(p:Replan):
    shared.snapshot()
    if p.request_id in shared.current['state']['requests']:return snapshot()
    t=deepcopy(world(shared.current['state'])['trips'].get(p.trip_id))
    if not t:raise HTTPException(404,'Trip not found')
    if t['plan_version']!=p.plan_version:raise HTTPException(409,'Trip plan changed')
    end=p.end.model_dump() if p.end else t['destination_position']
    # Hold movement while the route provider works, so its starting position cannot become stale.
    commit(dict(action='HOLD_REPLAN',actor=p.actor,trip_id=t['id'],plan_version=t['plan_version']),p.request_id+':hold')
    t=deepcopy(world(shared.current['state'])['trips'][t['id']])
    try:route=prepare(dict(lat=t['position'][1],lon=t['position'][0]),end)
    except HTTPException:
        return commit(dict(action='NO_ROUTE',actor=p.actor,trip_id=t['id'],plan_version=t['plan_version']),p.request_id)
    payload=dict(action='REPLAN',actor=p.actor,trip_id=t['id'],plan_version=t['plan_version'],route=route)
    if p.destination:payload.update(destination=p.destination,end=end)
    return commit(payload,p.request_id)

@router.post('/blockages')
def block(p:Blockage):
    return commit(dict(action='BLOCKAGE',actor=p.actor,id=str(uuid4()),lat=p.lat,lon=p.lon,reason=p.reason),p.request_id)

def sync(s):
    from incident_engine import incident_engine
    for b in world(s).get('blockages',{}).values():
        if b.get('resolved'):
            incident_engine.active_incidents.pop(b['id'],None);continue
        incident_engine.active_incidents[b['id']]=dict(id=b['id'],lat=b['lat'],lon=b['lon'],status='ACTIVE',incident_type='ROAD_BLOCKAGE',severity=3,target_edge_id=None,description=b['reason'],provenance='SYNTHETIC',created_at=b['created_at'],affected_edges=[],direction=None,lanes_blocked=None)

def start():
    def work():
        from time import monotonic
        attempted={};retry_at={}
        while not stop.wait(2):
            if shared.current is None:continue
            for t in deepcopy(world(shared.current['state'])['trips']).values():
                if t['status'] in ('COMPLETED','CANCELLED') or t['movement']!='REPLANNING' or attempted.get(t['id'])==t['plan_version'] or monotonic()<retry_at.get(t['id'],0):continue
                attempted[t['id']]=t['plan_version']
                try:replan(Replan(trip_id=t['id'],plan_version=t['plan_version'],actor='CLOSURE_WORKER',request_id=f"closure:{t['id']}:{t['plan_version']}"))
                except Exception:
                    attempted.pop(t['id'],None);retry_at[t['id']]=monotonic()+60
    Thread(target=work,daemon=True,name='emergency-rerouting').start()
