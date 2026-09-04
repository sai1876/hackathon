"""Deterministic prototype emergency controllers. No physical signal actuation."""
from math import radians, sin, cos, atan2, sqrt
from uuid import uuid4
from shapely.geometry import Point, LineString

def distance(a,b):
    lat1,lat2=radians(a[1]),radians(b[1]);dlat=lat2-lat1;dlon=radians(b[0]-a[0])
    v=sin(dlat/2)**2+cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000*2*atan2(sqrt(v),sqrt(max(0,1-v)))

def point_at(points,metres):
    for a,b in zip(points,points[1:]):
        length=distance(a,b)
        if metres<=length:
            f=min(1,max(0,metres/max(.001,length)))
            return [a[i]+f*(b[i]-a[i]) for i in (0,1)]
        metres-=length
    return list(points[-1])

def emit(s,kind,payload):
    from scenario_runtime import event
    return event(s,kind,payload)

def world(s):
    return s.setdefault('emergency',dict(fleet={},trips={},urgent={},controllers={},commands={}))

def urgent(s,t,reason):
    w=world(s);key=t['id']+':'+reason
    if key not in w['urgent']:
        w['urgent'][key]=dict(id=key,trip_id=t['id'],reason=reason,status='OPEN',owner=None,created=s['seconds'])
        emit(s,'EMERGENCY_HELP_REQUESTED',w['urgent'][key])

def recover(s,j):
    # A released green must pass through amber and all-red before ordinary phases resume.
    stage='AMBER_RECOVERY' if j['stage']=='GREEN' else 'RECOVERY'
    j.update(stage=stage,until=s['seconds']+(3 if stage=='AMBER_RECOVERY' else 8),verified_green=False)

def expire(s,t,why):
    w=world(s)
    for c in w['commands'].values():
        if c['trip_id']==t['id'] and c['status']=='PENDING':c['status']='EXPIRED';emit(s,'COMMAND_EXPIRED',dict(command_id=c['id'],reason=why))
    for j in w['controllers'].values():
        if j.get('trip_id')==t['id'] and j['stage'] not in ('NORMAL','RECOVERY'):
            recover(s,j)
            emit(s,'JUNCTION_RECOVERY',dict(junction_id=j['id'],reason=why))

def build_plan(points,assets):
    line=LineString(points);result=[];length=sum(distance(a,b) for a,b in zip(points,points[1:]))
    for a in assets:
        if a['kind']!='TRAFFIC_SIGNAL':continue
        pos=Point(a['longitude'],a['latitude'])
        if line.distance(pos)>.00035:continue
        # Project onto road geometry, then convert projection segment lengths to metres.
        loc=line.interpolate(line.project(pos));metres=0
        for p,q in zip(points,points[1:]):
            segment=LineString([p,q])
            if segment.distance(loc)<1e-9:
                metres+=distance(p,[loc.x,loc.y]);break
            metres+=distance(p,q)
        if metres<10 or length-metres<5:continue
        before=point_at(points,max(0,metres-15));after=point_at(points,metres+15)
        heading=(atan2(after[0]-before[0],after[1]-before[1])*180/3.141592653589793+360)%360
        from signal_operations import approaches
        definition=a.get('spec',{}).get('approaches') or approaches()
        approach=min(range(len(definition)),key=lambda i:abs((heading-definition[i]['bearing']+180)%360-180))
        result.append(dict(id=a['id'],name=a['name'],distance_m=metres,position=[loc.x,loc.y],approach=approach,status='UPCOMING',spec=a.get('spec',{})))
    return sorted(result,key=lambda j:j['distance_m'])

