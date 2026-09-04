"""Operational workflow integration tests on the existing synthetic graph fixture."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import test_api
from operations_engine import operations
from incident_engine import incident_engine


class OperationsTests(unittest.TestCase):
    def setUp(self):
        test_api.ApiTests.setUp(self)
        self.saved_operations = deepcopy(operations.__dict__)
        operations.__init__()
        self.counter = 0

    def tearDown(self):
        operations.__dict__.clear()
        operations.__dict__.update(self.saved_operations)
        test_api.ApiTests.tearDown(self)

    def create(self, provenance="SYNTHETIC"):
        self.counter += 1
        response = self.client.post("/corridors", json=dict(**self.payload, ambulance_id="TEST-108",
            destination_name="Test hospital", provenance=provenance, request_key=f"request-{self.counter}"))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def decision(self, item, decision="APPROVE"):
        return self.client.post(f"/corridors/{item['id']}/decision", json=dict(version=item["version"],
            decision=decision, operator="Test traffic operator", reason="Reviewed test route"))

    def current(self, identifier):
        return next(c for c in self.client.get("/operations").json()["corridors"] if c["id"] == identifier)

    def test_request_approval_movement_and_completion(self):
        item = self.create()
        self.assertEqual(item["status"], "PENDING")
        path = f"/simulation/corridors/{item['id']}/advance"
        self.assertEqual(self.client.post(path, json={"version": item["version"]}).status_code, 409)
        item = self.decision(item).json()
        result = self.client.post(path, json={"version": item["version"], "seconds": 2}).json()
        self.assertEqual(result["status"], "APPROVED")
        self.assertGreater(result["position"]["lon"], item["position"]["lon"])
        self.assertLess(result["route"]["eta_seconds"], item["route"]["eta_seconds"])
        result = self.client.post(path, json={"version": result["version"], "seconds": 60}).json()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["position"], self.payload["end"])
        self.assertEqual(self.client.post(path, json={"version": result["version"]}).status_code, 409)

    def test_legacy_incident_reroutes_and_requires_new_approval(self):
        item = self.decision(self.create()).json()
        created = self.client.post("/incidents", json={"incident_type": "ROAD_BLOCKAGE", "lat": 17.38, "lon": 78.485}).json()
        changed = self.current(item["id"])
        self.assertEqual(changed["status"], "PENDING")
        self.assertEqual(changed["route"]["eta_seconds"], 45)
        self.assertEqual(changed["eta_change_seconds"], 35)
        self.assertEqual(self.decision(item).status_code, 409)
        self.assertEqual(self.decision(changed).status_code, 200)
        self.client.delete(f"/incidents/{created['id']}")
        restored = self.current(item["id"])
        self.assertEqual(restored["status"], "PENDING")
        self.assertEqual(restored["route"]["eta_seconds"], 10)
        self.assertEqual(restored["eta_change_seconds"], -35)

    def test_reject_is_terminal_and_reason_required(self):
        item = self.create()
        rejected = self.decision(item, "REJECT").json()
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertEqual(self.decision(rejected).status_code, 409)
        self.assertEqual(self.client.post(f"/corridors/{rejected['id']}/reevaluate", json={"version": rejected["version"]}).status_code, 409)
        item = self.create()
        self.assertEqual(self.client.post(f"/corridors/{item['id']}/decision", json=dict(version=item["version"], decision="APPROVE", operator="  ", reason="   ")).status_code, 422)

    def test_unavailable_route_and_retry(self):
        with patch("operations_engine.route_engine.calculate_route", side_effect=RuntimeError("No path")):
            item = self.create()
        self.assertIsNone(item["route"])
        self.assertEqual(self.decision(item).status_code, 409)
        self.assertEqual(self.client.post(f"/corridors/{item['id']}/reevaluate", json={"version": item["version"]}).status_code, 200)
        self.assertIsNotNone(self.current(item["id"])["route"])

    def test_simulation_causal_lifecycle(self):
        item = self.decision(self.create()).json()
        event = self.client.post("/simulation/events", json=dict(lat=17.38, lon=78.485, incident_type="WATERLOGGING")).json()
        snap = self.client.get("/operations").json()
        self.assertEqual(event["status"], "AWAITING_ACTION")
        self.assertEqual(snap["incidents"][0]["provenance"], "SYNTHETIC")
        self.assertEqual(self.current(item["id"])["status"], "PENDING")
        kinds = [e["kind"] for e in snap["events"]]
        self.assertIn("REAPPROVAL_REQUIRED", kinds)
        self.assertIn("EXERCISE_AWAITING_ACTION", kinds)
        self.assertGreater(len(snap["recommendations"]), 0)
        self.client.delete(f"/incidents/{event['incident_id']}")
        snap = self.client.get("/operations").json()
        self.assertEqual(snap["exercises"][0]["status"], "RESOLVED")
        self.assertEqual(snap["incidents"], [])

    def test_real_report_cannot_be_simulated(self):
        item = self.decision(self.create("OPERATOR_REPORTED")).json()
        self.assertEqual(self.client.post(f"/simulation/corridors/{item['id']}/advance", json={"version": item["version"]}).status_code, 409)
        moved = self.client.post(f"/corridors/{item['id']}/position", json=dict(version=item["version"], lat=17.38, lon=78.481)).json()
        self.assertEqual(moved["position_provenance"], "OPERATOR_REPORTED")
        self.assertEqual(moved["status"], "PENDING")

    def test_create_idempotency_and_conflicts(self):
        item = self.create()
        retry = self.client.post("/corridors", json=item["request_payload"])
        self.assertEqual(retry.json()["id"], item["id"])
        changed = dict(item["request_payload"], ambulance_id="OTHER")
        self.assertEqual(self.client.post("/corridors", json=changed).status_code, 409)
        self.assertEqual(len(self.client.get("/operations").json()["corridors"]), 1)

    def test_concurrent_decisions_only_one_succeeds(self):
        item = self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.decision(item).status_code, range(2)))
        self.assertEqual(sorted(results), [200, 409])

    def test_revalidation_failure_revokes_approval(self):
        item = self.decision(self.create()).json()
        with patch("operations_engine.route_engine.calculate_route", side_effect=RuntimeError("No path")):
            self.client.post("/simulation/events", json=dict(lat=17.38, lon=78.485, incident_type="ACCIDENT"))
        changed = self.current(item["id"])
        self.assertIsNone(changed["route"])
        self.assertEqual(changed["status"], "PENDING")

    def test_snapshot_is_read_only_and_no_automatic_movement(self):
        item = self.decision(self.create()).json()
        first = self.current(item["id"])
        second = self.current(item["id"])
        self.assertEqual(first["position"], second["position"])
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(self.client.get("/operations").json()["storage"], "PROCESS_LOCAL")


if __name__ == "__main__":
    unittest.main()
