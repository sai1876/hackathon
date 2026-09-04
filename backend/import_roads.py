"""Bounded, append-only OSM maintenance import. Prepare first, then --apply.

Existing external IDs are never overwritten. Artifacts support audit/retries.
Run from backend with the maintenance requirements installed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import sleep

import httpx
import networkx as nx
import osmnx as ox
from shapely.geometry import LineString

from database import supabase
from graph_manager import GraphManager
from endpoint_snapping import snap_to_road, attach_endpoints, directed_geometry
from models import Coordinate

BBOX = (78.32, 17.50, 78.405, 17.585)  # west, south, east, north
BATCH = "mallampet-bachupally-2026-09-03"
SOURCE = "48855790-76ba-4195-ad58-363f9b527017"
ARTIFACTS = Path(__file__).parent / "data" / "imports" / BATCH
SPEEDS = {"motorway": 80, "trunk": 60, "primary": 50, "secondary": 40,
          "tertiary": 30, "residential": 25, "unclassified": 25,
          "service": 15, "living_street": 10}


def digest(rows):
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: r["external_id"]),
                                    sort_keys=True).encode()).hexdigest()


def text_value(value):
    return "; ".join(map(str, value)) if isinstance(value, list) else str(value) if value is not None else None


def fetch_roads():
    for attempt in range(3):
        try:
            return GraphManager().fetch_roads(*BBOX)
        except httpx.TransportError:
            if attempt == 2:
                raise
            sleep(2 * (attempt + 1))


def verify_saved_import():
    before = json.loads((ARTIFACTS / "existing-before.json").read_text(encoding="utf-8"))
    inserted = json.loads((ARTIFACTS / "inserted-ids.json").read_text(encoding="utf-8"))
    after = fetch_roads()
    previous_ids = {r["external_id"] for r in before}
    if digest([r for r in after if r["external_id"] in previous_ids]) != digest(before):
        raise RuntimeError("Existing road snapshot changed during import; review concurrent writes")
    # Validate the persisted graph, including conflicts that were left untouched.
    _, checks = validate(after, [])
    report = json.loads((ARTIFACTS / "report.json").read_text(encoding="utf-8"))
    report.update(applied=True, inserted_edges=len(inserted), existing_unchanged=True,
                  verification="passed", persisted_validation=checks)
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


def prepare():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = str(ARTIFACTS / "cache")
    ox.settings.log_console = True
    graph_file = ARTIFACTS / "roads.graphml"
    if graph_file.exists():
        graph = ox.load_graphml(graph_file)
    else:
        graph = ox.graph_from_bbox(BBOX, network_type="drive", simplify=True,
                                   retain_all=True, truncate_by_edge=True)
        graph = ox.routing.add_edge_speeds(graph, hwy_speeds=SPEEDS, fallback=25)
        ox.save_graphml(graph, graph_file)
    rows = []
    downloaded_at = datetime.fromtimestamp(graph_file.stat().st_mtime, timezone.utc).isoformat()
    for u, v, key, edge in graph.edges(keys=True, data=True):
        start = (graph.nodes[u]["x"], graph.nodes[u]["y"])
        end = (graph.nodes[v]["x"], graph.nodes[v]["y"])
        geometry = edge.get("geometry", LineString([start, end]))
        geometry = directed_geometry(graph, u, v, geometry)
        length, speed = float(edge["length"]), float(edge["speed_kph"])
        if length <= 0 or speed <= 0:
            raise ValueError("Non-positive road length/speed")
        rows.append({"external_id": f"OSM:{u}:{v}:{key}", "osm_u": str(u),
                     "osm_v": str(v), "osm_key": int(key),
                     "road_name": text_value(edge.get("name")),
                     "road_class": text_value(edge.get("highway")),
                     "geometry": "SRID=4326;" + geometry.wkt,
                     "length_m": length, "free_flow_speed_kmph": speed,
                     "base_travel_time_sec": length / speed * 3.6,
                     "oneway": bool(edge.get("oneway", False)),
                     "provenance": "REAL", "source_id": SOURCE,
                     "metadata": {"osmid": text_value(edge.get("osmid")),
                                  "maxspeed_raw": text_value(edge.get("maxspeed")),
                                  "import_source": "OSMnx 2.1.0", "network_type": "drive",
                                  "import_batch": BATCH, "downloaded_at": downloaded_at,
                                  "requested_bbox": BBOX, "license": "ODbL-1.0",
                                  "free_flow_speed_provenance": "DERIVED",
                                  "free_flow_speed_role": "routing_baseline",
                                  "speed_method": "OSMnx maxspeed parsing; class defaults; 25 km/h fallback"}})
    (ARTIFACTS / "prepared.json").write_text(json.dumps(rows), encoding="utf-8")
    return rows


def validate(existing, proposed):
    old = {r["external_id"]: r for r in existing}
    additions = [r for r in proposed if r["external_id"] not in old]
    old_graph = GraphManager().build_graph(existing)
    new_rows = [dict(r, geometry_wkt=r["geometry"].split(";", 1)[1]) for r in additions]
    new_graph = GraphManager().build_graph(new_rows)
    shared = set(old_graph) & set(new_graph)
    if additions and not shared:
        raise RuntimeError("No shared OSM junctions: expansion is disconnected")
    for node in shared:
        a, b = old_graph.nodes[node], new_graph.nodes[node]
        if abs(a["x"]-b["x"]) > .00002 or abs(a["y"]-b["y"]) > .00002:
            raise RuntimeError(f"Existing OSM junction moved: {node}; requires review")
    combined = GraphManager().build_graph(existing + new_rows)
    for u, v, data in combined.edges(data=True):
        directed_geometry(combined, u, v, data["geometry"])
    a = snap_to_road(combined, Coordinate(lat=17.55795, lon=78.36348), "Start")
    b = snap_to_road(combined, Coordinate(lat=17.54157, lon=78.36377), "Destination")
    start, end = attach_endpoints(combined, a, b)
    path = nx.shortest_path(combined, start, end, weight="current_cost")
    reachable = nx.descendants(combined, start)
    if not (reachable & set(old_graph)):
        raise RuntimeError("New start cannot reach existing road network")
    return additions, {"shared_junctions": len(shared), "sample_path_nodes": len(path),
                       "start_snap_m": a.distance_m, "end_snap_m": b.distance_m}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Insert validated missing roads; never update existing ones")
    parser.add_argument("--verify-only", action="store_true", help="Resume read-only verification of a completed/partial import")
    args = parser.parse_args()
    if args.verify_only:
        verify_saved_import()
        return
    rows = json.loads((ARTIFACTS / "prepared.json").read_text(encoding="utf-8")) if args.apply else prepare()
    existing = fetch_roads()
    additions, checks = validate(existing, rows)
    report = {"batch": BATCH, "bbox": BBOX, "downloaded_edges": len(rows),
              "existing_overlap": len(existing), "existing_fingerprint": digest(existing),
              "missing_edges": len(additions), "validation": checks, "applied": False}
    (ARTIFACTS / "existing-before.json").write_text(json.dumps(existing), encoding="utf-8")
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.apply:
        inserted = []
        for offset in range(0, len(additions), 250):
            batch = additions[offset:offset+250]
            response = supabase.table("road_segments").upsert(
                batch, on_conflict="external_id", ignore_duplicates=True).execute()
            inserted.extend(r["external_id"] for r in response.data)
            (ARTIFACTS / "inserted-ids.json").write_text(json.dumps(inserted), encoding="utf-8")
            print(f"Inserted {len(inserted)} / {len(additions)}", flush=True)
        verify_saved_import()
        return
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
