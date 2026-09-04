"""Manual reference comparison. No Google topology, polylines or raw responses on disk."""
import json, os, secrets
from pathlib import Path
from threading import RLock
from time import monotonic, perf_counter
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from models import RouteRequest, Coordinate
from route_engine import route_engine
from providers.google.routes_provider import google_routes
from core.api_usage_guard import usage_guard
from traffic.routing_config import config_store, validate, BOUNDS
router=APIRouter()
lock=RLock(); snapshots={}
PAIRS=json.loads((Path(__file__).parent/'calibration_pairs.json').read_text())
def compare(aegis,google):
    started=perf_counter()
    distance=(aegis['distance_m']-google['distance_m'])/max(1,google['distance_m'])*100
    eta=(aegis['eta_seconds']-google['duration_sec'])/max(1,google['duration_sec'])*100
    level=max(abs(distance),abs(eta))
    moderate=float(os.getenv('CALIBRATION_MODERATE_PERCENT','15')); high=float(os.getenv('CALIBRATION_HIGH_PERCENT','35'))
    diagnostics=[]; mix=aegis.get('road_class_mix',{})
    if level>=high:
        if mix.get('residential',0)>35: diagnostics.append('High residential-road share in Aegis; inspect local-road preference')
        if mix.get('service',0)>15: diagnostics.append('High service-road share in Aegis')
        if aegis.get('turn_count',0)/max(.1,aegis['distance_m']/1000)>6: diagnostics.append('Many turns per kilometre; inspect junction topology')
        if abs(eta)>=high: diagnostics.append('Review free-flow estimates and modeled delays; Google is a different model')
        if abs(distance)>=high: diagnostics.append('Inspect topology, road-class weighting and missing turn restrictions')
    return dict(status='HIGH_MISMATCH' if level>=high else 'MODERATE_MISMATCH' if level>=moderate else 'GOOD_MATCH',aegis_distance_m=aegis['distance_m'],google_distance_m=google['distance_m'],distance_difference_percent=round(distance,2),aegis_eta_sec=aegis['eta_seconds'],google_eta_sec=google['duration_sec'],eta_difference_percent=round(eta,2),road_class_mix=mix,turn_count=aegis.get('turn_count'),local_road_usage=mix.get('residential',0),service_road_usage=mix.get('service',0),diagnostics=diagnostics,route_overlap=None,calibration_analysis_ms=round((perf_counter()-started)*1000,2),note='Does not infer Google road-class mix; comparison is against provider estimates')
class FetchRequest(BaseModel):
    pair_ids:list[str]=Field(min_length=1,max_length=5)
    approved:bool=False
class Approval(BaseModel):
    approved:bool=False
    operator:str=Field(min_length=2,max_length=100)
    evidence:str=Field(min_length=8,max_length=2000)
    version:int=Field(ge=0)
    parameters:dict=Field(default_factory=dict)
def authorize(approved,token):
    expected=os.getenv('AEGIS_OPERATOR_TOKEN','')
    if not expected: raise HTTPException(503,'Configure AEGIS_OPERATOR_TOKEN on the backend to enable operator actions')
    if not token or not secrets.compare_digest(token,expected): raise HTTPException(403,'Operator token required')
    if not approved: raise HTTPException(422,'Explicit operator approval required')
def run_pair(pair):
    with lock:
        started=perf_counter()
        from main import runtime_lock
        with runtime_lock:
            aegis=route_engine.calculate_route(RouteRequest(start=Coordinate(**pair['origin']),end=Coordinate(**pair['destination']),alternatives=3))
        google=google_routes.fetch(pair['origin'],pair['destination'])
        result=dict(pair_id=pair['id'],origin=pair['origin'],destination=pair['destination'],aegis={k:aegis[k] for k in ['distance_m','eta_seconds','road_class_mix','turn_count','overall_score']},google=google,comparison=compare(aegis,google) if google.get('status')=='AVAILABLE' else None,timestamp=datetime.now(timezone.utc).isoformat(),provenance={'aegis':'CALIBRATED','google':'REAL' if google.get('status')=='AVAILABLE' else 'UNAVAILABLE'},total_ms=round((perf_counter()-started)*1000,2),retention='Transient process memory, 1 hour; no persistent Google metrics or geometry')
        snapshots[pair['id']]=(monotonic(),result)
        return result
@router.get('/system/api-usage')
def budget(): return usage_guard.snapshot()
@router.get('/calibration/pairs')
def pairs(): return dict(pairs=PAIRS)
@router.get('/calibration/config')
def config(): return {**config_store.snapshot(),'bounds':BOUNDS}
@router.get('/calibration/snapshots')
def read_snapshots():
    with lock:
        for key in list(snapshots):
            if monotonic()-snapshots[key][0]>3600: del snapshots[key]
        return dict(snapshots=[v[1] for v in snapshots.values()],note='Reading snapshots never calls Google; transient references expire after one hour')
@router.post('/calibration/google/fetch')
def fetch(request:FetchRequest,x_aegis_operator_token:str|None=Header(default=None)):
    authorize(request.approved,x_aegis_operator_token)
    selected={p['id']:p for p in PAIRS}
    if any(key not in selected for key in request.pair_ids): raise HTTPException(422,'Unknown calibration pair')
    return dict(results=[run_pair(selected[key]) for key in dict.fromkeys(request.pair_ids)])
@router.post('/calibration/google/fetch/{pair_id}')
def fetch_one(pair_id:str,request:FetchRequest,x_aegis_operator_token:str|None=Header(default=None)):
    return fetch(FetchRequest(pair_ids=[pair_id],approved=request.approved),x_aegis_operator_token)
@router.post('/calibration/apply')
def apply(request:Approval,x_aegis_operator_token:str|None=Header(default=None)):
    authorize(request.approved,x_aegis_operator_token)
    try:
        validate(request.parameters)
        return config_store.change(request.parameters,request.version,request.operator,request.evidence)
    except ValueError as e: raise HTTPException(422,str(e))
    except Exception: raise HTTPException(409,'Configuration update failed or version changed; review current settings')
@router.post('/calibration/revert')
def revert(request:Approval,x_aegis_operator_token:str|None=Header(default=None)):
    authorize(request.approved,x_aegis_operator_token)
    try: return config_store.change({},request.version,request.operator,request.evidence,True)
    except Exception: raise HTTPException(409,'No calibration to revert, database unavailable, or version changed')
