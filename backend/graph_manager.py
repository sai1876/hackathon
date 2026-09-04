import networkx as nx
from shapely import wkt

from database import supabase
from endpoint_snapping import build_snap_index


class GraphManager:

    def __init__(self):
        # Temporary in-memory cache.
        # Render can rebuild this cache whenever the service restarts.
        self.cache = {}
        self.cache_bounds = {}

    def _build_bbox(
        self,
        start_lat,
        start_lon,
        end_lat,
        end_lon,
        padding_deg=0.025
    ):
        min_lat = min(start_lat, end_lat) - padding_deg
        max_lat = max(start_lat, end_lat) + padding_deg

        min_lon = min(start_lon, end_lon) - padding_deg
        max_lon = max(start_lon, end_lon) + padding_deg

        return (
            min_lon,
            min_lat,
            max_lon,
            max_lat
        )

    def _make_cache_key(
        self,
        min_lon,
        min_lat,
        max_lon,
        max_lat
    ):
        return (
            round(min_lon, 3),
            round(min_lat, 3),
            round(max_lon, 3),
            round(max_lat, 3)
        )

    def fetch_roads(
        self,
        min_lon,
        min_lat,
        max_lon,
        max_lat
    ):

        all_roads = []

        # Supabase/PostgREST currently gives us
        # at most 1000 rows per RPC response.
        page_size = 1000
        offset = 0

        while True:

            print(
                f"Downloading roads "
                f"{offset:,} - "
                f"{offset + page_size - 1:,}"
            )

            response = (
                supabase
                .rpc(
                    "get_aegis_routing_roads",
                    {
                        "min_lon": min_lon,
                        "min_lat": min_lat,
                        "max_lon": max_lon,
                        "max_lat": max_lat,
                        "p_limit": page_size,
                        "p_offset": offset
                    }
                )
                .execute()
            )

            batch = response.data or []

            received = len(batch)

            all_roads.extend(batch)

            print(
                f"Received {received:,}"
                f" | Total {len(all_roads):,}"
            )

            # No rows means we are actually finished.
            if received == 0:
                break

            # Advance by what we actually received,
            # not by what we requested.
            offset += received

            # A genuinely short page also means end.
            if received < page_size:
                break

        print(
            f"Finished downloading "
            f"{len(all_roads):,} road edges"
        )

        return all_roads

    def build_graph(self, roads):

        graph = nx.MultiDiGraph()

        skipped = 0

        for road in roads:

            try:
                osm_u = str(road["osm_u"])
                osm_v = str(road["osm_v"])
                osm_key = int(road["osm_key"])

                geometry_text = road.get("geometry_wkt")

                if not geometry_text:
                    skipped += 1
                    continue

                geometry = wkt.loads(geometry_text)

                coordinates = list(geometry.coords)

                if len(coordinates) < 2:
                    skipped += 1
                    continue

                start_lon, start_lat = coordinates[0]
                end_lon, end_lat = coordinates[-1]

                if osm_u not in graph:
                    graph.add_node(
                        osm_u,
                        x=float(start_lon),
                        y=float(start_lat)
                    )

                if osm_v not in graph:
                    graph.add_node(
                        osm_v,
                        x=float(end_lon),
                        y=float(end_lat)
                    )

                length_m = float(
                    road.get("length_m") or 0
                )

                base_travel_time = float(
                    road.get("base_travel_time_sec") or 1
                )

                free_flow_speed = float(
                    road.get("free_flow_speed_kmph") or 0
                )

                graph.add_edge(
                    osm_u,
                    osm_v,
                    key=osm_key,

                    external_id=road.get("external_id"),

                    road_name=road.get("road_name"),

                    road_class=road.get("road_class"),

                    length_m=length_m,

                    free_flow_speed_kmph=free_flow_speed,

                    base_travel_time_sec=base_travel_time,

                    current_cost=base_travel_time,

                    oneway=bool(road.get("oneway")),

                    lanes=road.get("lanes"), access=road.get("access"), provenance=road.get("provenance","REAL"), signalized=road.get("signalized",False),
                    geometry=geometry
                )

            except Exception as error:
                skipped += 1
                print(
                    "Skipped road:",
                    str(error)
                )

        print(
            f"Graph built: "
            f"{graph.number_of_nodes():,} nodes, "
            f"{graph.number_of_edges():,} edges, "
            f"{skipped:,} skipped"
        )

        build_snap_index(graph)
        return graph

    def get_graph(
        self,
        start_lat,
        start_lon,
        end_lat,
        end_lon
    ):

        (
            min_lon,
            min_lat,
            max_lon,
            max_lat
        ) = self._build_bbox(
            start_lat,
            start_lon,
            end_lat,
            end_lon
        )

        cache_key = self._make_cache_key(
            min_lon,
            min_lat,
            max_lon,
            max_lat
        )

        # Reuse a cached operational area when it fully contains this request.
        for existing_key, bounds in self.cache_bounds.items():
            if existing_key in self.cache and bounds[0] <= min_lon and bounds[1] <= min_lat and bounds[2] >= max_lon and bounds[3] >= max_lat:
                result = self.cache[existing_key].copy()
                result.graph["cache_hit"] = True
                return result
        if cache_key in self.cache and self.cache_bounds.get(cache_key) == (min_lon,min_lat,max_lon,max_lat):

            print(
                "Using cached graph:",
                cache_key
            )

            result = self.cache[cache_key].copy()
            result.graph["cache_hit"] = True
            return result

        print(
            "Requesting roads from Supabase..."
        )

        roads = self.fetch_roads(
            min_lon,
            min_lat,
            max_lon,
            max_lat
        )

        print(
            f"Supabase returned {len(roads):,} road edges"
        )

        if not roads:
            raise RuntimeError(
                "Supabase returned zero roads for this area."
            )

        graph = self.build_graph(
            roads
        )

        if graph.number_of_edges() == 0:
            raise RuntimeError(
                "Road data was returned but graph construction produced zero edges."
            )

        if len(self.cache) >= 6:
            oldest = next(iter(self.cache))
            self.cache.pop(oldest)
            self.cache_bounds.pop(oldest, None)
        self.cache[cache_key] = graph
        self.cache_bounds[cache_key] = (min_lon,min_lat,max_lon,max_lat)

        result = graph.copy()
        result.graph["cache_hit"] = False
        return result


graph_manager = GraphManager()
