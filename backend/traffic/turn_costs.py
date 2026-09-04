"""Turn direction is derived from oriented edge tangents, not node identifiers."""
from math import atan2, sin, cos, radians, degrees
from endpoint_snapping import directed_geometry

def bearing(a,b):
    lat1,lat2=radians(a[1]),radians(b[1]); dl=radians(b[0]-a[0])
    return degrees(atan2(sin(dl)*cos(lat2),cos(lat1)*sin(lat2)-sin(lat1)*cos(lat2)*cos(dl)))%360

def classify(delta):
    angle=abs(delta)
    if angle<15: return 'straight'
    if angle<40: return 'slight'
    if angle>=165: return 'u_turn'
    if angle>=125: return 'sharp'
    return 'right' if delta>0 else 'left'

def prepare_bearings(graph):
    for u,v,k,d in graph.edges(keys=True,data=True):
        geom=directed_geometry(graph,u,v,d['geometry']); coords=list(geom.coords)
        first=next((p for p in coords[1:] if p!=coords[0]),coords[-1])
        last=next((p for p in reversed(coords[:-1]) if p!=coords[-1]),coords[0])
        d['entry_bearing']=bearing(coords[0],first); d['exit_bearing']=bearing(last,coords[-1])

def turn_cost(graph,previous,current,config):
    if previous is None: return 0,'straight'
    incoming=graph.edges[previous]; outgoing=graph.edges[current]
    delta=(outgoing['entry_bearing']-incoming['exit_bearing']+180)%360-180
    kind=classify(delta)
    penalty=config['turn_sec'][kind]
    if outgoing['road_class']=='service' and incoming['road_class']!='service': penalty+=config['service_transition_sec']
    if incoming['road_class'] in ('motorway','trunk','primary') and outgoing['road_class'] in ('residential','service'): penalty+=config['minor_transition_sec']
    # Unique outgoing neighbors, not parallel directed edges.
    penalty+=max(0,len(set(graph.successors(current[0])))-2)*config['junction_branch_sec']
    return penalty,kind
