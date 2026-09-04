"""Edge costs in seconds; preference penalties are kept separate from modeled ETA."""
from math import isfinite, inf

def road_class(data):
    value=data.get('road_class') or 'unknown'
    if isinstance(value,list): value=value[0] if value else 'unknown'
    return str(value).removesuffix('_link')
def prepare_edge(data, config):
    closed=not isfinite(data.get('current_cost',0)) or data.get('blocked') or data.get('status') in ('CLOSED','IMPASSABLE') or data.get('access') in ('no','private')
    length=max(0,float(data.get('length_m') or 0))
    base=float(data.get('base_speed_kph') or data.get('free_flow_speed_kmph') or 0)
    if base<=0:
        base=length/max(.01,float(data.get('base_travel_time_sec') or 1))*3.6
    traffic=data.get('traffic_speed_kph')
    base=max(.1,base*config['free_flow_multiplier'])
    speed=base if traffic is None else max(0,float(traffic))
    incident=max(0,min(1,float(data.get('incident_factor',1))))
    environment=max(0,min(1,float(data.get('environment_factor',1))))
    # Existing synthetic rainfall is translated once, not multiplied into time twice.
    environment/=max(1,float(data.get('synthetic_rain_delay_factor',1)))
    effective=speed*incident*environment
    if effective<=0: closed=True
    travel=inf if closed else length/(effective/3.6)
    queue=max(0,float(data.get('queue_delay_sec',0)))
    signal=max(0,float(data.get('signal_delay_sec',config['signal_delay_sec'] if data.get('signalized') else 0)))
    preference=length/1000*config['road_class_per_km'].get(road_class(data),config['road_class_per_km']['unclassified'])
    access=max(0,float(data.get('access_penalty_sec',0)))
    cost=travel+queue+signal+preference+access
    data.update(length_m=length,base_speed_kph=base,traffic_speed_kph=traffic,road_class=road_class(data),oneway=data.get('oneway'),lanes=data.get('lanes'),incident_factor=incident,environment_factor=environment,capacity_factor=data.get('capacity_factor',1),queue_delay_sec=queue,signal_delay_sec=signal,turn_penalty_sec=0,road_class_penalty_sec=preference,access_penalty_sec=access,travel_time_sec=travel,modeled_eta_sec=travel+queue+signal,current_cost_sec=cost,current_cost=cost,status='IMPASSABLE' if closed else 'DRIVABLE',provenance={'topology':data.get('provenance','REAL'),'cost':'CALIBRATED','traffic':'UNAVAILABLE' if traffic is None else data.get('traffic_provenance','DERIVED')})
    return data
