"""One coordinated request per executable operation, with station evidence."""
from uuid import uuid4
import metro_simulation as sim

OPEN=('PENDING','APPROVED','ACKNOWLEDGED')

def evaluate(s,m):
    evidence=[];clock=m['clock']
    for sid,st in m['stations'].items():
        for pid,q in st['platforms'].items():
            waiting=sim.count(q)
            # Missing pre-upgrade queue timestamps start at this migration, not
            # at the passenger's original journey departure time.
            for c in q:c.setdefault('queued_at',clock)
            oldest=clock-min([c['queued_at'] for c in q]+[clock]);capacity=sim.platform_area(m,pid)*m['config']['platform_limit_people_m2']
            if waiting<capacity*m['config']['crowding_trigger'] and (waiting<20 or oldest<m['config']['max_wait_trigger_seconds']):continue
            p=sim.network.platforms[pid];env=m.get('environment',{}).get(sid,{})
            evidence.append(dict(station=sid,station_name=sim.network.stations[sid]['name'],platform=pid,line=p['line'],towards=p['towards'],waiting=waiting,oldest_wait_seconds=round(oldest),capacity=round(capacity),rain_mm_hour=env.get('rain',0),demand_factor=env.get('demand',1),access_closed=env.get('access_closed',False),power_failed=env.get('power_failed',False),cause_ids=env.get('cause_ids',[])))
    candidates={}
    for e in evidence:
        if e['access_closed'] or e['power_failed']:continue
        reserve=next((v for v in m['vehicles'].values() if v['reserve'] and v['status']=='IDLE' and v['line']==e['line'] and v['station']==e['station']),None)
        # An extra train is not a proportionate response to a handful of people.
        if reserve and e['waiting']>=100:
            key='EXTRA_SERVICE:'+reserve['id'];candidates.setdefault(key,dict(action='EXTRA_SERVICE',vehicle=reserve['id'],value=0,evidence=[]))['evidence'].append(e)
        elif m['config']['min_headway_seconds']>90:
            candidates.setdefault('HEADWAY:NETWORK',dict(action='HEADWAY',vehicle=None,value=90,evidence=[]))['evidence'].append(e)
    groups={}
    for d in m['decisions']:
        if d['status'] in OPEN and clock>=d['expires']:d['status']='EXPIRED'
        if d.get('source')!='DETERMINISTIC_RULE_AGENT' or d['status'] not in OPEN:continue
        key=d['action']+(':'+str(d.get('vehicle')) if d['action']=='EXTRA_SERVICE' else ':NETWORK')
        groups.setdefault(key,[]).append(d)
    for key,rows in groups.items():
        rows.sort(key=lambda d:(d['status']=='PENDING',d['created']))
        for duplicate in rows[1:]:
            if duplicate['status']=='PENDING':
                duplicate.update(status='SUPERSEDED',superseded_by=rows[0]['id']);sim.log(s,'RECOMMENDATION_CONSOLIDATED',dict(id=duplicate['id'],retained=rows[0]['id']))
        if key not in candidates and rows[0]['status']=='PENDING':rows[0].update(status='WITHDRAWN',response='Current platform demand no longer supports this request')
    for key,c in candidates.items():
        existing=next((d for d in groups.get(key,[]) if d['status'] in OPEN),None)
        if existing and existing['status']!='PENDING':continue # Never alter an approved instruction.
        if not existing and any(d.get('coordination_key')==key and d['status'] in ('REJECTED','APPLIED') and clock-d.get('reviewed_at',d.get('applied_at',d['created']))<600 for d in m['decisions']):continue
        es=c['evidence'];names=list(dict.fromkeys(e['station_name'] for e in es));waiting=sum(e['waiting'] for e in es)
        reasons=[f"{e['station_name']} ({e['line']} toward {e['towards']}): {e['waiting']} waiting, oldest platform wait {round(e['oldest_wait_seconds']/60,1)} min"+ (f", shared rainfall {e['rain_mm_hour']} mm/h" if e['rain_mm_hour'] else '')+(f", demand {e['demand_factor']:.2f}×" if e['demand_factor']>1 else '') for e in es]
        proposed=f"Reduce the network minimum dispatch separation from {m['config']['min_headway_seconds']} to 90 seconds, subject to occupied-track clearance." if c['action']=='HEADWAY' else f"Dispatch available reserve {c['vehicle']} from {names[0]}; verify its return slot before Apply."
        update=dict(coordination_key=key,title=('Network headway review' if c['action']=='HEADWAY' else 'Extra service · '+names[0]),evidence=es,stations=names,reason=proposed+' '+'; '.join(reasons)+'.',cause_ids=list(dict.fromkeys(x for e in es for x in e['cause_ids'])),waiting_total=waiting,reviewed_at=clock)
        if existing:existing.update(update)
        else:
            d=dict(id=str(uuid4()),platform=es[0]['platform'],station=es[0]['station'],action=c['action'],vehicle=c['vehicle'],value=c['value'],status='PENDING',created=clock,expires=clock+600,source='DETERMINISTIC_RULE_AGENT',**update)
            m['decisions'].append(d);sim.log(s,'RECOMMENDATION_CREATED',d)
    # Keep open decisions even when historical audit entries exceed the UI window.
    closed=[d for d in m['decisions'] if d['status'] not in OPEN][-80:]
    m['decisions']=closed+[d for d in m['decisions'] if d['status'] in OPEN]
