"""Validated operational commands and read models for the shared metro engine."""
from copy import deepcopy
from math import ceil,isfinite
from uuid import uuid4
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
import metro_simulation as sim

router=APIRouter(prefix='/metro/operations',tags=['Metro operating model'])

class Action(BaseModel):
    action:str=Field(pattern='^(PROPOSE|APPROVE|REJECT|ACKNOWLEDGE|APPLY|CLAIM|READY|PROFILE|FAULT|CLEAR_FAULT)$')
    request_id:str=Field(min_length=8,max_length=90)
    actor:str=Field(min_length=1,max_length=80)
    target:str=''
    operation:str=Field(default='',pattern='^(|HOLD|RELEASE|HEADWAY|EXTRA_SERVICE|SHORT_TURN)$')
    station:str=''
    platform:str=''
    value:float=Field(default=120,ge=0,le=100000,allow_inf_nan=False)
    reason:str=Field(default='',max_length=1000)
    fault:str=Field(default='ACCESS',pattern='^(ACCESS|POWER)$')
    day:str=Field(default='weekday',pattern='^(weekday|weekend)$')
    profile:list[float]|None=Field(default=None,min_length=96,max_length=96)

def apply(s,p):
    m=sim.ensure(s);net=sim.network;c=m['config'];actor=p['actor'].strip();action=p['action']
    if not actor:raise ValueError('Operator identity is required')
    if action=='PROPOSE':
        operation=p['operation']
        if operation not in ('HOLD','RELEASE','HEADWAY','EXTRA_SERVICE','SHORT_TURN'):raise ValueError('Choose an operational command')
        if not p['reason'].strip():raise ValueError('Record the operating reason')
        if operation!='HEADWAY' and p['target'] not in m['vehicles']:raise ValueError('Select a train')
        if operation=='HEADWAY' and not 90<=p['value']<=600:raise ValueError('Headway must be between 90 and 600 seconds')
        if operation=='HOLD' and not 10<=p['value']<=900:raise ValueError('Hold must be between 10 and 900 seconds')
        d=dict(id=str(uuid4()),action=operation,vehicle=p['target'],station=p['station'],platform=p['platform'],
            value=p['value'],reason=p['reason'],status='PENDING',created=m['clock'],expires=m['clock']+600,source='OPERATOR',actor=actor)
        m['decisions'].append(d);sim.log(s,'COMMAND_PROPOSED',d);return
    if action in ('CLAIM','READY'):
        v=m['vehicles'].get(p['target'])
        if not v:raise ValueError('Train is unavailable')
        if action=='CLAIM':
            if v['pilot'] and v['pilot']!=actor:raise ValueError('This train is already assigned to another pilot')
            v.update(pilot=actor,manual=True,release=False,crew_ready=False)
        else:
            if v['pilot']!=actor:raise ValueError('Claim this train before declaring readiness')
            if v['status']=='TURNBACK' and m['clock']<v['turnback_start']+c['turnback_move_seconds']+c['cab_change_seconds']:raise ValueError('Cab-change time has not elapsed')
            v.update(crew_ready=True,release=True)
        sim.log(s,'PILOT_'+action,dict(vehicle=v['id'],actor=actor));return
    if action in ('PROFILE','FAULT','CLEAR_FAULT'):
        sid=p['station']
        if sid not in m['stations']:raise ValueError('Select a station')
        if not p['reason'].strip():raise ValueError('Record source or reason')
        if action=='PROFILE':
            if p.get('profile') is not None:
                if any(not isfinite(v) or v<0 or v>20000 for v in p['profile']):raise ValueError('Quarter-hour entries must be between 0 and 20,000')
                c['station_profile_overrides'][sid+'|'+p['day']]=p['profile']
            else:
                c['station_daily_targets'][sid+'|'+p['day']]=p['value'];c['station_profile_overrides'].pop(sid+'|'+p['day'],None)
            m['profiles']=net.demand_profiles(c)
        elif action=='CLEAR_FAULT':m['faults'].pop(sid,None)
        else:
            if not 10<=p['value']<=86400:raise ValueError('Fault duration must be 10 seconds to 24 hours')
            e=sim.log(s,'STATION_FAULT',dict(station=sid,fault=p['fault'],actor=actor,reason=p['reason']))
            m['faults'].setdefault(sid,{})[p['fault']]=dict(since=m['clock'],until=m['clock']+p['value'],backup_seconds=300,event_id=e)
        sim.log(s,action,dict(station=sid,actor=actor,reason=p['reason']));return
    d=next((d for d in m['decisions'] if d['id']==p['target']),None)
    if not d:raise ValueError('Command not found')
    if action=='REJECT':
        if d['status']!='PENDING' or not p['reason'].strip():raise ValueError('Pending command and rejection reason required')
        d.update(status='REJECTED',reviewer=actor,response=p['reason'])
    elif action=='APPROVE':
        if d['status']!='PENDING' or m['clock']>=d['expires']:raise ValueError('Recommendation is no longer current')
        d.update(status='APPROVED',reviewer=actor)
    elif action=='ACKNOWLEDGE':
        if d['status']!='APPROVED':raise ValueError('Only approved commands can be acknowledged')
        v=m['vehicles'].get(d.get('vehicle'))
        if v and v['pilot'] and v['pilot']!=actor:raise ValueError('The assigned pilot must acknowledge')
        d.update(status='ACKNOWLEDGED',acknowledged_by=actor)
    elif action=='APPLY':
        if d['status']!='ACKNOWLEDGED' or d['acknowledged_by']!=actor:raise ValueError('Acknowledge the approved command before applying it')
        if m['clock']>=d['expires']:raise ValueError('Command expired; submit a fresh plan')
        execute(s,m,d)
        d.update(status='APPLIED',applied_at=m['clock'],applied_by=actor)
    else:raise ValueError('Unsupported action')
    sim.log(s,'DECISION_'+action,deepcopy(d))

