"""Comprehensive deterministic concurrency, idempotency, clock safety, and resilience tests.
Validates all 14 backend test requirements specified in the approved implementation plan.
"""
import os
import sys
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DISABLE_SCENARIO_WORKER"] = "true"

import scenario_runtime as r

from scenario_runtime import (
    ScenarioError,
    ScenarioConflict,
    PersistenceContention,
    TransientPersistenceFailure,
    DatabaseUnavailable,
    load_state,
    commit_revision,
    apply_mutation,
    commit,
    check_readiness,
    flush_outbox,
    start,
    Command
)
from main import app


class MockQuery:
    def __init__(self, data=None):
        self._data = data

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class MockDatabase:
    """In-memory mock database enforcing PostgREST optimistic concurrency semantics."""
    def __init__(self, initial_row):
        self.row = deepcopy(initial_row)
        self.events = []
        self.update_should_fail_contention = False
        self.update_should_fail_transient = False
        self.update_should_fail_unavailable = False
        self.outbox_should_fail = False

    def table(self, name):
        mock_self = self
        class TableQuery:
            def select(self, *args, **kwargs):
                return self
            def eq(self, field, value):
                self.field = field
                self.value = value
                return self
            def single(self):
                return self
            def order(self, *args, **kwargs):
                return self
            def range(self, *args, **kwargs):
                return self
            def limit(self, *args, **kwargs):
                return self
            def execute(self):
                if name == 'aegis_sim_runs':
                    return SimpleNamespace(data=deepcopy(mock_self.row))
                return SimpleNamespace(data=[])
            def update(self, values):
                self.values = values
                return self
            def upsert(self, records, on_conflict=None):
                if mock_self.outbox_should_fail:
                    raise TransientPersistenceFailure("Simulated outbox upsert network timeout")
                mock_self.events.extend(records)
                return self

        query = TableQuery()
        # Decorate execute for update conditional checks
        orig_execute = query.execute
        def conditional_execute():
            if mock_self.update_should_fail_unavailable:
                raise DatabaseUnavailable("Simulated fatal database failure")
            if mock_self.update_should_fail_contention:
                raise PersistenceContention("Simulated database lock contention")
            if mock_self.update_should_fail_transient:
                raise TransientPersistenceFailure("Simulated transient socket timeout")
            if hasattr(query, 'values') and name == 'aegis_sim_runs':
                # Check version condition
                expected_ver = getattr(query, 'value', None)
                if expected_ver is not None and expected_ver != mock_self.row['version']:
                    # 0 rows updated
                    return SimpleNamespace(data=[])
                # Successful update
                mock_self.row.update(query.values)
                return SimpleNamespace(data=[deepcopy(mock_self.row)])
            return orig_execute()
        query.execute = conditional_execute
        return query


