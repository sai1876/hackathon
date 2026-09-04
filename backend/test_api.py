"""Isolated SYNTHETIC graph fixtures. Never write to Supabase."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from shapely.geometry import LineString
import networkx as nx
from main import app
from graph_manager import GraphManager, graph_manager
from incident_engine import incident_engine


def fixture():
    graph = nx.MultiDiGraph()
    points = {"a": (78.48, 17.38), "b": (78.49, 17.38), "c": (78.49, 17.39)}
    for node, (lon, lat) in points.items():
        graph.add_node(node, x=lon, y=lat)
    for u, v, cost in [("a", "b", 10), ("a", "c", 15), ("c", "b", 15)]:
        graph.add_edge(u, v, key=0, external_id=f"SYNTHETIC-{u}-{v}", road_name="SYNTHETIC",
                       geometry=LineString([points[u], points[v]]), length_m=100,
                       base_travel_time_sec=cost, current_cost=cost)
    graph.graph["cache_hit"] = True
    return graph


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.saved = incident_engine.active_incidents
        incident_engine.active_incidents = {}
        self.graph = fixture()
        self.mock = patch.object(graph_manager, "get_graph", side_effect=lambda *args: self.graph.copy())
        self.mock.start()
        self.payload = {"start": {"lat": 17.38, "lon": 78.48}, "end": {"lat": 17.38, "lon": 78.49}}

    def tearDown(self):
        self.mock.stop()
        incident_engine.active_incidents = self.saved

    def test_health_and_cors(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        result = self.client.options("/route", headers={"Origin": "http://127.0.0.1:3000", "Access-Control-Request-Method": "POST"})
        self.assertEqual(result.headers["access-control-allow-origin"], "http://127.0.0.1:3000")

    def test_route_incident_resolve_preserves_base(self):
        original = self.client.post("/route", json=self.payload).json()
        self.assertEqual(original["eta_seconds"], 10)
        for key in ["graph_load_ms", "nearest_node_ms", "route_compute_ms", "total_ms"]:
            self.assertGreaterEqual(original[key], 0)
        created = self.client.post("/incidents", json={"incident_type": "ROAD_BLOCKAGE", "lat": 17.38, "lon": 78.485}).json()
        self.assertEqual(created["provenance"], "SYNTHETIC")
        detour = self.client.post("/route", json=self.payload).json()
        self.assertEqual(detour["eta_seconds"], 45)
        self.assertEqual(detour["incidents"][0]["affected_geometry"]["type"], "LineString")
        self.assertEqual(self.graph["a"]["b"][0]["current_cost"], 10)
        self.assertEqual(self.client.delete(f"/incidents/{created['id']}").status_code, 200)
        self.assertEqual(self.client.post("/route", json=self.payload).json()["eta_seconds"], 10)
        self.assertEqual(self.client.delete(f"/incidents/{created['id']}").status_code, 404)

    def test_distant_incident_does_not_block(self):
        self.client.post("/incidents", json={"incident_type": "ROAD_BLOCKAGE", "lat": 18, "lon": 79})
        result = self.client.post("/route", json=self.payload).json()
        self.assertEqual(result["eta_seconds"], 10)
        self.assertEqual(result["incidents"][0]["affected_edges"], [])

    def test_invalid_and_same_node(self):
        self.assertEqual(self.client.post("/route", json={"start": {"lat": 999, "lon": 0}, "end": self.payload["end"]}).status_code, 422)
        self.assertEqual(self.client.post("/route", json={"start": self.payload["start"], "end": self.payload["start"]}).status_code, 400)

    def test_disconnected_route(self):
        self.graph.remove_edge("a", "b", 0)
        self.graph.remove_edge("a", "c", 0)
        self.assertEqual(self.client.post("/route", json=self.payload).status_code, 400)

    def test_cache_hit_and_copy(self):
        manager = GraphManager()
        with patch.object(manager, "fetch_roads", return_value=[{}]), patch.object(manager, "build_graph", return_value=fixture()):
            first = manager.get_graph(17.38, 78.48, 17.38, 78.49)
            first["a"]["b"][0]["current_cost"] = 999
            second = manager.get_graph(17.38, 78.48, 17.38, 78.49)
        self.assertFalse(first.graph["cache_hit"])
        self.assertTrue(second.graph["cache_hit"])
        self.assertEqual(second["a"]["b"][0]["current_cost"], 10)


if __name__ == "__main__":
    unittest.main()
