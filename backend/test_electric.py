import tempfile
import unittest
from pathlib import Path
from fastapi import HTTPException
from electric_engine import ElectricWorld, ElectricAction, generate


class ElectricTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"world.sqlite3"
        self.world = ElectricWorld(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def act(self, action, **kw):
        return self.world.act(ElectricAction(version=self.world.snapshot()["version"], action=action,
            operator="Test operator", note="Test exercise evidence", **kw))

    def repair(self, task):
        for action in ["ASSIGN", "START", "COMPLETE", "VERIFY"]:
            self.act(action, task_id=task, crew="Crew 1")

    def test_generation_counts_and_connections(self):
        assets = self.world.assets
        self.assertEqual(assets, generate())
        counts = self.world.snapshot()["counts"]
        self.assertEqual([counts[k] for k in ["SUBSTATION", "POWER_TRANSFORMER", "FEEDER_11KV", "DISTRIBUTION_TRANSFORMER"]], [20,38,95,6300])
        for a in assets.values():
            seen = set()
            while a["parent"]:
                self.assertNotIn(a["id"], seen)
                seen.add(a["id"])
                a = assets[a["parent"]]

    def test_road_layout_is_irregular_and_connections_follow_geometry(self):
        stations = [a for a in self.world.assets.values() if a["kind"] == "SUBSTATION"]
        self.assertEqual(len({a["lon"] for a in stations}), 20)
        self.assertEqual(len({a["lat"] for a in stations}), 20)
        transformers = [a for a in self.world.assets.values() if a["kind"] == "DISTRIBUTION_TRANSFORMER"]
        self.assertEqual(len({(a["lon"], a["lat"]) for a in transformers}), 6300)
        feeders = [a for a in self.world.assets.values() if a["kind"] == "FEEDER_11KV"]
        self.assertTrue(all(len(a["connection_geometry"]["coordinates"]) > 2 for a in feeders))
        for a in feeders + transformers:
            line = a["connection_geometry"]["coordinates"]
            parent = self.world.assets[a["parent"]]
            self.assertEqual(line[0], [parent["lon"], parent["lat"]])
            self.assertEqual(line[-1], [a["lon"], a["lat"]])
            self.assertEqual(a["layout_version"], "osm-constrained-v2")

    def test_fault_descendants_only_and_restart(self):
        state = self.act("FAULT", asset_id="F-001")
        self.assertIn("DT-00001", state["off_ids"])
        self.assertIn("SIG-001", state["off_ids"])
        self.assertNotIn("F-002", state["off_ids"])
        self.assertNotIn("SS-001", state["off_ids"])
        self.assertEqual(state, ElectricWorld(self.path).snapshot())

    def test_overlapping_faults_and_queue_recovery(self):
        first = self.act("FAULT", asset_id="SS-001")["tasks"][0]["id"]
        second = self.act("FAULT", asset_id="F-001")["tasks"][1]["id"]
        state = self.act("ADVANCE")
        self.assertEqual(state["queues"]["SIG-001"], 12)
        self.repair(first)
        state = self.world.snapshot()
        self.assertIn("SIG-001", state["off_ids"])
        self.assertNotIn("SIG-002", state["off_ids"])
        self.repair(second)
        self.assertEqual(self.world.snapshot()["queues"]["SIG-001"], 12)
        self.assertEqual(self.act("ADVANCE")["queues"]["SIG-001"], 0)

    def test_transition_and_stale_state_rejected(self):
        task = self.act("FAULT", asset_id="F-001")["tasks"][0]["id"]
        for action in ["START", "COMPLETE", "VERIFY"]:
            with self.assertRaises(HTTPException):
                self.act(action, task_id=task)
        with self.assertRaises(HTTPException):
            self.world.act(ElectricAction(version=0, action="ADVANCE", operator="test", note="stale"))
        self.assertEqual(self.world.snapshot()["version"], 1)

    def test_map_bounds_and_detail(self):
        overview = self.world.geometry(78,17,79,18,11,"")
        self.assertEqual(len(overview["features"]), 20)
        low = self.world.geometry(78,17,79,18,11,"SS-001")
        high = self.world.geometry(78,17,79,18,15,"SS-001")
        self.assertGreater(len(high["features"]), len(low["features"]))
        self.assertEqual(len(self.world.geometry(79,18,80,19,15,"SS-001")["features"]), 0)
        self.assertEqual(self.world.detail("DT-00001")["upstream"][:3], ["DT-00001", "F-001", "PT-001-1"])


if __name__ == "__main__":
    unittest.main()