def controller(s,entry):
    w=world(s)
    if entry['id'] not in w['controllers']:
        seed=sum(ord(c) for c in entry['id'])
        from scenario_runtime import signal_plan
        timing=signal_plan(s,entry)
        from signal_operations import approaches,assets
        asset=next((a for a in assets(s) if a['id']==entry['id']),entry)
        spec=asset.get('spec',{});definition=spec.get('approaches') or approaches()
        w['controllers'][entry['id']]=dict(id=entry['id'],stage='NORMAL',until=0,verified_green=False,
            trip_id=None,approach=None,manual=False,online=True,queues=[float(4+(seed+i*7)%15) for i in range(len(definition))],
            arrivals=[.10+(seed+i)%5*.025 for i in range(len(definition))],offset=timing['offset_seconds'],extra_delay=0,held_vehicle_seconds=0,
            approaches=definition,sequential=spec.get('sequential',False),cycle_seconds=timing['cycle_seconds'],green_seconds=timing['green_seconds'],amber_seconds=timing['amber_seconds'],all_red_seconds=timing['all_red_seconds'],
            provenance='SIMULATED_CONTROLLER',assumptions=dict(cycle_seconds=90,amber_seconds=3,all_red_seconds=2,discharge_vehicles_sec=.5))
    return w['controllers'][entry['id']]

