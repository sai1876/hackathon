"""Deterministic synthetic pilot. No real utility locations or switching controls."""
from contextlib import contextmanager, asynccontextmanager
import json
import math
import os
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock, Thread, Event
import time
import uuid
import logging
from shapely.geometry import Polygon, Point
import weather_effects

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal


def generate():
    """Load the frozen OSM-constrained synthetic layout; never invent a grid fallback."""
    return json.loads((Path(__file__).parent / "data" / "electric-road-layout.json").read_text(encoding="utf-8"))


class ElectricWorld:
    def __init__(self, path):
        self.lock = RLock()
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS world (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO world VALUES (1, ?)", (json.dumps(dict(version=0, faults=[], tasks=[], events=[], seconds=0, queues={})),))
            db.execute("CREATE TABLE IF NOT EXISTS dataset (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            row = db.execute("SELECT payload FROM dataset WHERE id=1").fetchone()
            if row:
                self.assets = json.loads(row[0])
            else:
                self.assets = generate()
                db.execute("INSERT INTO dataset VALUES (1, ?)", (json.dumps(self.assets),))

        self.base_load = {i: a["demand_kw"] for i, a in self.assets.items()}
        for i, a in reversed(list(self.assets.items())):
            if a["parent"]:
                self.base_load[a["parent"]] += self.base_load[i]
        # Synthetic operating limits, not manufacturer ratings or load-flow results.
        self.capacities = {i: round(max(1, load * 1.35), 2) for i, load in self.base_load.items()}

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self, db):
        state = json.loads(db.execute("SELECT payload FROM world WHERE id=1").fetchone()[0])
        for key, value in {"running": False, "speed": 1, "last_tick": None, "load_factors": {}, "trips": [], "overload_seconds": {}, "simulation_revision": 0, "rain_zones": []}.items():
            state.setdefault(key, value)
        return state

    def statuses(self, state):
        off = set()
        faults = set(state["faults"]) | set(state.get("trips", []))
        # Generator inserts parents before children: a radial dependency traversal.
        for identifier, a in self.assets.items():
            if identifier in faults or a["parent"] in off:
                off.add(identifier)
        return off

    def rain_factors(self, state):
        factors = {}
        for z in state["rain_zones"]:
            factor = 1 + min(0.35, z["intensity"] * 0.002 + z["water_mm"] * 0.01)
            for identifier in z["affected_ids"]:
                factors[identifier] = max(factors.get(identifier, 1), factor)
        return factors

    def weather(self):
        with self.lock, self.connect() as db:
            return self.read(db)["rain_zones"]

    def loads(self, state):
        off = self.statuses(state)
        factors, desired, supplied = {}, {}, {}
        rain = self.rain_factors(state)
        for i, a in self.assets.items():
            factors[i] = state["load_factors"].get(i, 1) * factors.get(a["parent"], 1)
            desired[i] = a["demand_kw"] * factors[i] * rain.get(i, 1)
            supplied[i] = 0 if i in off else desired[i]
        for i, a in reversed(list(self.assets.items())):
            if a["parent"]:
                desired[a["parent"]] += desired[i]
                supplied[a["parent"]] += supplied[i]
        return desired, supplied

    def record(self, state, action, identifier, note, operator="Simulation engine"):
        state["events"].append(dict(id=str(uuid.uuid4()), action=action, asset_id=identifier,
            task_id="", operator=operator, note=note, simulation_seconds=state["seconds"],
            at=datetime.now(timezone.utc).isoformat(), provenance="SYNTHETIC"))
        state["events"] = state["events"][-500:]

    def advance_seconds(self, state, seconds):
        for _ in range(seconds):
            for z in state["rain_zones"]:
                z["water_mm"] = round(max(0, min(200, z["water_mm"] + (z["intensity"] - 8) / 3600)), 6)
            rain = self.rain_factors(state)
            _, supplied = self.loads(state)
            off = self.statuses(state)
            pending = []
            for i, a in self.assets.items():
                if a["kind"] == "SIGNAL_LOAD":
                    state["queues"][i] = round(max(0, state["queues"].get(i, 0) + (0.2 if i in off else -0.3) + max(0, rain.get(i, 1) - 1) * 2), 2)
                    continue
                previous = state["overload_seconds"].get(i, 0)
                overloaded = supplied[i] > self.capacities[i] and i not in off
                exposure = previous + 1 if overloaded else 0
                if exposure:
                    state["overload_seconds"][i] = exposure
                else:
                    state["overload_seconds"].pop(i, None)
                if exposure == 1:
                    self.record(state, "OVERLOAD", i, "Demand exceeds the modeled operating limit; protection will trip after 10 continuous simulated seconds.")
                elif previous and not overloaded and i not in state["trips"]:
                    self.record(state, "OVERLOAD_CLEARED", i, "Supplied load returned below the modeled operating limit.")
                if exposure >= 10:
                    pending.append(i)
            state["seconds"] += 1
            # Downstream-first selectivity: allow local protection to remove load before
            # deciding whether an upstream device still needs to trip on this step.
            current = supplied.copy()
            for i in reversed(pending):
                if current[i] > self.capacities[i]:
                    removed = current[i]
                    parent = i
                    while parent:
                        current[parent] = max(0, current[parent] - removed)
                        parent = self.assets[parent]["parent"]
                    state["trips"].append(i)
                    self.record(state, "PROTECTION_TRIP", i, "Ten seconds above the modeled load limit disconnected this asset and its downstream supply. Reduce demand, then reset protection.")
            state["simulation_revision"] += 1

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = self.read(db)
            if not state["running"]:
                return
            last = state["last_tick"]
            elapsed = now - last if last is not None else 0
            if elapsed < 1:
                return
            if elapsed > 15:
                # A stopped service must not replay an unattended outage on restart.
                state["running"] = False
                self.record(state, "CLOCK_PAUSED", "", "Simulation paused after a service interruption. Press Run to resume.")
            else:
                steps = min(5, int(elapsed))
                self.advance_seconds(state, steps * state["speed"])
            state["last_tick"] = now
            db.execute("UPDATE world SET payload=? WHERE id=1", (json.dumps(state),))

    def snapshot(self):
        with self.lock, self.connect() as db:
            state = self.read(db)
        off = self.statuses(state)
        desired, supplied = self.loads(state)
        telemetry = {i: dict(demand_kw=round(desired[i], 2), supplied_kw=round(supplied[i], 2),
            capacity_kw=self.capacities[i], utilization_percent=round(100 * supplied[i] / self.capacities[i], 1),
            demand_percent=round(100 * desired[i] / self.capacities[i], 1),
            load_percent=round(state["load_factors"].get(i, 1) * 100),
            overload_seconds=state["overload_seconds"].get(i, 0),
            status="TRIPPED" if i in state["trips"] else "WITHOUT_SUPPLY" if i in off else "OVERLOADED" if supplied[i] > self.capacities[i] else "SUPPLIED") for i in self.assets}
        counts = {}
        for a in self.assets.values():
            counts[a["kind"]] = counts.get(a["kind"], 0)+1
        return {**state, "events": state["events"][-60:][::-1], "counts": counts,
            "off_ids": sorted(off), "assets_without_supply": len(off),
            "affected_stations": sorted({self.assets[i]["station"] for i in off}),
            "unserved_kw": round(sum(desired[i] - supplied[i] for i,a in self.assets.items() if a["parent"] is None), 2),
            "rain_effects": [dict(id=z["id"], intensity=z["intensity"], water_mm=round(z["water_mm"], 3),
                polygon=z["polygon"], affected_assets=len(z["affected_ids"]),
                electricity_uplift_percent=round(min(0.35, z["intensity"]*0.002+z["water_mm"]*0.01)*100, 1),
                road_delay_factor=round(1+min(1.5,z["intensity"]/100+z["water_mm"]/10),1),
                metro_demand_index=round(100+min(80,z["intensity"]*0.6+z["water_mm"]*2),1),
                provenance="SYNTHETIC") for z in state["rain_zones"]],
            "telemetry": telemetry, "overloaded_ids": [i for i,t in telemetry.items() if t["status"] == "OVERLOADED"],
            "signals_without_supply": sum(a["kind"] == "SIGNAL_LOAD" for i,a in self.assets.items() if i in off),
            "stations": [a for a in self.assets.values() if a["kind"] == "SUBSTATION"],
            "provenance": "SYNTHETIC", "dataset_version": "hyderabad-electric-osm-v2", "seed": 3297,
            "clock_mode": "RUNNING" if state["running"] else "PAUSED", "storage": "Local SQLite", "asset_total": len(self.assets)}

    def detail(self, identifier):
        if identifier not in self.assets:
            raise HTTPException(404, "Asset not found")
        chain = []
        current = self.assets[identifier]
        while current:
            chain.append(current["id"])
            current = self.assets.get(current["parent"])
        return {**self.assets[identifier], "upstream": chain,
            "children": [a for a in self.assets.values() if a["parent"] == identifier]}

    def geometry(self, west, south, east, north, zoom, station):
        if west >= east or south >= north:
            raise HTTPException(422, "Invalid map bounds")
        if station and (station not in self.assets or self.assets[station]["kind"] != "SUBSTATION"):
            raise HTTPException(404, "Substation not found")
        features = []
        for a in self.assets.values():
            if not (west <= a["lon"] <= east and south <= a["lat"] <= north):
                continue
            visible = a["kind"] == "SUBSTATION" or (a["station"] == station and
                (a["kind"] == "FEEDER_11KV" and zoom >= 12 or zoom >= 14))
            if not visible:
                continue
            features.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[a["lon"],a["lat"]]), properties={k:v for k,v in a.items() if k != "connection_geometry"}))
            parent = self.assets.get(a["parent"])
            if parent and a["station"] == station:
                features.append(dict(type="Feature", geometry=a.get("connection_geometry", dict(type="LineString", coordinates=[[parent["lon"],parent["lat"]],[a["lon"],a["lat"]]])), properties={k:v for k,v in a.items() if k != "connection_geometry"}))
        return dict(type="FeatureCollection", features=features)

    def act(self, payload):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = self.read(db)
            if state["version"] != payload.version:
                raise HTTPException(409, "State changed. Review the latest state and retry.")
            action, identifier = payload.action, payload.asset_id
            if action == "RAIN":
                if len(state["rain_zones"]) >= 10:
                    raise HTTPException(409, "At most 10 rain areas per exercise; remove an old area first")
                try:
                    polygon = Polygon(payload.polygon)
                except Exception:
                    raise HTTPException(422, "Draw a polygon with at least three points")
                if not polygon.is_valid or polygon.area < 0.000001 or polygon.area > 0.08:
                    raise HTTPException(422, "Draw a non-crossing area between approximately 0.01 and 900 square km")
                if any(not (78.05 <= x <= 78.95 and 17.05 <= y <= 17.85) for x,y in payload.polygon):
                    raise HTTPException(422, "Rain area must be within the Hyderabad study region")
                affected = [i for i,a in self.assets.items() if polygon.covers(Point(a["lon"],a["lat"]))]
                identifier = str(uuid.uuid4())
                state["rain_zones"].append(dict(id=identifier, polygon=payload.polygon, intensity=payload.intensity, water_mm=0, affected_ids=affected))
            elif action in ("RAIN_INTENSITY", "REMOVE_RAIN"):
                zone = next((z for z in state["rain_zones"] if z["id"] == identifier), None)
                if zone is None:
                    raise HTTPException(404, "Rain area not found")
                if action == "REMOVE_RAIN":
                    state["rain_zones"].remove(zone)
                else:
                    zone["intensity"] = payload.intensity
            elif action == "LOAD":
                if identifier not in self.assets:
                    raise HTTPException(404, "Asset not found")
                state["load_factors"][identifier] = payload.load_percent / 100
            elif action == "CLOCK":
                state["running"] = payload.running
                state["speed"] = payload.speed
                state["last_tick"] = time.time()
                identifier = ""
            elif action == "RESET_PROTECTION":
                if identifier not in state["trips"]:
                    raise HTTPException(409, "This asset has not tripped")
                desired, _ = self.loads(state)
                if desired[identifier] > self.capacities[identifier]:
                    raise HTTPException(409, "Reduce demand below this asset's modeled limit before resetting protection")
                state["trips"].remove(identifier)
                state["overload_seconds"].pop(identifier, None)
            elif action == "FAULT":
                if identifier not in self.assets or self.assets[identifier]["kind"] == "SIGNAL_LOAD":
                    raise HTTPException(422, "Choose a supply asset to fault")
                if identifier in state["faults"]:
                    raise HTTPException(409, "This asset already has a fault")
                state["faults"].append(identifier)
                state["tasks"].append(dict(id=f"JOB-{state['version']+1:05}", asset_id=identifier, status="OPEN", crew="", note=payload.note))
            elif action == "ADVANCE":
                identifier = ""
                if state["running"]:
                    raise HTTPException(409, "Pause the clock before advancing manually")
                self.advance_seconds(state, 60)
            else:
                task = next((t for t in state["tasks"] if t["id"] == payload.task_id), None)
                if not task:
                    raise HTTPException(404, "Repair task not found")
                transitions = {"ASSIGN": ("OPEN", "ASSIGNED"), "START": ("ASSIGNED", "IN_PROGRESS"),
                    "COMPLETE": ("IN_PROGRESS", "AWAITING_VERIFICATION"), "VERIFY": ("AWAITING_VERIFICATION", "RESTORED")}
                previous, following = transitions[action]
                if task["status"] != previous:
                    raise HTTPException(409, f"Repair must be {previous} before this action")
                if action == "ASSIGN":
                    if not payload.crew.strip():
                        raise HTTPException(422, "A crew name is required")
                    task["crew"] = payload.crew.strip()
                task["status"] = following
                identifier = task["asset_id"]
                if action == "VERIFY":
                    state["faults"].remove(identifier)
            state["version"] += 1
            state["events"].append(dict(id=state["version"], action=action, asset_id=identifier,
                task_id=payload.task_id, operator=payload.operator.strip(), note=(f"Set downstream demand to {payload.load_percent}% of baseline" if action == "LOAD" else f"Clock {'running' if payload.running else 'paused'} at {payload.speed}x" if action == "CLOCK" else payload.note.strip()),
                simulation_seconds=state["seconds"], at=datetime.now(timezone.utc).isoformat(), provenance="SYNTHETIC"))
            state["events"] = state["events"][-500:]
            db.execute("UPDATE world SET payload=? WHERE id=1", (json.dumps(state),))
        return self.snapshot()


