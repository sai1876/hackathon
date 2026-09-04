"""Compiled GTFS network and explicit, versioned simulation assumptions."""
from collections import defaultdict
from datetime import date
from heapq import heappush, heappop
from bisect import bisect_left
from math import exp, hypot
from itertools import count

VERSION='metro-operations-v3'

def services_on(data, service_date):
    day=date.fromisoformat(service_date); key=day.strftime('%Y%m%d')
    field=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][day.weekday()]
    services={r['service_id'] for r in data.get('calendar',[]) if r['start_date']<=key<=r['end_date'] and str(r[field])=='1'}
    for r in data.get('calendar_dates',[]):
        if r['date']==key:
            if str(r['exception_type'])=='1':services.add(r['service_id'])
            else:services.discard(r['service_id'])
    return services

def defaults():
    return dict(version=VERSION,train_capacity=965,fleet_limit=57,max_speed_mps=80/3.6,
        acceleration_mps2=.85,braking_mps2=1.0,door_flow_people_sec=12,
        door_setup_seconds=5,min_dwell_seconds=20,max_dwell_seconds=90,
        min_headway_seconds=120,turnback_seconds=180,cab_change_seconds=120,
        turnback_move_seconds=30,turnback_bays=2,entry_walk_seconds=90,
        transfer_walk_seconds=180,exit_walk_seconds=60,platform_area_m2=500,
        interchange_platform_area_m2=750,platform_limit_people_m2=2.5,
        crowding_trigger=.65,max_wait_trigger_seconds=480,profile_mix=.45,
        station_daily_targets={},station_profile_overrides={},
        source='https://www.ltmetro.in/about-us/project-highlights/rolling-stock',
        provenance='SIMULATED_OPERATING_MODEL',
        note='Fleet ceiling, 3-car capacity and speed use published specifications. Demand, platform areas, door flow, acceleration, bay positions, walking and protection thresholds are adjustable simulation assumptions, not surveyed telemetry.')

