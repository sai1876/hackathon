"""Directional signal definitions and transformer links in the shared database run."""
from copy import deepcopy
from math import atan2,degrees
from uuid import uuid4
from types import SimpleNamespace
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field

router=APIRouter(prefix='/command/signals',tags=['Signal registry'])

def approaches(count=4,rotation=0):
    angles={2:[0,180],3:[0,90,270],4:[0,90,180,270],6:[0,60,120,180,240,300]}[count]
    directions=['N','NE','E','SE','S','SW','W','NW']
    result=[]
    for i,b in enumerate(angles):
        b=(b+rotation)%360;name=directions[int((b+22.5)//45)%8]
        result.append(dict(index=i,bearing=b,label=f'{name} bound',from_side=directions[int(((b+180)%360+22.5)//45)%8]))
    return result

def assets(s):
    import scenario_runtime as shared
    return shared.assets+list(s.get('custom_signals',{}).values())

def nearest(s,lon,lat):
    from emergency_model import distance
    candidates=[a for a in assets(s) if a['kind']=='DISTRIBUTION_TRANSFORMER' and a.get('longitude') is not None]
    if not candidates:raise ValueError('No stored distribution transformers are available. Load the electrical inventory first.')
    a=min(candidates,key=lambda a:distance([lon,lat],[a['longitude'],a['latitude']]))
    return dict(asset_id=a['id'],name=a['name'],position=[a['longitude'],a['latitude']],distance_m=round(distance([lon,lat],[a['longitude'],a['latitude']])),provenance=a.get('provenance','SIMULATED'),relationship='MODELED_POWER_SUPPLY',note='Nearest stored transformer; electrical connectivity and cable route are not surveyed.')

def phase_states(s,j,failed=False):
    from emergency_model import green
    definitions=j.get('approaches') or approaches();allowed=green(s,j)
    amber=[];stage=j['stage'];elapsed=s['seconds']
    if stage=='NORMAL':
        if j.get('sequential'):
            phase=(elapsed+j['offset'])%j['cycle_seconds'];segment=j['green_seconds']+j['amber_seconds']+j['all_red_seconds'];index=int(phase//segment)
            if j['green_seconds']<=phase%segment<j['green_seconds']+j['amber_seconds']:amber=[index]
        else:
            phase=(elapsed+j['offset'])%90
            amber=[0,2] if 42<=phase<45 else [1,3] if 87<=phase<90 else []
    elif stage=='AMBER_RECOVERY':amber=[j['approach']] if j.get('approach') is not None else []
    elif stage=='AMBER':amber=j.get('clearance_approaches',[])
    return [{**a,'state':'FAILED' if failed or not j['online'] or j.get('environment_failed') else 'GREEN' if a['index'] in allowed else 'AMBER' if a['index'] in amber else 'RED',
             'queue_vehicles':round(j['queues'][a['index']],1) if a['index']<len(j['queues']) else None} for a in definitions]

def apply(s,p):
    from emergency_model import controller,distance
    from scenario_runtime import event
    if not p['actor'].strip() or not p['name'].strip():raise ValueError('Operator and junction name are required')
    if len(s.get('custom_signals',{}))>=250:raise ValueError('This run already contains 250 added junctions')
    if any(a['kind']=='TRAFFIC_SIGNAL' and distance([p['lon'],p['lat']],[a['longitude'],a['latitude']])<12 for a in assets(s)):raise ValueError('A signal already exists within 12 metres; inspect it before adding another controller')
    supply=nearest(s,p['lon'],p['lat']);identifier=str(uuid4());definition=approaches(p['bounds'],p['rotation'])
    a=dict(id=identifier,name=p['name'].strip(),kind='TRAFFIC_SIGNAL',longitude=p['lon'],latitude=p['lat'],parent_id=supply['asset_id'],provenance='OPERATOR_PLACED_SIMULATION',spec=dict(approaches=definition,power_supply=supply,sequential=True,green_seconds=25,amber_seconds=3,all_red_seconds=2,cycle_seconds=30*p['bounds']))
    s.setdefault('custom_signals',{})[identifier]=a
    s.setdefault('signal_plans',{})[identifier]=dict(cycle_seconds=30*p['bounds'],offset_seconds=0,green_seconds=25,amber_seconds=3,all_red_seconds=2,provenance='OPERATOR_GENERATED_TIMING_PLAN')
    controller(s,a)
    event(s,'SIGNAL_CREATED',dict(asset=deepcopy(a),actor=p['actor'],connection=supply))

class Create(BaseModel):
    actor:str=Field(min_length=1,max_length=80)
    name:str=Field(min_length=3,max_length=120)
    request_id:str=Field(min_length=8,max_length=90)
    bounds:int
    rotation:float=Field(default=0,ge=0,lt=360,allow_inf_nan=False)
    lat:float=Field(ge=17.05,le=17.85,allow_inf_nan=False)
    lon:float=Field(ge=78.05,le=78.95,allow_inf_nan=False)

@router.post('')
def create(p:Create):
    import scenario_runtime as shared
    if p.bounds not in (2,3,4,6):raise HTTPException(422,'Choose 2, 3, 4 or 6 approaches')
    shared.snapshot()
    try:
        shared.commit(SimpleNamespace(action='SIGNAL_CREATE',payload=p.model_dump(),request_id=p.request_id,target_id=None,speed=1))
    except ValueError as e:
        raise HTTPException(409,str(e))
    except shared.ScenarioConflict:
        raise HTTPException(409, 'Scenario was updated concurrently. Please retry.')
    from command_data import signals
    return signals()

