"""Conserved passenger flows and one physical state per generated metro vehicle.

All mutable values live inside the shared database run. This module has no clock,
random generator, browser state or database writer of its own.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date
from math import sqrt, ceil
from uuid import uuid4
import json, zlib, base64
from metro_network import defaults, VERSION

network=None

def pack_state(s):
    result={k:v for k,v in s.items() if k!='metro_v3'}
    if 'metro_v3' in s:result['metro_v3_zlib']=base64.b64encode(zlib.compress(json.dumps(s['metro_v3'],separators=(',',':')).encode(),6)).decode()
    return result

def unpack_state(s):
    if s and s.get('metro_v3_zlib'):
        s=dict(s);s['metro_v3']=json.loads(zlib.decompress(base64.b64decode(s.pop('metro_v3_zlib'))))
    return s

def log(s,kind,payload):
    if kind in ('DEPARTED','TURNBACK_ENTERED') and 'metro_v3' in s:
        s['metro_v3'].setdefault('trace',[]).append(dict(kind=kind,seconds=s['metro_v3']['clock'],**payload));return None
    from scenario_runtime import event
    return event(s,'METRO_'+kind,payload)

def station_state():
    return dict(walking=[],platforms={},exiting=[],entered=0,transfers=0,boarded=0,alighted=0,
                exited=0,remainder=0,sequence=0,denied=0,metered=0,history=[])

def create(s):
    config=defaults();plan=network.plan(s['service_date'],config)
    return dict(version=VERSION,config=config,profiles=network.demand_profiles(config),plan=deepcopy(plan),
        clock=s['start_seconds'],stations={sid:station_state() for sid in network.stations},
        vehicles={f['id']:dict(id=f['id'],line=f['line'],station=f['station'],reserve=f['reserve'],
            cursor=0,trip=None,index=0,status='IDLE',onboard=[],speed=0,distance=0,
            hold_until=0,manual=False,pilot=None,crew_ready=True,release=True) for f in plan['fleet']},
        extras={},decisions=[],commands=[],faults={},departures={},bay_owners={},
        demand_remainder=0,last_entries=s['start_seconds'],last_agent=s['start_seconds'],last_history=0,
        incident_version=0,initialized_at=s['seconds'],provenance='SIMULATED_DATABASE_OPERATIONS')

def ensure(s):
    if network is None:return None
    m=s.get('metro_v3')
    if m and m.get('version')==VERSION:return m
    m=create(s);s['metro_v3']=m
    # Existing v1 counters are retained for audit. Reconstruct this model from stored
    # profiles and timetable, rather than guessing destinations for old queues.
    s['metro_legacy_totals']={k:sum(q.get(k,0) for q in s.get('queues',{}).values()) for k in ('waiting','arrived','boarded','alighted')}
    target=s['start_seconds']+s['seconds']
    m['migration']=dict(rebuilt_at=target,source='Stored timetable and demand; active scenario history only',legacy_totals=s['metro_legacy_totals'])
    while m['clock']<target:
        tick(s,min(5,target-m['clock']),warmup=True)
    log(s,'MODEL_INITIALIZED',dict(model=VERSION,legacy_totals=s['metro_legacy_totals'],source_conflicts=m['plan']['source_conflicts'],fleet=len(m['vehicles'])))
    sync_totals(s)
    return m

def count(rows):return sum(c['n'] for c in rows)

def inside_count(st):return count(st['walking'])+sum(count(q) for q in st['platforms'].values())+count(st['exiting'])

def route_cohort(m,sid,c,delay):
    if c['d']==sid:
        m['stations'][sid]['exiting'].append(dict(n=c['n'],ready=m['clock']+m['config']['exit_walk_seconds']));return
    legs=network.paths.get((sid,c['d']))
    if not legs:raise ValueError('Passenger destination has no network path')
    leg=legs[0]
    if leg['shape']=='WALK':
        m['stations'][sid]['walking'].append({**c,'ready':m['clock']+m['config']['transfer_walk_seconds'],'walk_to':leg['alight']});return
    m['stations'][sid]['walking'].append({**c,'ready':m['clock']+delay,'platform':sid+'|'+leg['shape'],'alight':leg['alight']})

def environment(s,m):
    from scenario_runtime import effect
    from shapely.geometry import Point,Polygon
    clock=m['clock']-s['start_seconds'];zones=[]
    for z in s['scenarios']:
        # Warm-up does not apply future inputs to earlier passenger arrivals.
        if clock<z['start']:continue
        zones.append((Polygon(z['polygon']),z,effect(z,clock)))
    result={}
    for sid,a in network.asset_by_station.items():
        relevant=[(z,e) for p,z,e in zones if a['id'] in z.get('station_ids',[]) or (not z.get('station_ids') and p.covers(Point(a['longitude'],a['latitude'])))]
        faults=m['faults'].get(sid,{})
        active={k:v for k,v in faults.items() if v['until']>m['clock']}
        power=active.get('POWER');backup=power and m['clock']-power['since']<power['backup_seconds']
        water=max([e['water_mm'] for z,e in relevant]+[0])
        result[sid]=dict(demand=max([e['metro_factor'] for z,e in relevant]+[1]),
            rain=max([e['rain_mm_hour'] for z,e in relevant]+[0]),
            access_closed=bool('ACCESS' in active or water>=150),
            power_failed=bool(power and not backup),backup=bool(backup),
            cause_ids=[z['event_id'] for z,e in relevant]+[v['event_id'] for v in active.values()])
    return result

def arrivals(s,m,elapsed,env):
    day='weekend' if date.fromisoformat(s['service_date']).weekday()>4 else 'weekday'
    slot=int(m['clock']//900)%96
    for sid,st in m['stations'].items():
        rate=m['profiles'].get(sid+'|'+day,[0]*96)[slot]/900 if m['clock']<86400 else 0
        n=rate*elapsed*env.get(sid,{}).get('demand',1)+st['remainder'];whole=int(n);st['remainder']=n-whole
        destinations=defaultdict(int)
        for _ in range(whole):
            d=network.destination(sid,st['sequence']);st['sequence']+=1
            if not d:continue
            destinations[d]+=1
        for d,n in destinations.items():
            st['entered']+=n
            route_cohort(m,sid,dict(d=d,n=n,born=m['clock'],o=sid),m['config']['entry_walk_seconds'])

def circulate(m,env):
    for sid,st in m['stations'].items():
        left=[]
        sizes={pid:count(q) for pid,q in st['platforms'].items()}
        areas={pid:platform_area(m,pid)*m['config']['platform_limit_people_m2'] for pid in st['platforms']}
        for c in st['walking']:
            if c['ready']>m['clock']:left.append(c);continue
            if c.get('walk_to'):
                route_cohort(m,c['walk_to'],{k:v for k,v in c.items() if k not in ('walk_to','ready')},0);continue
            pid=c['platform'];q=st['platforms'].setdefault(pid,[])
            if pid not in areas:areas[pid]=platform_area(m,pid)*m['config']['platform_limit_people_m2']
            limit=areas[pid]
            if env.get(sid,{}).get('access_closed') or env.get(sid,{}).get('power_failed') or sizes.get(pid,0)+c['n']>limit:
                left.append(c);continue
            q.append({**{k:v for k,v in c.items() if k!='ready'},'queued_at':m['clock']})
            sizes[pid]=sizes.get(pid,0)+c['n']
        st['walking']=left
        exiting=[]
        for c in st['exiting']:
            if c['ready']<=m['clock']:st['exited']+=c['n']
            else:exiting.append(c)
        st['exiting']=exiting

def platform_area(m,pid):
    sid=pid.split('|')[0]
    lines={v['line'] for v in network.platforms.values() if v['station']==sid}
    return m['config']['interchange_platform_area_m2'] if len(lines)>1 else m['config']['platform_area_m2']

def trip_for(m,v):return m['extras'].get(v['trip']) or network.trips.get(v['trip'])

def start_trip(m,v,job):
    trip=m['extras'].get(job['trip']) or network.trips[job['trip']]
    v.update(trip=trip['id'],index=0,status='DWELLING',distance=0,speed=0,shift=job['shift'],
        actual_arrival=m['clock'],exchange=0,release=not v['manual'],crew_ready=not v['manual'])
    v['dwell_until']=max(job['start']+trip['times'][0][2]-trip['times'][0][1],m['clock']+m['config']['min_dwell_seconds'])

def arrive(m,v):
    trip=trip_for(m,v);sid=network.parent(trip['times'][v['index']][0]);v['station']=sid
    v.update(status='DWELLING',speed=0,distance=0,actual_arrival=m['clock'],exchange=0,release=not v['manual'])
    pid=sid+'|'+trip['shape'];q=m['stations'][sid]['platforms'].get(pid,[])
    alight=sum(c['n'] for c in v['onboard'] if c['alight']==sid or v['index']==v.get('short_end',len(trip['times'])-1))
    board=min(count(q),max(0,m['config']['train_capacity']-count(v['onboard'])+alight))
    crowd=count(v['onboard'])/m['config']['train_capacity'];flow=m['config']['door_flow_people_sec']*max(.4,1-.5*crowd)
    dwell=max(m['config']['min_dwell_seconds'],min(m['config']['max_dwell_seconds'],m['config']['door_setup_seconds']+(alight+board)/flow))
    v['dwell_until']=max(trip['times'][v['index']][2]+v['shift'],m['clock']+dwell)

def exchange(m,v,dt,env):
    trip=trip_for(m,v);sid=v['station'];st=m['stations'][sid];last=v['index']==v.get('short_end',len(trip['times'])-1)
    if m['clock']-v['actual_arrival']<m['config']['door_setup_seconds']:return
    crowd=count(v['onboard'])/m['config']['train_capacity']
    quota=m['config']['door_flow_people_sec']*max(.4,1-.5*crowd)*dt+v['exchange'];budget=int(quota);v['exchange']=quota-budget
    keep=[]
    for c in v['onboard']:
        n=min(c['n'],budget) if c['alight']==sid or last else 0
        if n:
            budget-=n;st['alighted']+=n
            if c['d']!=sid:st['transfers']+=n
            route_cohort(m,sid,{**c,'n':n},m['config']['transfer_walk_seconds'])
        if c['n']>n:keep.append({**c,'n':c['n']-n})
    v['onboard']=keep
    if last or env.get(sid,{}).get('power_failed'):return
    # Everyone waiting here already chose a compatible line, direction and alighting stop.
    pid=sid+'|'+trip['shape'];q=st['platforms'].setdefault(pid,[]);remaining=[]
    downstream={network.parent(t[0]) for t in trip['times'][v['index']+1:v.get('short_end',len(trip['times'])-1)+1]}
    capacity=m['config']['train_capacity']-count(v['onboard'])
    for index,c in enumerate(q):
        if not budget or not capacity:
            remaining.extend(q[index:]);break
        n=min(c['n'],budget,capacity) if c['alight'] in downstream else 0
        if n:
            budget-=n;capacity-=n;st['boarded']+=n;v['onboard'].append({**c,'n':n})
        if c['n']>n:remaining.append({**c,'n':c['n']-n})
    st['platforms'][pid]=remaining

def tick(s,dt,warmup=False):
    m=s['metro_v3'];m['clock']+=dt;env=environment(s,m);m['environment']=env
    if m['clock']-m['last_entries']>=15:
        arrivals(s,m,m['clock']-m['last_entries'],env);m['last_entries']=m['clock']
    circulate(m,env)
    occupied={v.get('section'):v['id'] for v in m['vehicles'].values() if v['status']=='IN_TRANSIT'}
    for v in m['vehicles'].values():
        jobs=m['plan']['jobs'].get(v['id'],[])
        if v['status']=='TURNBACK':
            elapsed=m['clock']-v['turnback_start'];c=m['config']
            v['turnback_phase']='ENTERING_BAY' if elapsed<c['turnback_move_seconds'] else 'CAB_CHANGE' if elapsed<c['turnback_move_seconds']+c['cab_change_seconds'] else 'RETURNING_TO_PLATFORM'
            if m['clock']>=max(v['turnback_end'],v['hold_until']) and v['crew_ready']:
                v.update(status='IDLE',trip=None);m['bay_owners'].pop(v['id'],None)
            else:continue
        if v['status']=='IDLE':
            if m['clock']<v['hold_until']:continue
            if v['cursor']>=len(jobs):v['reserve']=True
            while v['cursor']<len(jobs) and jobs[v['cursor']]['start']<=m['clock']:
                job=jobs[v['cursor']];trip=m['extras'].get(job['trip']) or network.trips[job['trip']]
                if v['station']!=network.parent(trip['times'][0][0]):
                    v['cursor']+=1
                    if not warmup:log(s,'SERVICE_CANCELLED',dict(vehicle=v['id'],trip=trip['id'],reason='Vehicle is at another terminal after operational change'))
                    continue
                start_trip(m,v,job);break
            if v['status']=='IDLE':continue
        trip=trip_for(m,v);i=v['index'];sid=v['station'];last=i==v.get('short_end',len(trip['times'])-1)
        if v['status']=='DWELLING':
            exchange(m,v,dt,env)
            if m['clock']<max(v['dwell_until'],v['hold_until']):continue
            if last:
                if count(v['onboard']):continue
                bay=sid+'|'+trip['route']
                if sum(x==bay for x in m['bay_owners'].values())>=m['config']['turnback_bays']:continue
                m['bay_owners'][v['id']]=bay;v['cursor']+=1
                v.update(status='TURNBACK',turnback_start=m['clock'],turnback_end=m['clock']+m['config']['turnback_seconds'],crew_ready=not v['manual'])
                v.pop('short_end',None)
                if not warmup:log(s,'TURNBACK_ENTERED',dict(vehicle=v['id'],station=sid))
                continue
            next_sid=network.parent(trip['times'][i+1][0]);pid=sid+'|'+trip['shape'];section=pid+'|'+next_sid
            if not v['release'] or not v['crew_ready'] or env.get(sid,{}).get('power_failed') or env.get(next_sid,{}).get('power_failed'):continue
            if section in occupied or m['clock']-m['departures'].get(pid,-10000)<m['config']['min_headway_seconds']:continue
            # Do not enter an occupied receiving platform in the same direction.
            if any(o['id']!=v['id'] and o['status']=='DWELLING' and o['station']==next_sid and trip_for(m,o)['shape']==trip['shape'] for o in m['vehicles'].values()):continue
            q=m['stations'][sid]['platforms'].get(pid,[]);m['stations'][sid]['denied']+=count(q)
            v.update(status='IN_TRANSIT',section=section,distance=0,speed=0,
                segment_m=network.segment_metres(trip,i),departed=m['clock'])
            m['departures'][pid]=m['clock'];occupied[section]=v['id']
            if not warmup:log(s,'DEPARTED',dict(vehicle=v['id'],trip=trip['id'],station=sid,passengers=count(v['onboard'])))
        if v['status']=='IN_TRANSIT':
            next_sid=network.parent(trip['times'][i+1][0]);remaining=max(0,v['segment_m']-v['distance'])
            scheduled=max(1,trip['times'][i+1][1]-trip['times'][i][2]);ceiling=min(m['config']['max_speed_mps'],v['segment_m']/scheduled*1.35)
            rainfall=max(env.get(sid,{}).get('rain',0),env.get(next_sid,{}).get('rain',0))
            ceiling/=1+min(.4,rainfall/300)
            if env.get(next_sid,{}).get('power_failed'):ceiling=0
            target=min(ceiling,sqrt(2*m['config']['braking_mps2']*remaining));old=v['speed']
            speed=min(target,old+m['config']['acceleration_mps2']*dt) if target>=old else max(target,old-m['config']['braking_mps2']*dt)
            move=min(remaining,(old+speed)/2*dt);v['distance']+=move;v['speed']=speed
            if remaining-move<.5:
                occupied.pop(v['section'],None);v['index']+=1;arrive(m,v)
    if m['clock']-m['last_agent']>=30 and not warmup:
        agent(s,m);m['last_agent']=m['clock']
        if m.get('trace'):
            log(s,'MOVEMENT_BATCH',dict(samples=m['trace']));m['trace']=[]
    if m['clock']-m['last_history']>=60:
        for st in m['stations'].values():
            st['history']=(st['history']+[dict(seconds=m['clock'],waiting=sum(count(q) for q in st['platforms'].values()),occupancy=inside_count(st),entered=st['entered'])])[-60:]
        m['last_history']=m['clock']

def agent(s,m):
    from metro_agent import evaluate
    evaluate(s,m)

def sync_totals(s):
    m=s['metro_v3'];s['queues']={sid:dict(waiting=sum(count(q) for q in st['platforms'].values())+count(st['walking']),arrived=st['entered'],boarded=st['boarded'],alighted=st['alighted']) for sid,st in m['stations'].items()}
    s['trains']={v['id']:dict(passengers=count(v['onboard'])) for v in m['vehicles'].values()}

def invariant(m):
    entered=sum(st['entered'] for st in m['stations'].values());exited=sum(st['exited'] for st in m['stations'].values())
    inside=sum(inside_count(st) for st in m['stations'].values());onboard=sum(count(v['onboard']) for v in m['vehicles'].values())
    return dict(entered=entered,exited=exited,inside_stations=inside,onboard=onboard,error=entered-exited-inside-onboard)