def execute(s,m,d):
    net=sim.network;v=m['vehicles'].get(d.get('vehicle'));op=d['action']
    if op=='HEADWAY':
        if not 90<=d['value']<=600:raise ValueError('Invalid separation')
        m['config']['min_headway_seconds']=d['value'];return
    if not v:raise ValueError('Train is unavailable')
    if op=='HOLD':
        if v['status'] not in ('IDLE','DWELLING','TURNBACK'):raise ValueError('Hold applies at a station or turnback, not midway along track')
        v['hold_until']=m['clock']+d['value'];return
    if op=='RELEASE':v.update(hold_until=0,release=True);return
    if op=='SHORT_TURN':
        # Use explicitly designated model reversing locations, not every station.
        if d['station'] not in ('AME','PRG'):raise ValueError('Only modelled Ameerpet / Parade Ground reversing facilities support short-turns; these are unverified simulation facilities')
        if v['status']!='DWELLING' or v['station']!=d['station']:raise ValueError('Train must be at the designated reversing station')
        v['short_end']=v['index']
    if op in ('EXTRA_SERVICE','SHORT_TURN'):
        if op=='EXTRA_SERVICE' and (v['status']!='IDLE' or not v['reserve']):raise ValueError('An idle reserve train at the departure terminal is required')
        patterns=[(shape,p) for shape,p in net.patterns.items() if p['line']==v['line'] and v['station'] in p['stops'][:-1]]
        if op=='SHORT_TURN':patterns=[x for x in patterns if x[0]!=sim.trip_for(m,v)['shape']]
        elif d.get('platform'):patterns=[x for x in patterns if x[0]==d['platform'].split('|')[-1]]
        if not patterns:raise ValueError('No compatible reverse/extra-service track pattern')
        shape,pattern=patterns[0];index=pattern['stops'].index(v['station']);source=pattern['times'][index:]
        start=m['clock']+(m['config']['turnback_seconds']+30 if op=='SHORT_TURN' else 30)
        offset=start-source[0][1];times=[[x[0],x[1]+offset,x[2]+offset,x[3]] for x in source]
        future=m['plan']['jobs'].get(v['id'],[])[v['cursor']+(1 if op=='SHORT_TURN' else 0):]
        if future and future[0]['start']<times[-1][2]+m['config']['turnback_seconds']:raise ValueError('Insufficient vehicle time before its next assignment; choose another train or hold plan')
        key='EXTRA-'+str(uuid4())[:8];trip={**pattern['trip'],'id':key,'times':times,'block':v['id']}
        m['extras'][key]=trip;job=dict(trip=key,start=start,end=times[-1][2],shift=0)
        m['plan']['jobs'].setdefault(v['id'],[]).insert(v['cursor']+(1 if op=='SHORT_TURN' else 0),job)
        v['reserve']=False