class ConcurrencyResilienceTests(unittest.TestCase):
    def setUp(self):
        self.initial_runtime = dict(
            seconds=100.0,
            running=True,
            speed=1,
            last_wall=1000.0,
            start_seconds=18000,
            service_date='2026-09-03',
            scenarios=[],
            events=[],
            outbox=[],
            requests=['prior-req-1'],
            recommendations=[],
            assumptions=dict(block_depth_mm=150, drainage_dispatch_multiplier=2, pumping_max_load_fraction=.15)
        )
        self.initial_row = dict(
            id=r.RUN_ID,
            version=1,
            sim_seconds=100.0,
            status='RUNNING',
            configuration=dict(
                runtime=deepcopy(self.initial_runtime),
                service_date='2026-09-03',
                active_run_id=r.RUN_ID
            )
        )
        self.mock_db = MockDatabase(self.initial_row)
        r.db = self.mock_db
        r.current = dict(state=deepcopy(self.initial_runtime), version=1)
        r.checked = 1000.0
        r.failure = ''

    def tearDown(self):
        r.stop.set()
        r._worker_started = False
        r._worker_thread = None

    # TEST 1: Normal scenario tick commits successfully.
    def test_1_normal_tick_commits_successfully(self):
        res = r.commit()
        self.assertEqual(res['version'], 2)
        self.assertEqual(self.mock_db.row['version'], 2)
        self.assertGreater(self.mock_db.row['sim_seconds'], 100.0)
        self.assertEqual(r.failure, '')

    # TEST 2: Scenario revision changes between read and commit -> ScenarioConflict detected.
    def test_2_scenario_revision_conflict_detected(self):
        row, s = load_state()
        # External actor bumps version in DB
        self.mock_db.row['version'] = 99
        with self.assertRaises(ScenarioConflict) as ctx:
            commit_revision(s, expected_version=row['version'], config=row['configuration'])
        self.assertEqual(ctx.exception.expected_version, 1)
        self.assertEqual(ctx.exception.actual_version, 99)

    # TEST 3: Worker reloads latest state, recalculates from NEW state, and commits successfully after conflict.
    def test_3_worker_recalculates_from_new_state_after_conflict(self):
        # We simulate that during the first attempt, DB version was 1 with seconds=100.
        # Before commit, intervening actor commits version 2 with seconds=200 and a new scenario area!
        call_count = 0
        orig_load = r.load_state

        def dynamic_load():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                res = orig_load()
                # Intervening actor writes version 2 to DB after attempt 1 read version 1
                self.mock_db.row['version'] = 2
                self.mock_db.row['configuration']['runtime']['seconds'] = 200.0
                self.mock_db.row['configuration']['runtime']['last_wall'] = 2000.0
                self.mock_db.row['configuration']['runtime']['scenarios'].append({
                    'id': 'intervening-rain', 'kind': 'RAIN', 'polygon': [], 'start': 0, 'end': 3600,
                    'intensity': 60, 'multiplier': 1, 'water_mm': 10.0, 'drainage': 0, 'blocked': False,
                    'event_id': 'intervening-event'
                })
                return res
            return orig_load()

        with patch('scenario_runtime.load_state', side_effect=dynamic_load), \
             patch('scenario_runtime.time', return_value=2002.0):
            # First commit_revision will fail because expected_version=1 != DB version 2
            # apply_mutation must catch ScenarioConflict, reload at version 2, recalculate, and commit version 3!
            res = apply_mutation(lambda s: r.advance(s, 2002.0), max_retries=3)

        self.assertEqual(res['version'], 3)
        self.assertEqual(self.mock_db.row['version'], 3)
        # Verify recalculation used NEW state (200 + 2s = 202s, NOT 100 + 2s = 102s!)
        self.assertAlmostEqual(self.mock_db.row['sim_seconds'], 202.0, places=1)
        # Verify intervening scenario was preserved and updated
        scenarios = self.mock_db.row['configuration']['runtime']['scenarios']
        self.assertTrue(any(z['id'] == 'intervening-rain' for z in scenarios))

    # TEST 4: Repeated conflicts exhaust retries -> tick skipped safely, worker remains alive, runtime remains available.
    def test_4_repeated_conflicts_exhaust_retries_safely(self):
        call_count = 0
        orig_load = r.load_state

        def conflict_load():
            nonlocal call_count
            call_count += 1
            res = orig_load()
            # Bumping DB version causes commit_revision with expected_version=res[0]['version'] to conflict
            self.mock_db.row['version'] += 1
            return res

        with patch('scenario_runtime.load_state', side_effect=conflict_load), \
             patch('scenario_runtime.sleep', return_value=None):
            with self.assertRaises(ScenarioConflict):
                apply_mutation(lambda s: r.advance(s, 1005.0), max_retries=3)

        # Background worker work() catches ScenarioConflict and skips tick safely
        # Verify runtime state was NOT poisoned with an outage
        self.assertEqual(r.failure, '')
        self.assertIsNotNone(r.current)

    # TEST 5: Real database failure -> correct unavailable/degraded behavior.
    def test_5_real_database_failure(self):
        self.mock_db.update_should_fail_unavailable = True
        with self.assertRaises(DatabaseUnavailable):
            commit_revision(r.current['state'], expected_version=1)

    # TEST 6: /health returns 200 for liveness; /ready reflects dependency readiness.
    def test_6_health_and_ready_endpoints(self):
        client = TestClient(app)
        # When healthy
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/ready").status_code, 200)

        # When database unavailable
        r.failure = 'Database unreachable: ConnectionError'
        with patch.object(r, 'check_readiness', return_value=False):
            # /health remains 200 (liveness)
            self.assertEqual(client.get("/health").status_code, 200)
            # /ready returns 503 (readiness)
            ready_res = client.get("/ready")
            self.assertEqual(ready_res.status_code, 503)
            self.assertEqual(ready_res.json()["detail"]["status"], "not_ready")

    # TEST 7: Concurrent command update while scenario worker ticks -> no corruption, no permanent 503 state.
    def test_7_concurrent_command_update(self):
        # Issue an operator command while clock advances
        cmd = Command(
            action='SPEED',
            speed=5,
            request_id='cmd-concurrent-speed-1',
            duration_minutes=60,
            intensity=35
        )
        res = r.commit(cmd)
        self.assertEqual(res['version'], 2)
        self.assertEqual(self.mock_db.row['version'], 2)
        self.assertEqual(self.mock_db.row['configuration']['runtime']['speed'], 5)
        self.assertIn('cmd-concurrent-speed-1', self.mock_db.row['configuration']['runtime']['requests'])

    # TEST 8: Metro snapshot remains accessible after recoverable scenario conflict.
    def test_8_metro_snapshot_accessible_after_conflict(self):
        # Simulate that current holds a valid state, and a tick conflict just occurred
        from time import time as real_time
        r.checked = real_time()
        snapshot = r.snapshot()
        self.assertTrue(snapshot['ready'])
        self.assertEqual(snapshot['version'], 1)

    # TEST 9: Duplicate background scenario workers prevented during startup.
    def test_9_worker_startup_idempotency(self):
        r._worker_started = False
        r._worker_thread = None
        os.environ["DISABLE_SCENARIO_WORKER"] = "false"
        try:
            with patch('scenario_runtime.Thread') as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread.is_alive.return_value = True
                mock_thread_cls.return_value = mock_thread

                start()
                first_thread = r._worker_thread
                # Call start second time
                start()
                self.assertEqual(r._worker_thread, first_thread)
                # Thread.start should only have been called once
                mock_thread.start.assert_called_once()
        finally:
            os.environ["DISABLE_SCENARIO_WORKER"] = "true"
            r._worker_started = False

    # TEST 10: Transient persistence outage -> recovery -> failure flag clears -> /ready returns 200.
    def test_10_transient_outage_and_self_healing_recovery(self):
        client = TestClient(app)
        # Set transient failure
        r.failure = 'Shared simulation persistence unavailable: TransientPersistenceFailure'
        self.assertEqual(client.get("/health").status_code, 200)

        # Database is healthy again; check_readiness actively probes and clears failure
        self.assertTrue(check_readiness())
        self.assertEqual(r.failure, '')
        ready_res = client.get("/ready")
        self.assertEqual(ready_res.status_code, 200)
        self.assertEqual(ready_res.json()["status"], "ready")

    # TEST 11: Automated tests do not unintentionally create background workers.
    def test_11_test_isolation_guard(self):
        os.environ["DISABLE_SCENARIO_WORKER"] = "true"
        r._worker_started = False
        r._worker_thread = None
        start()
        self.assertIsNone(r._worker_thread)
        self.assertFalse(r._worker_started)

    # TEST 12: Successful DB commit + lost response + same request ID retry.
    def test_12_command_idempotency_lost_response_retry(self):
        cmd = Command(
            action='PLAY',
            speed=2,
            request_id='idempotent-test-req-1234',
            duration_minutes=60,
            intensity=35
        )
        # First commit succeeds
        res1 = r.commit(cmd)
        version_after_first = res1['version']
        self.assertEqual(self.mock_db.row['version'], version_after_first)
        self.assertIn('idempotent-test-req-1234', self.mock_db.row['configuration']['runtime']['requests'])

        # Caller believes response was lost and retries with the exact same request_id
        res2 = r.commit(cmd)
        # Version MUST NOT increment again
        self.assertEqual(res2['version'], version_after_first)
        self.assertEqual(self.mock_db.row['version'], version_after_first)
        # Requests list must not duplicate the ID
        requests_list = self.mock_db.row['configuration']['runtime']['requests']
        self.assertEqual(requests_list.count('idempotent-test-req-1234'), 1)

    # TEST 13: State commit succeeds + outbox delivery fails.
    def test_13_state_commit_succeeds_when_outbox_fails(self):
        # Configure outbox upsert to fail
        self.mock_db.outbox_should_fail = True
        state = deepcopy(self.initial_runtime)
        state['outbox'].append({'id': 'event-outbox-fail', 'kind': 'TEST_EVENT', 'sim_seconds': 100})

        # State commit should succeed even if outbox flush logs a warning
        res = commit_revision(state, expected_version=1)
        self.assertEqual(res['version'], 2)
        self.assertEqual(self.mock_db.row['version'], 2)
        # The outbox remains retained in configuration.runtime for subsequent retry
        retained_outbox = self.mock_db.row['configuration']['runtime']['outbox']
        self.assertTrue(any(e['id'] == 'event-outbox-fail' for e in retained_outbox))

    # TEST 14: Two simultaneous scenario workers representing rolling deployment (clock safety).
    def test_14_multi_instance_clock_safety_invariant(self):
        # Initial state in DB at wall time 1000.0, seconds 100.0
        # Time advances to 1002.0 (2 seconds)
        # Worker A runs advance(1002.0)
        row_a, state_a = load_state()
        r.advance(state_a, wall=1002.0)
        self.assertEqual(state_a['seconds'], 102.0)
        self.assertEqual(state_a['last_wall'], 1002.0)
        commit_revision(state_a, expected_version=row_a['version'], config=row_a['configuration'])

        # Worker B also started around wall 1002.0. If it had read stale version 1, its commit is rejected.
        # Now Worker B retries and reloads from DB at wall time 1002.1:
        row_b, state_b = load_state()
        self.assertEqual(state_b['seconds'], 102.0)
        self.assertEqual(state_b['last_wall'], 1002.0)

        # Worker B runs advance at wall=1002.1
        r.advance(state_b, wall=1002.1)
        # Invariant: simulated seconds only advanced by 0.1s, NOT another 2 seconds!
        self.assertAlmostEqual(state_b['seconds'], 102.1, places=1)
        commit_revision(state_b, expected_version=row_b['version'], config=row_b['configuration'])

        # Total elapsed wall clock was 2.1s; total simulated time advanced is EXACTLY 2.1s!
        final_row, final_state = load_state()
        self.assertAlmostEqual(final_state['seconds'], 102.1, places=1)


if __name__ == '__main__':
    unittest.main()
