"""Map positions from committed operational state, never independent playback."""
from math import ceil
import metro_simulation as sim

def view(s):
    m=s['metro_v3'];net=sim.network;trains=[];turnbacks=[]
    from metro_engine import point_at
    for v in m['vehicles'].values():
        trip=sim.trip_for(m,v)
        if v['status']=='TURNBACK':
            jobs=m['plan']['jobs'].get(v['id'],[]);next_job=jobs[v['cursor']] if v['cursor']<len(jobs) else None
            following=(m['extras'].get(next_job['trip']) or net.trips[next_job['trip']]) if next_job else None
            turnbacks.append(dict(id='turnback:'+v['id'],block=v['id'],line_id=v['line'],station_id=v['station'],station=net.stations[v['station']]['name'],started_at_seconds=v['turnback_start'],ends_at_seconds=v['turnback_end'],remaining_seconds=max(0,v['turnback_end']-m['clock']),duration_seconds=m['config']['turnback_seconds'],next_departure_seconds=max(v['turnback_end'],next_job['start'])+(following['times'][0][2]-following['times'][0][1]) if following else None,next_trip_id=following['id'] if following else None,next_destination=following['headsign'] if following else 'Awaiting assignment',phase=v.get('turnback_phase','ENTERING_BAY'),crew_ready=v['crew_ready'],provenance='SIMULATED_REVERSING_OPERATION'))
            continue
        if not trip or v['status']=='IDLE':continue
        i=v['index'];a=trip['times'][i];b=trip['times'][min(i+1,len(trip['times'])-1)];progress=v['distance']/max(.01,v.get('segment_m',1)) if v['status']=='IN_TRANSIT' else 0
        distance=a[3]+(b[3]-a[3])*progress;shape=net.data['shapes'][trip['shape']]
        leg=[point_at(shape,a[3])]+[p[:2] for p in shape if a[3]<p[2]<b[3]]+[point_at(shape,b[3])]
        remaining=max(0,v['dwell_until']-m['clock']) if v['status']=='DWELLING' else max(0,v.get('segment_m',0)-v['distance'])/max(1,v['speed'])
        trains.append(dict(id=v['id'],block=v['id'],source_trip_id=trip['id'],line_id=v['line'],headsign=trip['headsign'],status=v['status'],
            from_station=net.data['stops'][a[0]]['name'],to_station=net.data['stops'][b[0]]['name'],position=point_at(shape,distance),
            progress=progress,seconds_to_next=round(remaining,1),speed_mps=v['speed'],segment_m=v.get('segment_m',0),geometry=leg,
            dwell_until=v['dwell_until'],motion='OPERATIONAL',passengers=sim.count(v['onboard']),capacity=m['config']['train_capacity'],
            delay_seconds=round(max(0,m['clock']-(a[2] if v['status']=='DWELLING' else a[2]+progress*(b[1]-a[2])))),
            pilot=v['pilot'],release=v['release'],crew_ready=v['crew_ready'],hold_until=v['hold_until'],shape_id=trip['shape'],
            schedule=[dict(station=net.data['stops'][x[0]]['name'],arrival=x[1]+v['shift'],departure=x[2]+v['shift']) for x in trip['times']],provenance='SIMULATED_OPERATING_STATE'))
    seconds=int(m['clock']);return dict(trains=trains,turnbacks=turnbacks,turnback_quality=dict(overlapping_trip_pairs=m['plan']['source_conflicts'],note='Source conflicts are resolved in the generated fleet assignment; source GTFS is retained.'),
        state=dict(running=s['running'],speed=s['speed'],sim_seconds=m['clock'],service_date=s['service_date']),clock=f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}',
        source=net.data['source_file'],station_count=len(net.stations),trip_count=sum(len(jobs) for jobs in m['plan']['jobs'].values()),
        note='Database operating model: platform boarding, finite fleet, dwell, acceleration/braking, track separation, turnbacks and approved commands. Simulated positions, not live GPS.',provenance='SIMULATED_OPERATING_STATE')
