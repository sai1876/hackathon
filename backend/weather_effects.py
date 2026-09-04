"""Synthetic polygon rainfall effects shared with road routing. Not weather telemetry."""
from threading import Event
from shapely.geometry import Polygon
from shapely import wkt
import json

zones = []
shared_zones = []
changed = Event()
on_change = None
signature = "[]"

def publish(items):
    global zones, signature
    next_zones = [{"id": z["id"], "polygon": z["polygon"], "factor": round(1 + min(1.5, z["intensity"] / 100 + z["water_mm"] / 10), 1)} for z in items if z["intensity"] or z["water_mm"] > 0.1]
    next_signature = json.dumps(next_zones, sort_keys=True)
    zones = next_zones
    if signature != next_signature:
        signature = next_signature
        changed.set()

def apply(graph):
    current = [(Polygon(z["polygon"]), z) for z in zones + shared_zones]
    affected = 0
    if not current:
        return {"provenance": "SYNTHETIC", "rain_zones": 0, "affected_graph_edges": 0}
    for _, _, _, data in graph.edges(keys=True, data=True):
        geom = data.get("geometry")
        if isinstance(geom, str): geom = wkt.loads(geom)
        if geom is None: continue
        factors = [z["factor"] for polygon,z in current if polygon.intersects(geom)]
        if factors:
            factor = max(factors)
            data["current_cost"] *= factor
            if any(z.get("blocked") for polygon,z in current if polygon.intersects(geom)):
                data["blocked"] = True
                data["current_cost"] = float("inf")
            data["synthetic_rain_delay_factor"] = factor
            affected += 1
    return {"provenance": "SYNTHETIC", "rain_zones": len(current), "affected_graph_edges": affected, "model": "Polygon rainfall delay; overlapping zones use the maximum delay; existing road closures remain closed"}
