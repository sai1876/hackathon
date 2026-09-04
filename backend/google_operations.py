"""Server-only Google integrations; paid calls are explicit and quota guarded."""
import os
from datetime import datetime, timezone
from threading import RLock
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal
from core.api_usage_guard import usage_guard
from shapely.geometry import LineString, Point, Polygon

router=APIRouter(prefix='/api',tags=['Google operations'])
lock=RLock()

class Location(BaseModel):
    lat:float=Field(ge=17.05,le=17.85,allow_inf_nan=False)
    lng:float=Field(ge=78.05,le=78.95,allow_inf_nan=False)
    def google(self):return dict(latitude=self.lat,longitude=self.lng)

class RouteInput(BaseModel):
    origin:Location
    destination:Location

class MatrixInput(BaseModel):
    origins:list[Location]=Field(min_length=1,max_length=5)
    destinations:list[Location]=Field(min_length=1,max_length=5)

class PointsInput(BaseModel):
    points:list[Location]=Field(min_length=1,max_length=100)

class PlacesInput(Location):
    category:Literal['hospital','police','fire_station','transit_station']='hospital'
    radius_m:int=Field(default=3000,ge=100,le=10000)

def meta(source,mode='LIVE'):
    return dict(source=source,mode=mode,updatedAt=datetime.now(timezone.utc).isoformat(),confidence=None)

def call(service,url,body=None,params=None,fields=None,units=1):
    key=os.getenv('GOOGLE_MAPS_API_KEY','').strip()
    if not key:return dict(**meta('GOOGLE_'+service,'UNAVAILABLE'),reason='BACKEND_KEY_MISSING')
    # Matrix billing is per element. Reserve every element before making one request.
    with lock:
        for _ in range(units):
            budget=usage_guard.budget(service,True)
            if not budget.get('allowed'):return dict(**meta('GOOGLE_'+service,'UNAVAILABLE'),reason='USAGE_LIMIT_OR_STORE_UNAVAILABLE')
        headers={'X-Goog-Api-Key':key}
        if url.startswith('https://maps.googleapis.com/') or url.startswith('https://roads.googleapis.com/'):
            params=dict(params or {},key=key)
        if fields:headers['X-Goog-FieldMask']=fields
        try:
            if body is None:r=httpx.get(url,params=params,headers=headers,timeout=20,follow_redirects=False)
            else:r=httpx.post(url,json=body,headers=headers,timeout=20,follow_redirects=False)
            data=r.json()
            if r.status_code!=200:
                reasons=[d.get('reason') for d in data.get('error',{}).get('details',[]) if d.get('reason')]
                return dict(**meta('GOOGLE_'+service,'UNAVAILABLE'),reason=reasons[0] if reasons else 'HTTP_'+str(r.status_code))
            if isinstance(data,dict) and data.get('status') not in (None,'OK','ZERO_RESULTS'):
                return dict(**meta('GOOGLE_'+service,'UNAVAILABLE'),reason=data['status'])
            return dict(**meta('GOOGLE_'+service),data=data)
        except Exception:return dict(**meta('GOOGLE_'+service,'UNAVAILABLE'),reason='PROVIDER_REQUEST_FAILED')

def decode(encoded):
    points=[];index=lat=lng=0
    while index<len(encoded):
        values=[]
        for _ in range(2):
            result=shift=0
            while True:
                b=ord(encoded[index])-63;index+=1;result|=(b&31)<<shift;shift+=5
                if b<32:break
            values.append(~(result>>1) if result&1 else result>>1)
        lat+=values[0];lng+=values[1];points.append([lng/1e5,lat/1e5])
    return points