def snapshot():
    import scenario_runtime as shared
    shared.snapshot();m=shared.current['state'].get('metro_v3')
    if not m:raise HTTPException(503,'Metro operating model is rebuilding from database inputs')
    net=sim.network;stations=[]
    for sid,st in m['stations'].items():
        platforms=[]
        for pid,info in net.platforms.items():
            if info['station']!=sid:continue
            q=st['platforms'].get(pid,[]);n=sim.count(q);area=sim.platform_area(m,pid)
            platforms.append(dict(**info,waiting=n,area_m2=area,density_people_m2=round(n/area,2),
                capacity=round(area*m['config']['platform_limit_people_m2']),oldest_wait_seconds=round(m['clock']-min([c.get('queued_at',m['clock']) for c in q]+[m['clock']])),
                destinations=[dict(station=net.stations[d]['name'],passengers=sum(c['n'] for c in q if c['d']==d)) for d in sorted({c['d'] for c in q})]))
        cap=sum(p['capacity'] for p in platforms);occupancy=sim.inside_count(st)
        stations.append(dict(id=sid,name=net.stations[sid]['name'],waiting_passengers=sum(p['waiting'] for p in platforms),walking=sim.count(st['walking']),exiting=sim.count(st['exiting']),occupancy=occupancy,
            occupancy_percent=round(100*occupancy/max(1,cap),1),entered=st['entered'],transfers=st['transfers'],boarded=st['boarded'],alighted=st['alighted'],denied_boardings=st['denied'],platforms=platforms,
            history=st['history'],environment=m.get('environment',{}).get(sid,{}),provenance='SIMULATED_PLATFORM_FLOWS',
            weekday_profile=m['profiles'].get(sid+'|weekday'),weekend_profile=m['profiles'].get(sid+'|weekend')))
    return dict(stations=sorted(stations,key=lambda x:x['name']),vehicles=[dict(id=v['id'],station=v['station'],line=v['line'],status=v['status'],pilot=v['pilot'],manual=v['manual'],crew_ready=v['crew_ready'],reserve=v['reserve'],passengers=sim.count(v['onboard']),capacity=m['config']['train_capacity'],hold_until=v['hold_until']) for v in m['vehicles'].values()],
        decisions=m['decisions'],clock_seconds=m['clock'],running=shared.current['state']['running'],speed=shared.current['state']['speed'],version=shared.current['version'],
        conservation=sim.invariant(m),config=m['config'],quality=dict(source_conflicts=m['plan']['source_conflicts'],retimed=len(m['plan']['retimed']),unassigned=len(m['plan']['unassigned']),fleet=len(m['vehicles'])),
        agent=dict(status='ACTIVE',mode='DETERMINISTIC_RULES',schedule_changes_enabled=True,reason='Crowding and waiting time create reviewable commands. Approval, acknowledgement and Apply are required. Track and fleet interlocks still apply.'),
        source='SHARED_DATABASE_METRO_V3')

@router.get('')
def get():return snapshot()

@router.post('')
def post(p:Action):
    import scenario_runtime as shared
    from types import SimpleNamespace
    try:shared.commit(SimpleNamespace(action='METRO_OPERATION',payload=p.model_dump(),request_id=p.request_id,target_id=p.target,speed=1))
    except ValueError as e:raise HTTPException(409,str(e))
    return snapshot()