def normal_approaches(s,j):
    if j.get('sequential'):
        phase=(s['seconds']+j['offset'])%j['cycle_seconds'];segment=j['green_seconds']+j['amber_seconds']+j['all_red_seconds']
        return [int(phase//segment)] if phase%segment<j['green_seconds'] else []
    phase=(s['seconds']+j['offset'])%90
    return [0,2] if 3<=phase<42 else [1,3] if 48<=phase<87 else []

def green(s,j):
    if not j['online'] or j.get('environment_failed'):return []
    if j['stage']=='NORMAL':return normal_approaches(s,j)
    return [j['approach']] if j['stage']=='GREEN' and j['verified_green'] else []

def send(s,t,entry,manual_apply=False):
    j=controller(s,entry);w=world(s)
    if j['stage']!='NORMAL' or j.get('retry_exhausted'):return
    if j['manual'] and not manual_apply:
        if not any(c['junction_id']==j['id'] and c['trip_id']==t['id'] and c['status']=='PENDING' for c in w['commands'].values()):
            c=dict(id=str(uuid4()),trip_id=t['id'],junction_id=j['id'],plan_version=t['plan_version'],status='PENDING',expires=s['seconds']+30,action='PREPARE_PRIORITY')
            w['commands'][c['id']]=c;emit(s,'MANUAL_COMMAND_RECOMMENDED',c)
        return
    required=j['queues'][entry['approach']]/.5+8
    required=max(required,(entry['distance_m']-t['travelled_m'])/max(2,t['speed_mps'])-12+8)
    average_extra=delay_estimate(s,j,entry['approach'],required)
    t['calculation']=dict(queue_clearance_seconds=round(required-8,1),required_green_seconds=round(required,1),average_extra_delay_seconds=round(average_extra,1),provenance='SIMULATED_QUEUE_MODEL')
    if average_extra>120 and not t.get('delay_exception'):
        t['priority_hold']=True;urgent(s,t,'AVERAGE_DELAY_EXCEPTION');return
    j['clearance_approaches']=green(s,j)
    j.update(stage='SENT',until=s['seconds']+1,trip_id=t['id'],approach=entry['approach'],attempts=1,verified_green=False,green_seconds=min(120,max(8,required)))
    emit(s,'PRIORITY_REQUEST_SENT',dict(trip_id=t['id'],junction_id=j['id'],plan_version=t['plan_version']))

def apply(s,p):
    w=world(s);action=p['action'];actor=p.get('actor','').strip()
    if not actor:raise ValueError('Enter the operator or requester name')
    if action=='REGISTER':
        vehicle=p['vehicle'].strip()
        if not vehicle:raise ValueError('Vehicle identifier is required')
        w['fleet'][vehicle]=dict(id=vehicle,active=True,registered_by=actor)
        emit(s,'VEHICLE_REGISTERED',w['fleet'][vehicle]);return
    if action=='CREATE':
        if p['vehicle'] not in w['fleet'] or not w['fleet'][p['vehicle']]['active']:raise ValueError('Traffic Command must register this vehicle first')
        if any(t['vehicle']==p['vehicle'] and t['status'] not in ('COMPLETED','CANCELLED') for t in w['trips'].values()):raise ValueError('Vehicle already has an active trip')
        points=p['route']['coordinates']
        if route_conflicts(s,points):raise ValueError('A closure changed while preparing the route. Recalculate before starting.')
        plan=build_plan(points,p['_assets'])
        if len(w['trips'])>=100:raise ValueError('This run has reached its trip limit; archive it before creating another run')
        t=dict(id=p['id'],vehicle=p['vehicle'],destination=p['destination'],destination_position=p['end'],priority=p['priority'],description=p.get('description',''),
            status='PENDING',plan_version=1,created=s['seconds'],review_ready=s['seconds'],review_deadline=s['seconds']+60,
            coordinates=points,route_source=p['route']['source'],distance_m=sum(distance(a,b) for a,b in zip(points,points[1:])),
            travelled_m=0,speed_mps=0,position=list(points[0]),plan=plan,priority_hold=False,limited_used=False,
            movement='NORMAL_NAVIGATION',provenance='SIMULATED_GPS',history=[],decisions=[],route_expires_at=p['route'].get('expires_at'))
        w['trips'][t['id']]=t
        for entry in plan:controller(s,entry)
        emit(s,'EMERGENCY_REVIEW_READY',dict(trip_id=t['id'],vehicle=t['vehicle'],priority=t['priority'],junctions=len(plan),review_deadline=t['review_deadline']));return
    if action=='BLOCKAGE':
        from datetime import datetime,timezone
        b=dict(id=p['id'],lat=p['lat'],lon=p['lon'],reason=p['reason'],created_at=datetime.now(timezone.utc).isoformat())
        w.setdefault('blockages',{})[b['id']]=b
        emit(s,'EMERGENCY_BLOCKAGE_CREATED',b)
        for trip in w['trips'].values():
            if trip['status'] in ('COMPLETED','CANCELLED','RECOVERING'):continue
            remaining=[point_at(trip['coordinates'],trip['travelled_m'])]
            cumulative=0
            for a,c in zip(trip['coordinates'],trip['coordinates'][1:]):
                cumulative+=distance(a,c)
                if cumulative>trip['travelled_m']:remaining.append(c)
            if len(remaining)>1 and LineString(remaining).distance(Point(b['lon'],b['lat']))<.0003:
                expire(s,trip,'Blockage invalidated corridor');trip.update(movement='REPLANNING',priority_hold=True,speed_mps=0)
                trip['status']='PENDING';trip['plan_version']+=1
                urgent(s,trip,'CORRIDOR_BLOCKED')
                emit(s,'EMERGENCY_REPLAN_REQUIRED',dict(trip_id=trip['id'],blockage_id=b['id']))
        return
    if action=='CLEAR_BLOCKAGE':
        b=w.get('blockages',{}).get(p['target'])
        if not b:raise ValueError('Blockage not found')
        b['resolved']=True;emit(s,'EMERGENCY_BLOCKAGE_CLEARED',dict(id=b['id'],actor=actor));return
    if action=='RESOLVE_HELP':
        u=w['urgent'].get(p['target'])
        if not u:raise ValueError('Urgent request not found')
        if u['owner']!=actor:raise ValueError('Take responsibility before resolving this request')
        if not p.get('reason','').strip():raise ValueError('Enter the response or resolution')
        u.update(status='RESOLVED',response=p['reason'],resolved_at=s['seconds']);emit(s,'URGENT_RESOLVED',dict(id=u['id'],actor=actor,response=p['reason']));return
    if action=='CLAIM':
        u=w['urgent'].get(p['target'])
        if not u:raise ValueError('Urgent request not found')
        if u['owner'] and u['owner']!=actor:raise ValueError('Another officer owns this request')
        u.update(owner=actor,status='CLAIMED');emit(s,'URGENT_CLAIMED',dict(id=u['id'],actor=actor));return
    if action in ('MANUAL','AUTO','OFFLINE','ONLINE'):
        j=w['controllers'].get(p['target'])
        if not j:
            a=next((a for a in p.get('_assets',[]) if a['kind']=='TRAFFIC_SIGNAL' and a['id']==p['target']),None)
            if not a:raise ValueError('Controller not found')
            j=controller(s,dict(id=a['id']))
        if action in ('MANUAL','AUTO'):j['manual']=action=='MANUAL'
        else:j['online']=action=='ONLINE';j['verified_green']=False
        if action=='ONLINE':j['retry_exhausted']=False
        if action=='MANUAL' and j['stage']=='SENT':j.update(stage='NORMAL',trip_id=None)
        emit(s,'CONTROLLER_'+action,dict(junction_id=j['id'],actor=actor));return
    if action=='APPLY':
        c=w['commands'].get(p['target'])
        if not c or c['status']!='PENDING':raise ValueError('Command is no longer applicable')
        t=w['trips'][c['trip_id']]
        entry=next((j for j in t['plan'] if j['id']==c['junction_id'] and j['distance_m']>t['travelled_m']),None)
        if c['expires']<=s['seconds'] or c['plan_version']!=t['plan_version'] or not entry or t['status']!='APPROVED' or t['priority_hold']:raise ValueError('Command expired or priority is no longer authorized')
        j=controller(s,entry)
        if j['stage']!='NORMAL':raise ValueError('Controller is busy; review its current state')
        c['status']='APPLIED';send(s,t,entry,True);emit(s,'MANUAL_COMMAND_APPLIED',dict(command_id=c['id'],actor=actor));return
    t=w['trips'].get(p.get('trip_id'))
    if not t:raise ValueError('Trip not found')
    if t['status'] in ('COMPLETED','CANCELLED'):raise ValueError('This trip has ended; its route cannot be changed')
    if p.get('plan_version')!=t['plan_version']:raise ValueError('Route changed; review the current plan before acting')
    if action in ('APPROVE','REJECT'):
        if t['status']!='PENDING':raise ValueError('Trip is not awaiting review')
        if action=='APPROVE' and (t['movement'] in ('NO_ACCESSIBLE_ROUTE','REPLANNING') or route_conflicts(s,remaining_route(t))):raise ValueError('A usable route must be prepared before approval')
        if action=='REJECT' and not p.get('reason','').strip():raise ValueError('Rejection requires a reason')
        t['status']='APPROVED' if action=='APPROVE' else 'REJECTED';t['priority_hold']=False
        t['decisions'].append(dict(action=action,actor=actor,reason=p.get('reason'),at=s['seconds'],plan_version=t['plan_version']))
        if action=='REJECT':expire(s,t,'Priority rejected')
    elif action=='HELP':urgent(s,t,'REQUESTED_ASSISTANCE')
    elif action=='EXCEPTION':
        if not p.get('reason','').strip():raise ValueError('Delay exception requires an officer reason')
        t['delay_exception']=True;t['priority_hold']=False
    elif action=='STOP':t['stopped']=True;expire(s,t,'Ambulance stopped')
    elif action=='RESUME':t['stopped']=False
    elif action=='GPS_LOSS':t['gps_lost_at']=s['seconds'];expire(s,t,'GPS unavailable')
    elif action=='GPS_RESTORE':t.pop('gps_lost_at',None)
    elif action=='CANCEL_REQUEST':
        if not p.get('reason','').strip():raise ValueError('Cancellation requires a reason')
        t['cancel_reason']=p['reason'];urgent(s,t,'CANCELLATION_REQUEST')
    elif action=='CANCEL':t['status']='CANCELLED';expire(s,t,'Cancellation confirmed')
    elif action=='REPLAN':
        points=p['route']['coordinates']
        if route_conflicts(s,points):raise ValueError('The replacement route intersects a current closure')
        expire(s,t,'Route replaced');t['old_coordinates']=t['coordinates'];t['old_eta_seconds']=t.get('eta_seconds')
        t.update(coordinates=points,route_source=p['route']['source'],route_expires_at=p['route'].get('expires_at'),position=list(points[0]),travelled_m=0,
            distance_m=sum(distance(a,b) for a,b in zip(points,points[1:])),plan=build_plan(points,p['_assets']),status='PENDING',
            plan_version=t['plan_version']+1,review_ready=s['seconds'],review_deadline=s['seconds']+60,limited_used=False,priority_hold=False,movement='NORMAL_NAVIGATION')
        if p.get('destination'):t['destination']=p['destination'];t['destination_position']=p['end']
        for entry in t['plan']:controller(s,entry)
    elif action=='HOLD_REPLAN':t['movement']='REPLANNING';t['priority_hold']=True;t['speed_mps']=0;expire(s,t,'Route calculation pending')
    elif action=='NO_ROUTE':t['priority_hold']=True;t['movement']='NO_ACCESSIBLE_ROUTE';t['speed_mps']=0;expire(s,t,'No accessible route');urgent(s,t,'NO_ACCESSIBLE_ROUTE')
    else:raise ValueError('Unknown emergency action')
    emit(s,'EMERGENCY_'+action,dict(trip_id=t['id'],actor=actor,reason=p.get('reason'),plan_version=t['plan_version']))

def tick(s,dt):
    w=world(s)
    for c in w['commands'].values():
        if c['status']=='PENDING' and c['expires']<=s['seconds']:c['status']='EXPIRED';emit(s,'COMMAND_EXPIRED',dict(command_id=c['id']))
    from scenario_runtime import effect
    from signal_operations import assets as signal_assets
    assets=signal_assets(s)
    from shapely.geometry import Polygon
    locations={a['id']:[a['longitude'],a['latitude']] for a in assets if a['kind']=='TRAFFIC_SIGNAL'}
    for j in w['controllers'].values():
        location=locations.get(j['id'])
        j['environment_failed']=bool(location and any(effect(z,s['seconds'])['signal_failed'] and Polygon(z['polygon']).covers(Point(location)) for z in s.get('scenarios',[])))
        allowed=green(s,j)
        for i in range(len(j['queues'])):j['queues'][i]=max(0,j['queues'][i]+j['arrivals'][i]*dt-(.5*dt if i in allowed else 0))
        if j['stage']=='GREEN':j['held_vehicle_seconds']+=sum(q for i,q in enumerate(j['queues']) if i not in allowed)*dt
        if j['stage']!='NORMAL' and s['seconds']>=j['until']:
            if j['stage']=='SENT' and (not j['online'] or j.get('environment_failed')):
                if j['attempts']<3:j['attempts']+=1;j['until']=s['seconds']+3
                else:
                    t=w['trips'].get(j['trip_id']);j.update(stage='NORMAL',verified_green=False,trip_id=None,retry_exhausted=True)
                    if t:urgent(s,t,'CONTROLLER_OFFLINE:'+j['id'])
                continue
            stages={'SENT':('PEDESTRIAN_CLEARANCE',max(7,10-((s['seconds']+j['offset'])%45))),'PEDESTRIAN_CLEARANCE':('AMBER',3),'AMBER':('ALL_RED',2),'ALL_RED':('GREEN',j.get('green_seconds',90)),'GREEN':('AMBER_RECOVERY',3),'AMBER_RECOVERY':('ALL_RED_RECOVERY',2),'ALL_RED_RECOVERY':('RECOVERY',8),'RECOVERY':('NORMAL',0)}
            previous=j['stage'];next_stage,seconds=stages[previous];j.update(stage=next_stage,until=s['seconds']+seconds,verified_green=next_stage=='GREEN' and j['online'] and not j.get('environment_failed'))
            emit(s,'CONTROLLER_'+next_stage,dict(junction_id=j['id'],trip_id=j['trip_id'],verified=j['verified_green']))
            if next_stage=='NORMAL':j['trip_id']=None
    detect_closures(s)
    trips=sorted(w['trips'].values(),key=lambda t:({'CRITICAL':0,'URGENT':1,'TRANSFER':2}[t['priority']],t['created']))
    for t in trips:
        if t['status'] in ('COMPLETED','CANCELLED'):
            t.update(speed_mps=0,movement='ARRIVED' if t['status']=='COMPLETED' else 'CANCELLED',eta_seconds=0 if t['status']=='COMPLETED' else None)
            t.pop('next_junction',None);continue
        if t['status']=='RECOVERING':
            if not any(j.get('trip_id')==t['id'] and j['stage']!='NORMAL' for j in w['controllers'].values()):t['status']='COMPLETED';emit(s,'EMERGENCY_COMPLETED',dict(trip_id=t['id']))
            continue
        t.pop('next_junction',None)
        upcoming=next((e for e in t['plan'] if e['distance_m']>t['travelled_m']),None)
        gps_age=s['seconds']-t['gps_lost_at'] if 'gps_lost_at' in t else 0
        if gps_age>15:urgent(s,t,'GPS_UNAVAILABLE')
        target=13.9 # Scenario assumption: 50 km/h ceiling, reduced by braking, turns and queues.
        if t.get('stopped') or t['movement'] in ('NO_ACCESSIBLE_ROUTE','REPLANNING') or gps_age>15:target=0
        a=point_at(t['coordinates'],t['travelled_m']);b=point_at(t['coordinates'],t['travelled_m']+15);c=point_at(t['coordinates'],t['travelled_m']+35)
        u=[b[i]-a[i] for i in (0,1)];v=[c[i]-b[i] for i in (0,1)]
        norm=sqrt(sum(x*x for x in u)*sum(x*x for x in v))
        if norm and sum(u[i]*v[i] for i in (0,1))/norm<.85:target=min(target,5.5)
        stop_distance=t['distance_m']-t['travelled_m']
        if upcoming:
            j=controller(s,upcoming);ahead=upcoming['distance_m']-t['travelled_m'];t['next_junction']=dict(**upcoming,eta_seconds=round(ahead/max(2,t['speed_mps']),1),stage=j['stage'],queue=round(j['queues'][upcoming['approach']],1))
            window=j['queues'][upcoming['approach']]/.5+12+ahead/max(2,t['speed_mps'])*.1
            authorized=t['status']=='APPROVED' or (t['status']=='PENDING' and t['priority']=='CRITICAL' and s['seconds']>=t['review_deadline'] and not t['limited_used'])
            if authorized and ahead/max(2,t['speed_mps'])<=window and not t['priority_hold'] and not t.get('stopped') and not gps_age:send(s,t,upcoming)
            if upcoming['approach'] not in green(s,j) or j['queues'][upcoming['approach']]>1:stop_distance=min(stop_distance,max(0,ahead-5))
        target=min(target,sqrt(max(0,2*2.5*stop_distance)))
        previous=t['speed_mps'];speed=max(target,previous-2.5*dt) if previous>target else min(target,previous+1.4*dt)
        move=min(stop_distance,max(0,(previous+speed)*.5*dt))
        t['travelled_m']=min(t['distance_m'],t['travelled_m']+move);t['speed_mps']=speed if move>0 else 0
        t['position']=point_at(t['coordinates'],t['travelled_m']);t['position_mode']='PREDICTED' if gps_age else 'SIMULATED'
        remaining=[e for e in t['plan'] if e['distance_m']>t['travelled_m']]
        signal_delay=0
        for e in remaining:
            cj=controller(s,e);signal_delay+=cj['queues'][e['approach']]/.5
            if e['approach'] not in green(s,cj):signal_delay+=max(0,cj['until']-s['seconds']) if cj['stage']!='NORMAL' else 45
        # Route-average speed assumption avoids dividing the whole journey by speed at a red light.
        t['eta_seconds']=None if t['movement'] in ('REPLANNING','NO_ACCESSIBLE_ROUTE') else round((t['distance_m']-t['travelled_m'])/11.1+signal_delay)
        t['eta_provenance']='MODEL: 40 km/h route average plus current queues and signal clearance; not a measured arrival time'
        if not t['history'] or s['seconds']-t['history'][-1]['seconds']>=5:t['history'].append(dict(seconds=s['seconds'],position=t['position'],speed_mps=t['speed_mps']))
        # History snapshots are archived in the shared event store; keep only a small live window.
        if len(t['history'])>120:emit(s,'AMBULANCE_TRACE',dict(trip_id=t['id'],samples=t['history'][:60]));t['history']=t['history'][60:]
        for entry in t['plan']:
            if entry['status']=='UPCOMING' and t['travelled_m']>=entry['distance_m']+3:
                entry['status']='PASSED';j=controller(s,entry)
                for command in w['commands'].values():
                    if command['trip_id']==t['id'] and command['junction_id']==entry['id'] and command['status']=='PENDING':
                        command['status']='EXPIRED';emit(s,'COMMAND_EXPIRED',dict(command_id=command['id'],reason='Ambulance passed'))
                if j.get('trip_id')==t['id']:
                    recover(s,j)
                    if t['status']=='PENDING':t['limited_used']=True;t['priority_hold']=True;urgent(s,t,'FURTHER_AUTHORIZATION_REQUIRED')
                emit(s,'AMBULANCE_PASSED',dict(trip_id=t['id'],junction_id=entry['id']))
        if t['distance_m']-t['travelled_m']<1:
            t.update(status='RECOVERING',speed_mps=0);expire(s,t,'Arrived at destination');emit(s,'AMBULANCE_ARRIVED',dict(trip_id=t['id']))


def detect_closures(s):
    from incident_engine import incident_engine
    import json
    from shapely.geometry import Polygon
    w=world(s)
    incidents=[i for i in list(incident_engine.active_incidents.values()) if i.get('status')=='ACTIVE' and i.get('incident_type') in ('ROAD_BLOCKAGE','ACCIDENT','WATERLOGGING')]
    from scenario_runtime import effect
    polygons=[z['polygon'] for z in s.get('scenarios',[]) if z.get('blocked') or effect(z,s['seconds'])['blocked']]
    signature=json.dumps([[(i['id'],i['lat'],i['lon']) for i in incidents],polygons],sort_keys=True)
    for t in w['trips'].values():
        if t['status'] in ('COMPLETED','CANCELLED','RECOVERING') or t['movement']=='REPLANNING' or t.get('closure_signature')==signature:continue
        t['closure_signature']=signature
        remaining=[point_at(t['coordinates'],t['travelled_m'])];n=0
        for a,b in zip(t['coordinates'],t['coordinates'][1:]):
            n+=distance(a,b)
            if n>t['travelled_m']:remaining.append(b)
        if len(remaining)<2:continue
        line=LineString(remaining)
        if any(line.distance(Point(i['lon'],i['lat']))<.0003 for i in incidents) or any(line.intersects(Polygon(p)) for p in polygons):
            expire(s,t,'Remaining route intersects a shared closure');t.update(movement='REPLANNING',priority_hold=True,speed_mps=0,status='PENDING',plan_version=t['plan_version']+1)
            urgent(s,t,'CORRIDOR_BLOCKED');emit(s,'EMERGENCY_REPLAN_REQUIRED',dict(trip_id=t['id'],reason='Shared incident or flood closure'))

def remaining_route(t):
    points=[point_at(t['coordinates'],t['travelled_m'])];n=0
    for a,b in zip(t['coordinates'],t['coordinates'][1:]):
        n+=distance(a,b)
        if n>t['travelled_m']:points.append(b)
    return points

def route_conflicts(s,points):
    if len(points)<2:return False
    from incident_engine import incident_engine
    from scenario_runtime import effect
    from shapely.geometry import Polygon
    line=LineString(points)
    closures=[b for b in world(s).get('blockages',{}).values() if not b.get('resolved')]+[i for i in incident_engine.active_incidents.values() if i.get('status')=='ACTIVE' and i.get('incident_type') in ('ROAD_BLOCKAGE','ACCIDENT','WATERLOGGING')]
    return any(line.distance(Point(b['lon'],b['lat']))<.0003 for b in closures) or any((z.get('blocked') or effect(z,s['seconds'])['blocked']) and line.intersects(Polygon(z['polygon'])) for z in s.get('scenarios',[]))

def delay_estimate(s,j,approach,hold):
    # Compare the same queue arrivals with and without priority, through one recovery cycle.
    # This is a model estimate, not an observed citywide delay or a guarantee.
    baseline=list(j['queues']);priority=list(j['queues']);extra=0
    horizon=int(min(600,hold+13+90));affected=[i for i in range(len(j['queues'])) if i!=approach]
    vehicles=sum(baseline[i]+j['arrivals'][i]*horizon for i in affected)
    for second in range(horizon):
        normal=normal_approaches(dict(seconds=s['seconds']+second),j)
        allowed=[] if second<13 else [approach] if second<13+hold else normal
        for i in range(len(j['queues'])):
            baseline[i]=max(0,baseline[i]+j['arrivals'][i]-(.5 if i in normal else 0))
            priority[i]=max(0,priority[i]+j['arrivals'][i]-(.5 if i in allowed else 0))
        extra+=sum(max(0,priority[i]-baseline[i]) for i in affected)
    return extra/max(1,vehicles)
