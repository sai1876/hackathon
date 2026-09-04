import test from "node:test";
import assert from "node:assert/strict";
import { PollingLifecycleManager, calculateBackoff } from "./pollingLifecycle.ts";

test("TEST 15: Polling lifecycle and backoff specification", async (t) => {
  await t.test("15.1: Correct exponential backoff progression", () => {
    assert.equal(calculateBackoff(0, 3000), 3000, "0 failures should use normal interval (3s)");
    assert.equal(calculateBackoff(1, 3000), 5000, "1 failure should back off to 5s");
    assert.equal(calculateBackoff(2, 3000), 10000, "2 failures should back off to 10s");
    assert.equal(calculateBackoff(3, 3000), 20000, "3 failures should back off to 20s");
    assert.equal(calculateBackoff(4, 3000), 30000, "4 failures should back off to 30s");
    assert.equal(calculateBackoff(10, 3000), 30000, "10 failures should cap at 30s");
  });

  await t.test("15.2: No overlapping fetches while in-flight", async () => {
    let activeCalls = 0;
    let maxConcurrent = 0;
    let resolvePromise;

    const fetcher = () => {
      activeCalls++;
      maxConcurrent = Math.max(maxConcurrent, activeCalls);
      return new Promise((resolve) => {
        resolvePromise = resolve;
      });
    };

    const manager = new PollingLifecycleManager(
      fetcher,
      { onSuccess: () => {}, onError: () => {} },
      3000
    );

    // Start first poll
    const p1 = manager.poll();
    assert.equal(manager.inFlight, true);
    assert.equal(activeCalls, 1);

    // Try to trigger second poll while first is still in flight (non-manual)
    const p2 = manager.poll(false);
    assert.equal(activeCalls, 1, "Second poll must be dropped because one is in flight");

    // Complete the in-flight fetch
    resolvePromise({ ok: true });
    await p1;
    await p2;

    assert.equal(maxConcurrent, 1, "Concurrent requests must never exceed 1");
    manager.cancel();
  });

  await t.test("15.3: AbortController cleanup on cancel / unmount", async () => {
    let capturedSignal = null;

    const fetcher = (signal) => {
      capturedSignal = signal;
      return new Promise(() => {}); // Intentionally never resolves
    };

    const manager = new PollingLifecycleManager(
      fetcher,
      { onSuccess: () => {}, onError: () => {} },
      3000
    );

    void manager.poll();
    assert.ok(capturedSignal, "Signal should be created");
    assert.equal(capturedSignal.aborted, false, "Signal should not be aborted initially");

    // Simulate unmount by calling cancel()
    manager.cancel();
    assert.equal(capturedSignal.aborted, true, "Signal must be aborted upon cancel");
    assert.equal(manager.abortController, null, "AbortController reference must be cleared");
    assert.equal(manager.isCancelled, true);
  });

  await t.test("15.4: No timers running after cancel / unmount", async () => {
    let failFetch;
    const fetcher = () => new Promise((_, reject) => { failFetch = reject; });

    const manager = new PollingLifecycleManager(
      fetcher,
      { onSuccess: () => {}, onError: () => {} },
      3000
    );

    const pollPromise = manager.poll();
    // Simulate error to trigger timer scheduling
    failFetch(new Error("Simulated network timeout"));
    await pollPromise;

    assert.ok(manager.timer !== null, "Timer should be scheduled after failure");

    // Simulate unmount
    manager.cancel();
    assert.equal(manager.timer, null, "Timer must be cleared upon cancel");

    // Extra poll after cancel should be a no-op
    await manager.poll();
    assert.equal(manager.timer, null, "No timer should be scheduled after cancel");
  });

  await t.test("15.5: Successful response resets normal polling interval", async () => {
    let succeeds = false;
    let lastResult = null;

    const fetcher = () => {
      if (!succeeds) {
        return Promise.reject(new Error("Simulated error"));
      }
      return Promise.resolve({ data: "fresh" });
    };

    const manager = new PollingLifecycleManager(
      fetcher,
      {
        onSuccess: (data) => { lastResult = data; },
        onError: () => {}
      },
      3000
    );

    // Fail 3 times
    await manager.poll();
    assert.equal(manager.consecutiveFailures, 1);
    await manager.poll();
    assert.equal(manager.consecutiveFailures, 2);
    await manager.poll();
    assert.equal(manager.consecutiveFailures, 3);
    assert.equal(calculateBackoff(manager.consecutiveFailures, 3000), 20000);

    // Now succeed
    succeeds = true;
    await manager.poll();
    assert.equal(manager.consecutiveFailures, 0, "Success must reset consecutive failures to 0");
    assert.equal(calculateBackoff(manager.consecutiveFailures, 3000), 3000, "Polling interval must reset to normal 3s");
    assert.deepEqual(lastResult, { data: "fresh" });

    manager.cancel();
  });
});