class ElectricAction(BaseModel):
    version: int = Field(ge=0)
    action: Literal["FAULT", "ASSIGN", "START", "COMPLETE", "VERIFY", "ADVANCE", "LOAD", "CLOCK", "RESET_PROTECTION", "RAIN", "RAIN_INTENSITY", "REMOVE_RAIN"]
    polygon: list[tuple[float, float]] = Field(default_factory=list, max_length=40)
    intensity: int = Field(default=30, ge=0, le=150)
    load_percent: int = Field(default=100, ge=0, le=400)
    running: bool = False
    speed: Literal[1, 5, 10] = 1
    asset_id: str = ""
    task_id: str = ""
    crew: str = Field(default="", max_length=100)
    operator: str = Field(min_length=1, max_length=100, pattern=r"\S")
    note: str = Field(min_length=3, max_length=500, pattern=r"\S")


@asynccontextmanager
async def electric_lifespan(app):
    stop = Event()
    def loop():
        while not stop.wait(1):
            try:
                if os.getenv("AEGIS_DATA_MODE", "DATABASE_ONLY") == "EXERCISE":
                    world().tick()
                    weather_effects.publish(world().weather())
            except Exception:
                logging.exception("Electrical simulation tick failed")
    def routing_loop():
        while not stop.is_set():
            if weather_effects.changed.wait(1):
                weather_effects.changed.clear()
                if weather_effects.on_change:
                    try: weather_effects.on_change()
                    except Exception: logging.exception("Weather corridor refresh failed")
    routing_worker = Thread(target=routing_loop, name="weather-routing", daemon=True)
    routing_worker.start()
    worker = Thread(target=loop, name="electric-clock", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=5)

router = APIRouter(prefix="/electric", tags=["Synthetic electricity"], lifespan=electric_lifespan)
_world = None
_world_lock = RLock()

def world():
    global _world
    with _world_lock:
        if _world is None:
            _world = ElectricWorld(os.getenv("ELECTRIC_DB_PATH", str(Path(__file__).parent / "data" / "electric-world.sqlite3")))
    return _world

@router.get("")
def snapshot():
    return world().snapshot()

@router.get("/assets/{identifier}")
def detail(identifier: str):
    return world().detail(identifier)

@router.get("/map")
def geometry(west: float = Query(78.05, ge=-180, le=180), south: float = Query(17.05, ge=-90, le=90),
             east: float = Query(78.95, ge=-180, le=180), north: float = Query(17.85, ge=-90, le=90),
             zoom: float = Query(11, ge=0, le=24), station: str = ""):
    return world().geometry(west, south, east, north, zoom, station)

@router.post("/actions")
def action(payload: ElectricAction):
    if os.getenv("AEGIS_DATA_MODE", "DATABASE_ONLY") != "EXERCISE":
        raise HTTPException(409, "Legacy generated-data exercises are disabled in database-only mode. Configure verified inputs in the main Command Center.")
    return world().act(payload)
