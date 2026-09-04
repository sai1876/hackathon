"""Road-interior endpoint routing on request-local graph copies only."""
from dataclasses import dataclass
from math import cos, radians, isfinite

from shapely.affinity import scale
from shapely.geometry import Point, LineString, box
from shapely.ops import substring
from shapely.strtree import STRtree


def build_snap_index(graph):
    edges = [(u, v, k) for u, v, k, data in graph.edges(keys=True, data=True)
             if data.get("geometry") is not None and data["geometry"].length > 0]
    geometries = [graph[u][v][k]["geometry"] for u, v, k in edges]
    graph.graph["snap_index"] = (STRtree(geometries), edges)


def directed_geometry(graph, u, v, geometry):
    """Never join reversed or geographically inconsistent edge geometry blindly."""
    start = Point(graph.nodes[u]["x"], graph.nodes[u]["y"])
    end = Point(graph.nodes[v]["x"], graph.nodes[v]["y"])
    first, last = Point(geometry.coords[0]), Point(geometry.coords[-1])
    tolerance = 0.00002  # About 2 m; accommodates source rounding, not missing roads.
    if first.distance(start) <= tolerance and last.distance(end) <= tolerance:
        return geometry
    if last.distance(start) <= tolerance and first.distance(end) <= tolerance:
        return LineString(list(geometry.coords)[::-1])
    raise RuntimeError("Road geometry does not match its graph nodes. Choose another road; this segment needs data review.")


@dataclass
class Snap:
    requested: dict
    point: Point
    distance_m: float
    candidates: list
    node: str | None

    def metadata(self):
        return {"requested": self.requested,
                "snapped": {"lat": self.point.y, "lon": self.point.x},
                "distance_m": round(self.distance_m, 2)}


def snap_to_road(graph, coordinate, label, max_distance_m=100):
    if "snap_index" not in graph.graph:
        build_snap_index(graph)
    tree, edges = graph.graph["snap_index"]
    point = Point(coordinate.lon, coordinate.lat)
    # Local equirectangular metric projection; adequate for a <=100 m offset in Hyderabad.
    x_scale = 111195 * cos(radians(coordinate.lat))
    y_scale = 111195
    if x_scale < 1:
        raise RuntimeError("Road snapping is not supported at this latitude.")
    radius_x, radius_y = max_distance_m / x_scale, max_distance_m / y_scale
    indices = tree.query(box(point.x-radius_x, point.y-radius_y, point.x+radius_x, point.y+radius_y))
    projected_point = scale(point, xfact=x_scale, yfact=y_scale, origin=(0, 0))
    nearest = None
    for index in indices:
        u, v, key = edges[int(index)]
        geometry = graph[u][v][key]["geometry"]
        metric = scale(geometry, xfact=x_scale, yfact=y_scale, origin=(0, 0))
        projected = metric.interpolate(metric.project(projected_point))
        distance = projected.distance(projected_point)
        rank = (distance, str(graph[u][v][key].get("external_id", key)))
        if nearest is None or rank < nearest[0]:
            nearest = (rank, (u, v, key), geometry, projected)
    if nearest is None or nearest[0][0] > max_distance_m:
        raise RuntimeError(f"{label} is more than {max_distance_m} m from a loaded road. Click closer to a road.")
    _, (u, v, key), raw, projected = nearest
    snapped = scale(projected, xfact=1/x_scale, yfact=1/y_scale, origin=(0, 0))
    geometry = directed_geometry(graph, u, v, raw)
    position = geometry.project(snapped)
    # Use exact stored endpoints when the projection reaches a junction.
    node = None
    if position <= 1e-10:
        node = u
    elif geometry.length - position <= 1e-10:
        node = v
    if node is not None:
        snapped = Point(graph.nodes[node]["x"], graph.nodes[node]["y"])
    candidates = []
    # Include the reverse directed representation of this same physical segment,
    # never a nearby parallel road or a crossing with unrelated topology.
    for a, b in {(u, v), (v, u)}:
        for k, data in (graph.get_edge_data(a, b) or {}).items():
            if data["geometry"].equals(raw):
                oriented = directed_geometry(graph, a, b, data["geometry"])
                candidates.append((a, b, k, oriented, oriented.project(snapped)))
    offset = scale(snapped, xfact=x_scale, yfact=y_scale, origin=(0, 0)).distance(projected_point)
    if offset > max_distance_m:
        raise RuntimeError(f"{label} is more than {max_distance_m} m from a loaded road. Click closer to a road.")
    return Snap({"lat": coordinate.lat, "lon": coordinate.lon}, snapped, offset, candidates, node)


def _add_partial(graph, source, target, candidate, begin, finish):
    u, v, key, geometry, _ = candidate
    if finish - begin <= 1e-12:
        return
    data = graph[u][v][key]
    if not isfinite(data["current_cost"]):
        return  # A closed edge cannot become usable through an endpoint split.
    piece = substring(geometry, begin, finish)
    latitude = (piece.coords[0][1] + piece.coords[-1][1]) / 2
    factor = cos(radians(latitude))
    ratio = scale(piece, xfact=factor, origin=(0, 0)).length / scale(geometry, xfact=factor, origin=(0, 0)).length
    attributes = dict(data)
    for field in ("length_m", "base_travel_time_sec", "current_cost"):
        attributes[field] = data.get(field, 0) * ratio
    attributes.update(geometry=piece, partial=True, signalized=bool(data.get("signalized")) and abs(finish-geometry.length)<1e-10)
    graph.add_edge(source, target, **attributes)


def attach_endpoints(graph, start, end):
    if start.point.distance(end.point) < 1e-9:
        raise RuntimeError("Start and destination snap to the same road position. Choose points farther apart.")
    start_node, end_node = start.node or "__aegis_start__", end.node or "__aegis_end__"
    for node, snap in ((start_node, start), (end_node, end)):
        if snap.node is None:
            graph.add_node(node, x=snap.point.x, y=snap.point.y)
    if start.node is None:
        for candidate in start.candidates:
            _add_partial(graph, start_node, candidate[1], candidate, candidate[4], candidate[3].length)
    if end.node is None:
        for candidate in end.candidates:
            _add_partial(graph, candidate[0], end_node, candidate, 0, candidate[4])
    if start.node is None and end.node is None:
        for a in start.candidates:
            for b in end.candidates:
                if a[:3] == b[:3] and a[4] < b[4]:
                    _add_partial(graph, start_node, end_node, a, a[4], b[4])
    return start_node, end_node
