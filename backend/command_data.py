"""Database-backed command view. Missing records never fall back to exercise data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from fastapi import APIRouter, HTTPException, Query
from shapely import wkt, wkb
from shapely.geometry import mapping
from database import supabase
from shared_simulation import inventory as simulation_inventory

router = APIRouter(prefix="/command", tags=["Database command center"])
TABLES = ["junctions", "signal_groups", "traffic_signal_state", "road_segments", "substations", "feeders", "transformers", "transformer_state", "feeder_state", "traffic_state", "rainfall_state", "metro_stations", "metro_train_state", "incidents", "system_actions", "event_log", "scenario_controls", "simulation_runs"]
_cache = None
_cache_time = 0
_lock = Lock()

def read_table(table):
    for attempt in range(2):
        try:
            response = supabase.table(table).select("*", count="exact").limit(1).execute()
            return dict(table=table, count=response.count, status="AVAILABLE" if response.count else "EMPTY")
        except Exception:
            if attempt:
                return dict(table=table, count=None, status="UNAVAILABLE")

@router.get("/snapshot")
def snapshot():
    global _cache, _cache_time
    with _lock:
        if _cache is not None and monotonic() - _cache_time < 15:
            return _cache
        with ThreadPoolExecutor(max_workers=5) as pool:
            tables = list(pool.map(read_table, TABLES))
        try:
            sources = supabase.table("data_sources").select("source_name,source_type,provenance,provider,created_at").limit(100).execute().data
        except Exception:
            sources = []
        _cache = dict(tables=tables, sources=sources, checked_at=datetime.now(timezone.utc).isoformat(),
            source="Supabase database", mode="DATABASE_ONLY", scenario_ready=False,
            scenario_reason="Verified electrical assets, current measurements and calibrated cross-system parameters are not configured. No generated fallback is used.")
        _cache_time = monotonic()
        return _cache

@router.get("/roads")
def roads(west: float = Query(ge=78.05, le=78.95), south: float = Query(ge=17.05, le=17.85),
          east: float = Query(ge=78.05, le=78.95), north: float = Query(ge=17.05, le=17.85)):
    if west >= east or south >= north:
        raise HTTPException(422, "Invalid map bounds")
    try:
        if east - west > .08 or north - south > .08:
            raise HTTPException(422, "Zoom in to load road detail")
        records = []
        for offset in range(0, 10000, 1000):
            batch = supabase.rpc("get_roads_in_bbox_paged", dict(min_lon=west,min_lat=south,max_lon=east,max_lat=north,p_limit=1000,p_offset=offset)).execute().data or []
            records.extend(batch)
            if len(batch) < 1000:
                break
        features = []
        for row in records:
            if row.get("provenance") not in (None, "REAL"):
                continue
            raw = row.get("geometry_wkt") or row["geometry"]
            geom = wkt.loads(raw) if "LINESTRING" in raw.upper() else wkb.loads(bytes.fromhex(raw))
            features.append(dict(type="Feature", geometry=mapping(geom), properties=dict(id=row.get("external_id",row.get("id")), name=row.get("road_name"), provenance=row.get("provenance", "SOURCE_RECORD"), **scenario_road_effect(geom))))
        return dict(type="FeatureCollection",features=features,metadata=dict(limit=10000,returned=len(features),truncated=len(records)>=10000,source="Supabase road_segments",coverage="Visible map area",traffic_status="UNKNOWN"))
    except Exception:
        raise HTTPException(503, "Database road geometry is unavailable")


_signals_cache = None
_signals_time = 0
_signals_lock = Lock()

def signal_locations():
    """Mapped assets only; a location does not establish an operating phase."""
    global _signals_cache, _signals_time
    with _signals_lock:
        if _signals_cache is not None and monotonic() - _signals_time < 60:
            return _signals_cache
        try:
            records = []
            offset = 0
            while True:
                batch = supabase.table("junctions").select("id,external_id,name,location,junction_type,provenance,metadata").in_("junction_type", ["TRAFFIC_SIGNAL", "TRAFFIC_SIGNAL_REFERENCE"]).order("id").range(offset, offset + 499).execute().data or []
                records.extend(batch)
                if len(batch) < 500:
                    break
                offset += 500
            features, unresolved = [], []
            for row in records:
                meta = row.get("metadata") or {}
                props = dict(id=row["id"], name=row["name"], external_id=row.get("external_id"), provenance=row["provenance"], state="UNKNOWN", source="OpenStreetMap" if meta.get("osm_node_id") else "Database junction record", note=meta.get("note", ""))
                raw = row.get("location")
                if not raw:
                    unresolved.append(dict(id=row["id"], name=row["name"], group=meta.get("user_group"), reason="Coordinates need verification"))
                    continue
                geom = wkt.loads(raw.split(";", 1)[-1]) if "POINT" in raw.upper() else wkb.loads(bytes.fromhex(raw))
                if geom.geom_type != "Point":
                    raise ValueError("Signal location must be a point")
                features.append(dict(type="Feature", geometry=mapping(geom), properties=props))
            _signals_cache = dict(type="FeatureCollection", features=features, unresolved=unresolved, metadata=dict(mapped=len(features), unresolved=len(unresolved), checked_at=datetime.now(timezone.utc).isoformat(), source="Supabase junctions", telemetry="No connected signal controller telemetry; phase is unknown. OSM nodes can represent individual approaches."))
            _signals_time = monotonic()
            return _signals_cache
        except Exception:
            raise HTTPException(503, "Database traffic signal locations are unavailable")


@router.get('/simulation-inventory')
def simulation_inventory_endpoint():
 return simulation_inventory()


def scenario_road_effect(geometry):
 import scenario_runtime as shared
 from shapely.geometry import Polygon
 if shared.current is None:return dict(traffic_status='UNKNOWN')
 state=shared.current['state'];items=[shared.effect(z,state['seconds']) for z in state['scenarios'] if Polygon(z['polygon']).intersects(geometry)]
 if not items:return dict(traffic_status='UNKNOWN')
 blocked=any(e['blocked'] for e in items);factor=min(e['traffic_factor'] for e in items)
 return dict(traffic_status='BLOCKED' if blocked else 'CONGESTED' if factor<.5 else 'SLOW' if factor<.85 else 'UNKNOWN',simulation_speed_factor=factor,traffic_provenance='SIMULATED',scenario_version=shared.current['version'])


@router.get('/signals')
def signals():
 from copy import deepcopy
 import scenario_runtime as shared
 from shapely.geometry import Point,Polygon
 from signal_operations import assets,phase_states,approaches
 from emergency_model import controller
 data=deepcopy(signal_locations())
 if shared.current is None:return data
 state=shared.current['state'];elapsed=state['seconds'];all_assets=assets(state)
 for a in state.get('custom_signals',{}).values():
  data['features'].append(dict(type='Feature',geometry=dict(type='Point',coordinates=[a['longitude'],a['latitude']]),properties=dict(id=a['id'],name=a['name'],provenance=a['provenance'],source='Shared database signal registry')))
 for feature in data['features']:
  props=feature['properties'];point=Point(feature['geometry']['coordinates'])
  asset=next((a for a in all_assets if a['kind']=='TRAFFIC_SIGNAL' and abs(a['longitude']-point.x)<.0001 and abs(a['latitude']-point.y)<.0001),None)
  if not asset:
   props.update(state='UNKNOWN',approaches=[],note='No stored operating controller is linked to this mapped location.');continue
  failed=any(shared.effect(z,elapsed)['signal_failed'] and Polygon(z['polygon']).covers(point) for z in state['scenarios'])
  # Reading never inserts a controller into live state. A temporary projection
  # uses the same committed timing plan until its first operational command.
  local={'seconds':elapsed,'signal_plans':deepcopy(state.get('signal_plans',{})),'custom_signals':state.get('custom_signals',{}),'emergency':{'controllers':{}},'events':[],'outbox':[]}
  j=state.get('emergency',{}).get('controllers',{}).get(asset['id']) or controller(local,asset)
  phase=phase_states(state,j,failed);props.update(controller_id=asset['id'],approaches=phase,bounds=len(phase),state='FAILED' if failed else 'OPERATING',cycle_seconds=j.get('cycle_seconds',90),phase_offset_seconds=j['offset'],controller_mode='MANUAL' if j['manual'] else 'AUTOMATIC',queues=j['queues'],emergency_stage=j['stage'],verified_priority=j['verified_green'],power_supply=asset.get('spec',{}).get('power_supply'),note='Each row identifies travel direction and the side vehicles enter from. Phases and queues are simulated; stored approach bearings require field verification.')
  props['commands']=[dict(id=c['id'],action=c['action'],status=c['status']) for c in state.get('emergency',{}).get('commands',{}).values() if c['junction_id']==asset['id'] and c['status']=='PENDING']
 data['metadata'].update(mapped=len(data['features']),telemetry='Shared directional signal operating model')
 return data
