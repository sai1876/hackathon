"""SYNTHETIC regression graphs for exact route endpoints, not map cosmetics."""
import unittest
from unittest.mock import patch
import networkx as nx
from shapely.geometry import LineString
from fastapi.testclient import TestClient
from main import app
from graph_manager import graph_manager
from incident_engine import incident_engine
from endpoint_snapping import build_snap_index


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph()
        self.graph.add_node("u", x=78.48, y=17.38)
        self.graph.add_node("v", x=78.50, y=17.38)
        self.add_edge("u", "v", [(78.48, 17.38), (78.50, 17.38)])
        self.client = TestClient(app)
        self.saved = incident_engine.active_incidents
        incident_engine.active_incidents = {}
        self.mock = patch.object(graph_manager, "get_graph", side_effect=lambda *args: self.graph.copy())
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        incident_engine.active_incidents = self.saved

    def add_edge(self, u, v, coords):
        self.graph.add_edge(u, v, key=0, external_id=f"SYNTHETIC-{u}-{v}",
                            geometry=LineString(coords), length_m=2000,
                            base_travel_time_sec=200, current_cost=200)

    def route(self, start=(78.485, 17.38), end=(78.495, 17.38)):
        return self.client.post("/route", json={"start": {"lon": start[0], "lat": start[1]},
                                               "end": {"lon": end[0], "lat": end[1]}})

    def assert_endpoints(self, data):
        for index, name in [(0, "start"), (-1, "end")]:
            actual = data["route"]["geometry"]["coordinates"][index]
            snap = data["snapping"][name]["snapped"]
            self.assertAlmostEqual(actual[0], snap["lon"], places=8)
            self.assertAlmostEqual(actual[1], snap["lat"], places=8)

    def test_long_edge_interiors_use_partial_distance_and_eta(self):
        response = self.route()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["distance_m"], 1000)
        self.assertEqual(data["eta_seconds"], 100)
        self.assertEqual(data["snapping"]["start"]["distance_m"], 0)
        self.assert_endpoints(data)
        self.assertEqual(self.graph.number_of_nodes(), 2)
        self.assertEqual(self.graph.number_of_edges(), 1)
        self.assertEqual(self.graph["u"]["v"][0]["current_cost"], 200)

    def test_oneway_cannot_be_traversed_backwards(self):
        self.assertEqual(self.route((78.495, 17.38), (78.485, 17.38)).status_code, 400)

    def test_reverse_edge_geometry_is_oriented(self):
        # Same stored geometry order on reverse directed edge is repaired at runtime.
        self.add_edge("v", "u", [(78.48, 17.38), (78.50, 17.38)])
        result = self.route((78.495, 17.38), (78.485, 17.38))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["distance_m"], 1000)
        self.assert_endpoints(result.json())
        self.assertEqual(list(self.graph["v"]["u"][0]["geometry"].coords)[0], (78.48, 17.38))

    def test_click_offset_is_explicit_not_included_in_metrics(self):
        result = self.route((78.485, 17.38045), (78.495, 17.38045))
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertAlmostEqual(data["snapping"]["start"]["distance_m"], 50.04, delta=0.1)
        self.assertEqual(data["distance_m"], 1000)
        self.assert_endpoints(data)

    def test_far_click_rejected(self):
        response = self.route((78.485, 17.382), (78.495, 17.38))
        self.assertEqual(response.status_code, 400)
        self.assertIn("100 m", response.json()["detail"])

    def test_closed_edge_cannot_be_bypassed_by_splitting(self):
        self.client.post("/incidents", json={"incident_type": "ROAD_BLOCKAGE", "lat": 17.38, "lon": 78.49})
        self.assertEqual(self.route().status_code, 400)

    def test_node_to_interior_and_interior_to_node(self):
        for start, end in [((78.48, 17.38), (78.49, 17.38)), ((78.49, 17.38), (78.50, 17.38))]:
            data = self.route(start, end).json()
            self.assertEqual(data["distance_m"], 1000)
            self.assert_endpoints(data)

    def test_same_road_position_rejected(self):
        self.assertEqual(self.route((78.49, 17.38), (78.49, 17.38)).status_code, 400)

    def test_inconsistent_geometry_fails_instead_of_drawing_gap(self):
        self.graph.nodes["u"]["x"] = 78.47
        response = self.route()
        self.assertEqual(response.status_code, 400)
        self.assertIn("geometry", response.json()["detail"])

    def test_bends_retained_and_multiple_edges_connected(self):
        self.graph.add_node("w", x=78.51, y=17.40)
        self.add_edge("v", "w", [(78.50, 17.38), (78.51, 17.39), (78.51, 17.40)])
        response = self.route(end=(78.51, 17.395))
        self.assertEqual(response.status_code, 200, response.text)
        coordinates = response.json()["route"]["geometry"]["coordinates"]
        self.assertIn([78.50, 17.38], coordinates)
        self.assertIn([78.51, 17.39], coordinates)
        self.assert_endpoints(response.json())

    def test_cached_index_uses_current_runtime_cost(self):
        build_snap_index(self.graph)
        self.graph["u"]["v"][0]["current_cost"] = float("inf")
        self.assertEqual(self.route().status_code, 400)


if __name__ == "__main__":
    unittest.main()
