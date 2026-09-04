"""Google Weather boundary. No fabricated measurements or simulator fallback."""
import os
import hashlib
import json
from datetime import timedelta
from database import supabase
from datetime import datetime, timezone
from threading import RLock
import httpx
from fastapi import APIRouter, Query
from core.api_usage_guard import usage_guard

router = APIRouter(prefix='/api/weather', tags=['Google Weather'])

def stamp():
    return datetime.now(timezone.utc).isoformat()

def value(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict): return None
        obj = obj.get(key)
    return obj

def normalize(raw, location, forecast=False):
    precipitation = raw.get('precipitation') or {}
    qpf = precipitation.get('qpf') or {}
    amount = qpf.get('quantity')
    if amount is not None and qpf.get('unit') != 'MILLIMETERS': amount = None
    return dict(source='GOOGLE_WEATHER', mode='LIVE', confidence=None,
        updatedAt=stamp(), observedAt=raw.get('currentTime'), location=location,
        forecast=forecast, interval=raw.get('interval'),
        temperatureC=value(raw,'temperature','degrees') if value(raw,'temperature','unit')=='CELSIUS' else None,
        feelsLikeC=value(raw,'feelsLikeTemperature','degrees') if value(raw,'feelsLikeTemperature','unit')=='CELSIUS' else None,
        condition=value(raw,'weatherCondition','description','text'),
        humidityPct=raw.get('relativeHumidity'),
        precipitation=dict(probabilityPct=value(precipitation,'probability','percent'),
            type=value(precipitation,'probability','type'), rateMmHr=None,
            accumulationMm=amount, accumulationPeriod='FORECAST_INTERVAL' if forecast else 'PROVIDER_PERIOD'),
        thunderstormProbabilityPct=raw.get('thunderstormProbability'),
        wind=dict(speedKph=value(raw,'wind','speed','value') if value(raw,'wind','speed','unit')=='KILOMETERS_PER_HOUR' else None,
            gustKph=value(raw,'wind','gust','value') if value(raw,'wind','gust','unit')=='KILOMETERS_PER_HOUR' else None,
            directionDeg=value(raw,'wind','direction','degrees')),
        visibilityKm=value(raw,'visibility','distance') if value(raw,'visibility','unit')=='KILOMETERS' else None,
        cloudCoverPct=raw.get('cloudCover'), seaLevelPressureHpa=value(raw,'airPressure','meanSeaLevelMillibars'),
        uvIndex=raw.get('uvIndex'), rawSource='Google Weather API')

class AegisDataOrchestrator:
    def __init__(self, guard=usage_guard, transport=httpx.get):
        self.guard, self.transport = guard, transport
        self.lock = RLock()
        self.cache = {}
        self.failures = {}

    def weather(self, lat, lng, hourly=False, name='Hyderabad'):
        location=dict(name=name,lat=lat,lng=lng)
        key=(round(lat,4),round(lng,4),hourly)
        now=datetime.now(timezone.utc).timestamp()
        with self.lock:
            cache_id=hashlib.sha256(json.dumps(key).encode()).hexdigest()
            cached=self.cache.get(key)
            if not cached or cached['expires']<=now:
                try:
                    rows=supabase.table('google_api_cache').select('response,expires_at').eq('id',cache_id).gt('expires_at',stamp()).limit(1).execute().data
                    if rows:
                        cached=dict(data=rows[0]['response'],expires=datetime.fromisoformat(rows[0]['expires_at']).timestamp())
                        self.cache[key]=cached
                except Exception:
                    return dict(source='GOOGLE_WEATHER',mode='UNAVAILABLE',confidence=None,updatedAt=stamp(),location=location,reason='CACHE_STORE_UNAVAILABLE')
            if cached and cached['expires']>now:
                return dict(cached['data'],cached=True)
            unavailable=dict(source='GOOGLE_WEATHER',mode='UNAVAILABLE',confidence=None,
                updatedAt=stamp(),location=location,lastSuccessfulAt=cached['data']['updatedAt'] if cached else None)
            if now < self.failures.get(key,0):
                return dict(unavailable,reason='PROVIDER_RETRY_BACKOFF')
            api_key=os.getenv('GOOGLE_MAPS_API_KEY','').strip()
            if os.getenv('GOOGLE_WEATHER_ENABLED','false').lower()!='true' or not api_key:
                return dict(unavailable,reason='GOOGLE_WEATHER_NOT_ENABLED')
            def external():
                endpoint='forecast/hours:lookup' if hourly else 'currentConditions:lookup'
                params={'location.latitude':lat,'location.longitude':lng,'unitsSystem':'METRIC','languageCode':'en'}
                if hourly: params.update(hours=24,pageSize=24)
                response=self.transport('https://weather.googleapis.com/v1/'+endpoint,
                    headers={'X-Goog-Api-Key':api_key},params=params,timeout=15,follow_redirects=False)
                if response.status_code!=200:
                    # Never return URLs, request headers, or raw Google errors containing credentials.
                    return dict(status='FAILED',reason='GOOGLE_WEATHER_HTTP_'+str(response.status_code))
                raw=response.json()
                if hourly:
                    rows=[normalize(r,location,True) for r in raw.get('forecastHours',[])]
                    if not rows: return dict(status='FAILED',reason='EMPTY_FORECAST')
                    return dict(source='GOOGLE_WEATHER',mode='LIVE',confidence=None,updatedAt=stamp(),hours=rows,location=location)
                if not raw.get('currentTime'): return dict(status='FAILED',reason='INVALID_CURRENT_RESPONSE')
                return normalize(raw,location)
            result=self.guard.attempt('GOOGLE_WEATHER',external)
            if result.get('mode')!='LIVE':
                self.failures[key]=now+60
                return dict(unavailable,reason=result.get('reason','PROVIDER_UNAVAILABLE'))
            ttl=900 if hourly else 300
            try:
                supabase.table('google_api_cache').upsert(dict(id=cache_id,service='WEATHER',request_hash=cache_id,
                    request_params=dict(lat=lat,lng=lng,hourly=hourly),response=result,fetched_at=stamp(),
                    expires_at=(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat())).execute()
            except Exception:
                self.failures[key]=now+60
                return dict(unavailable,reason='CACHE_WRITE_FAILED')
            self.cache[key]=dict(data=result,expires=now+ttl)
            return dict(result,cached=False)

orchestrator=AegisDataOrchestrator()

@router.get('/current')
def current(lat:float=Query(17.385,ge=17.05,le=17.85),lng:float=Query(78.4867,ge=78.05,le=78.95)):
    return orchestrator.weather(lat,lng)

@router.get('/hourly')
def hourly(lat:float=Query(17.385,ge=17.05,le=17.85),lng:float=Query(78.4867,ge=78.05,le=78.95)):
    return orchestrator.weather(lat,lng,True)

@router.get('/zones')
def zones():
    # Explicit configured coordinates only. Do not automatically spend on every generated asset.
    import json
    try: configured=json.loads(os.getenv('GOOGLE_WEATHER_ZONES','[]'))
    except ValueError: return dict(mode='UNAVAILABLE',reason='INVALID_ZONE_CONFIGURATION',zones=[])
    return dict(source='GOOGLE_WEATHER',zones=[orchestrator.weather(float(z['lat']),float(z['lng']),name=z['name']) for z in configured[:25]])