def conflicts(points):
    from incident_engine import incident_engine
    import weather_effects
    if len(points)<2:return ['INVALID_ROUTE_GEOMETRY']
    line=LineString(points)
    found=[]
    for incident in list(incident_engine.active_incidents.values()):
        if incident.get('status')=='ACTIVE' and incident.get('incident_type') in ('ROAD_BLOCKAGE','ACCIDENT','WATERLOGGING'):
            if line.distance(Point(incident['lon'],incident['lat']))<.0003:found.append(incident['id'])
    for zone in getattr(weather_effects,'shared_zones',[]):
        if zone.get('blocked') and zone.get('polygon') and line.intersects(Polygon(zone['polygon'])):found.append(zone.get('id','FLOOD_AREA'))
    return found

@router.post('/routes/compute')
def compute(p:RouteInput):
    result=call('ROUTES','https://routes.googleapis.com/directions/v2:computeRoutes',body={
        'origin':{'location':{'latLng':p.origin.google()}},'destination':{'location':{'latLng':p.destination.google()}},
        'travelMode':'DRIVE','routingPreference':'TRAFFIC_AWARE','computeAlternativeRoutes':False},
        fields='routes.distanceMeters,routes.duration,routes.staticDuration,routes.polyline.encodedPolyline,routes.legs')
    if result['mode']=='UNAVAILABLE':return result
    rows=result['data'].get('routes',[])
    if not rows:return dict(**meta('GOOGLE_ROUTES','UNAVAILABLE'),reason='NO_ROUTE')
    row=rows[0];points=decode(row['polyline']['encodedPolyline'])
    blocked=conflicts(points)
    base=float(row['staticDuration'].removesuffix('s'));traffic=float(row['duration'].removesuffix('s'))
    return dict(**meta('GOOGLE_ROUTES','DERIVED'),distanceM=row['distanceMeters'],normalDurationSec=base,
        trafficDurationSec=traffic,trafficRatio=traffic/base if base else None,polyline=row['polyline']['encodedPolyline'],
        coordinates=points,legs=row.get('legs',[]),conflicts=blocked,operationallyUsable=not blocked,
        safetyNote='Local incident proximity and flood polygons checked. Not a guarantee of road access. Traffic approval is required.',
        displayPolicy='GOOGLE_MAP_ONLY',affectedJunctionsMode='UNAVAILABLE')

@router.post('/routes/matrix')
def matrix(p:MatrixInput):
    return call('ROUTES','https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix',body={
        'origins':[{'waypoint':{'location':{'latLng':x.google()}}} for x in p.origins],
        'destinations':[{'waypoint':{'location':{'latLng':x.google()}}} for x in p.destinations],
        'travelMode':'DRIVE','routingPreference':'TRAFFIC_AWARE'},
        fields='originIndex,destinationIndex,status,condition,distanceMeters,duration,staticDuration',units=len(p.origins)*len(p.destinations))

@router.post('/roads/snap')
def snap(p:PointsInput):
    return call('ROADS','https://roads.googleapis.com/v1/snapToRoads',params={
        'path':'|'.join(f'{x.lat},{x.lng}' for x in p.points),'interpolate':'true'})

@router.post('/roads/nearest')
def nearest(p:PointsInput):
    return call('ROADS','https://roads.googleapis.com/v1/nearestRoads',params={
        'points':'|'.join(f'{x.lat},{x.lng}' for x in p.points)})

@router.post('/elevation/lookup')
def elevation(p:PointsInput):
    return call('ELEVATION','https://maps.googleapis.com/maps/api/elevation/json',params={
        'locations':'|'.join(f'{x.lat},{x.lng}' for x in p.points)})

@router.post('/places/nearby')
def places(p:PlacesInput):
    return call('PLACES','https://places.googleapis.com/v1/places:searchNearby',body={
        'includedTypes':[p.category],'maxResultCount':10,
        'locationRestriction':{'circle':{'center':p.google(),'radius':p.radius_m}}},
        fields='places.id,places.displayName,places.location,places.formattedAddress')

@router.post('/geocoding/reverse')
def reverse(p:Location):
    return call('GEOCODING','https://maps.googleapis.com/maps/api/geocode/json',params={'latlng':f'{p.lat},{p.lng}'})
