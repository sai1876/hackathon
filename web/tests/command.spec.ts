import { test, expect } from "@playwright/test";
import type { Corridor, OperationsSnapshot } from "../src/types/dispatch";
import type { RouteResult } from "../src/types/aegis";
const point = { lat: 17.415, lon: 78.4867 };
function snapshot(): OperationsSnapshot {
  const route = { route: { type: "Feature", properties: { engine: "NetworkX", source: "SYNTHETIC TEST FIXTURE" }, geometry: { type: "LineString", coordinates: [[78.4867, 17.415], [78.49, 17.415]] } }, distance_m: 350, distance_km: .35, eta_seconds: 30, eta_minutes: .5, total_ms: 1, route_edges: [{ external_id: "test-edge", road_name: "Test road" }], snapping: { method: "ROAD_SEGMENT", max_distance_m: 100, start: { requested: point, snapped: point, distance_m: 0 }, end: { requested: { lat: 17.415, lon: 78.49 }, snapped: { lat: 17.415, lon: 78.49 }, distance_m: 0 } }, incidents: [] } as unknown as RouteResult;
  return { revision: 1, server_time: new Date().toISOString(), storage: "PROCESS_LOCAL", corridors: [{ id: "test-corridor", ambulance_id: "TEST-108", destination_name: "Test hospital", priority: "URGENT", provenance: "SYNTHETIC", status: "PENDING", version: 1, start: point, end: { lat: 17.415, lon: 78.49 }, position: point, position_at: new Date().toISOString(), position_provenance: "SYNTHETIC", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), route, route_state: "AVAILABLE", route_error: null, eta_change_seconds: 0, decisions: [] }], events: [], exercises: [], incidents: [], recommendations: [], provenance: { roads: "TEST", routing: "TEST", telemetry: "TEST", persistence: "TEST" } };
}

test("traffic has no planner; approval gates route and vehicle visibility", async ({ page }) => {
  const state = snapshot();
  await page.route("**/operations", r => r.fulfill({ json: state }));
  await page.route("**/corridors/test-corridor/decision", r => {
    const body = r.request().postDataJSON();
    expect(body.version).toBe(1);
    expect(body.decision).toBe("APPROVE");
    state.corridors[0].status = "APPROVED"; state.corridors[0].version++;
    return r.fulfill({ json: state.corridors[0] });
  });
  await page.goto("/traffic");
  await expect(page.getByRole("heading", { name: "Traffic operations", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pick pickup", exact: true })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Show ambulance route and location on map" })).toHaveCount(0);
  await page.getByLabel("Traffic operator", { exact: true }).fill("Test operator");
  await page.getByLabel("Decision reason", { exact: true }).fill("Route reviewed in test");
  await page.getByRole("button", { name: "Approve corridor", exact: true }).click();
  const toggle = page.getByRole("checkbox", { name: "Show ambulance route and location on map" });
  await expect(toggle).toBeVisible(); await expect(toggle).not.toBeChecked();
  await toggle.check();
  await expect(page.locator(".ambulance-marker")).toHaveCount(1);
  await expect(page.getByTestId("traffic-map")).toHaveAttribute("data-route-features", /^[1-9]\d*$/, { timeout: 30000 });
  await toggle.uncheck();
  await expect(page.locator(".ambulance-marker")).toHaveCount(0);
  await expect(page.getByTestId("traffic-map")).toHaveAttribute("data-route-features", "0");
});

test("ambulance map selections submit a backend corridor request", async ({ page }) => {
  const state = snapshot(); state.corridors = [];
  await page.route("**/operations", r => r.fulfill({ json: state }));
  let payload: Record<string, unknown> | undefined;
  await page.route("**/corridors", r => {
    payload = r.request().postDataJSON();
    const item = { ...snapshot().corridors[0], ...payload } as Corridor;
    state.corridors.push(item);
    return r.fulfill({ json: item });
  });
  await page.goto("/ambulance");
  await page.getByLabel("Ambulance identifier", { exact: true }).fill("TEST-108");
  await page.getByLabel("Destination name", { exact: true }).fill("Test hospital");
  await page.getByLabel("Synthetic exercise request", { exact: true }).check();
  await expect(page.getByText("Loading Hyderabad basemap…")).toBeHidden({ timeout: 30000 });
  const canvas = page.locator(".maplibregl-canvas");
  await page.getByRole("button", { name: "Pick pickup", exact: true }).click();
  await canvas.click({ position: { x: 110, y: 230 } });
  await canvas.click({ position: { x: 200, y: 300 } });
  await page.getByRole("button", { name: "Request corridor", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Awaiting traffic review");
  expect(payload?.ambulance_id).toBe("TEST-108");
  expect(payload?.provenance).toBe("SYNTHETIC");
  expect(payload?.request_key).toBeTruthy();
  expect(payload?.start).not.toEqual(payload?.end);
});

test("stale backend is explicit and decisions are disabled", async ({ page }) => {
  await page.route("**/operations", r => r.fulfill({ status: 503, json: { detail: "Test outage" } }));
  await page.goto("/traffic");
  await expect(page.locator(".dispatch-error[role=alert]")).toContainText("Test outage");
  await expect(page.getByText("BACKEND DATA STALE", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Inject backend event", exact: true })).toBeDisabled();
});


test("clicking displayed corridor targets its road instead of a nearer side street", async ({ page }) => {
  const state = snapshot();
  state.corridors[0].status = "APPROVED";
  const route = state.corridors[0].route!;
  route.route_segments = { type: "FeatureCollection", features: [{ type: "Feature", properties: { external_id: "test-edge", road_name: "Test road" }, geometry: route.route.geometry }] };
  await page.route("**/operations", r => r.fulfill({ json: state }));
  let target: string | undefined;
  await page.route("**/simulation/events", r => { target = r.request().postDataJSON().target_edge_id; return r.fulfill({ json: { id: "test-event" } }); });
  await page.goto("/traffic");
  await page.getByRole("checkbox", { name: "Show ambulance route and location on map" }).check();
  await expect(page.getByTestId("traffic-map")).toHaveAttribute("data-route-features", /^[1-9]\d*$/, { timeout: 30000 });
  await page.getByRole("button", { name: "Pick event location", exact: true }).click();
  const canvas = page.locator(".maplibregl-canvas"); const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error("Map not available");
  await canvas.click({ position: { x: bounds.width / 2, y: bounds.height / 2 } });
  await expect(page.getByText(/Selected route segment/)).toBeVisible();
  await page.getByRole("button", { name: "Inject backend event", exact: true }).click();
  await expect.poll(() => target).toBe("test-edge");
});