class Network:
    def __init__(self,data,assets,profiles):
        self.data=data
        self.stations={k:v for k,v in data['stops'].items() if v.get('type')=='1'}
        self.asset_by_station={a['spec']['gtfs_stop_id']:a for a in assets if a['kind']=='METRO_STATION'}
        self.station_by_asset={v['id']:k for k,v in self.asset_by_station.items()}
        self.patterns={};self.graph=defaultdict(list);self.platforms={};self.paths={};self.plans={}
        self.trips={t['id']:t for t in data['trips']}
        for trip in data['trips']:
            if trip['shape'] in self.patterns:continue
            times=trip['times'];stops=[self.parent(t[0]) for t in times]
            self.patterns[trip['shape']]=dict(line=trip['route'],stops=stops,times=times,trip=trip)
            for i,(a,b) in enumerate(zip(stops,stops[1:])):
                self.graph[a].append((b,trip['shape'],max(10,times[i+1][1]-times[i][2])))
                key=a+'|'+trip['shape']
                self.platforms[key]=dict(id=key,station=a,line=trip['route'],shape=trip['shape'],towards=data['stops'][times[-1][0]]['name'])
        # Separate GTFS station IDs within one interchange complex require a walking link.
        if 'JBS' in self.stations and 'PRG' in self.stations:
            self.graph['JBS'].append(('PRG','WALK',180));self.graph['PRG'].append(('JBS','WALK',180))
        for origin in self.stations:self.compile_paths(origin)
        self.weights={};self.profile={}
        for p in profiles:
            sid=self.station_by_asset.get(p['asset_id'])
            if sid and p['kind'].startswith('passenger_entries_per_15min_'):self.profile[(sid,p['kind'].split('_')[-1])]=p['values']
        for a in assets:
            if a['kind']!='METRO_OD_MODEL':continue
            sid=self.station_by_asset.get(a['parent_id']);rows=[];total=0
            for d in a['spec']['destinations']:
                target=self.station_by_asset.get(d['station_id'])
                if (sid,target) in self.paths:
                    total+=d['probability'];rows.append((target,total))
            if rows:self.weights[sid]=[(t,w/total) for t,w in rows]

    def parent(self,stop):return self.data['stops'][stop].get('parent') or stop

    def compile_paths(self,origin):
        sequence=count();heap=[(0,next(sequence),origin,'',[])];seen={}
        while heap:
            cost,_,sid,shape,legs=heappop(heap)
            if (sid,shape) in seen:continue
            seen[sid,shape]=cost
            if sid!=origin and (origin,sid) not in self.paths:self.paths[origin,sid]=legs
            for target,direction,seconds in self.graph[sid]:
                transfer=180 if shape and shape!=direction and direction!='WALK' else 0
                if direction=='WALK':new=legs+[dict(board=sid,alight=target,shape='WALK')]
                elif legs and legs[-1]['shape']==direction:new=legs[:-1]+[{**legs[-1],'alight':target}]
                else:new=legs+[dict(board=sid,alight=target,shape=direction)]
                heappush(heap,(cost+seconds+transfer,next(sequence),target,direction,new))

    def destination(self,sid,sequence):
        choices=self.weights.get(sid)
        if not choices:choices=[(d,(i+1)/len(self.stations)) for i,d in enumerate(self.stations) if (sid,d) in self.paths]
        if not choices:return None
        # Seeded low-discrepancy stream: deterministic replay, not browser randomness.
        x=((sequence+1)*.6180339887498949+sum(map(ord,sid))*.137)%1
        return choices[min(len(choices)-1,bisect_left([p[1] for p in choices],x))][0]

    def demand_profiles(self,config):
        output={}
        for (sid,day),source in self.profile.items():
            override=config['station_profile_overrides'].get(sid+'|'+day)
            if override is not None:output[sid+'|'+day]=override;continue
            total=config['station_daily_targets'].get(sid+'|'+day,sum(source))
            mixed=[];active=[i for i in range(96) if 6<=i/4<23]
            # Preserve daily totals while avoiding the previous near-zero midday trough.
            for i,v in enumerate(source):
                hour=i/4;uniform=total/len(active) if i in active else 0
                mixed.append((1-config['profile_mix'])*v+config['profile_mix']*uniform)
            scale=total/max(1,sum(mixed));output[sid+'|'+day]=[v*scale for v in mixed]
        return output

    def plan(self,service_date,config):
        key=(service_date,config['fleet_limit'],config['turnback_seconds'])
        if key in self.plans:return self.plans[key]
        active=services_on(self.data,service_date)
        source=sorted([t for t in self.data['trips'] if t['service'] in active and len(t['times'])>1],key=lambda t:(t['times'][0][1],t['id']))
        fleets=[];jobs=defaultdict(list);shifted=[];rejected=[];overlaps=0;source_end={}
        lines=sorted({t['route'] for t in source})
        # Reserve one explicitly modelled train/crew per line inside the total fleet limit.
        for line in lines:
            t=next(t for t in source if t['route']==line)
            fleets.append(dict(id=f'TRAIN-{len(fleets)+1:03}',line=line,station=self.parent(t['times'][0][0]),available=0,reserve=True))
        for trip in source:
            start=trip['times'][0][1];terminal=self.parent(trip['times'][0][0]);last=self.parent(trip['times'][-1][0])
            if start<source_end.get(trip['block'],0):overlaps+=1
            source_end[trip['block']]=max(source_end.get(trip['block'],0),trip['times'][-1][2])
            options=[f for f in fleets if not f['reserve'] and f['line']==trip['route'] and f['station']==terminal]
            ready=[f for f in options if f['available']<=start]
            if ready:f=min(ready,key=lambda x:x['available'])
            elif len(fleets)<config['fleet_limit']:
                f=dict(id=f'TRAIN-{len(fleets)+1:03}',line=trip['route'],station=terminal,available=0,reserve=False);fleets.append(f)
            elif options:f=min(options,key=lambda x:x['available'])
            else:rejected.append(dict(trip=trip['id'],reason='NO_COMPATIBLE_VEHICLE_AT_ORIGIN'));continue
            shift=max(0,f['available']-start)
            if shift:shifted.append(dict(trip=trip['id'],delay_seconds=shift))
            jobs[f['id']].append(dict(trip=trip['id'],shift=shift,start=start+shift,end=trip['times'][-1][2]+shift))
            f['available']=trip['times'][-1][2]+shift+config['turnback_seconds'];f['station']=last
        # Initial vehicle locations come from their first service, not their final schedule.
        for f in fleets:
            if jobs[f['id']]:f['station']=self.parent(self.trips[jobs[f['id']][0]['trip']]['times'][0][0])
        result=dict(jobs=dict(jobs),fleet=fleets,source_conflicts=overlaps,retimed=shifted,unassigned=rejected,
                    service_ids=sorted(active),last_seconds=max([j['end']+config['turnback_seconds'] for rows in jobs.values() for j in rows]+[86400]),
                    provenance='GENERATED_FEASIBLE_ASSIGNMENT_FROM_GTFS')
        self.plans[key]=result;return result

    def segment_metres(self,trip,index):
        shape=self.data['shapes'][trip['shape']];a,b=trip['times'][index][3],trip['times'][index+1][3]
        from metro_engine import point_at
        points=[point_at(shape,a)]+[p[:2] for p in shape if a<p[2]<b]+[point_at(shape,b)]
        return sum(111195*hypot((q[0]-p[0])*.955,q[1]-p[1]) for p,q in zip(points,points[1:]))
