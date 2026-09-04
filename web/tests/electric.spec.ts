import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test.use({ actionTimeout: 15000 });
let server: ChildProcess;
test.beforeAll(async () => {
  const folder = mkdtempSync(join(tmpdir(), "aegis-electric-e2e-"));
  server = spawn("D:/aegisgrid/.venv/Scripts/python.exe", ["-c", "from fastapi import FastAPI; from electric_engine import router; import uvicorn; app=FastAPI(); app.include_router(router); uvicorn.run(app,host='127.0.0.1',port=8002)"], {
    cwd: "D:/aegisgrid/backend", windowsHide: true, env: { ...process.env, ELECTRIC_DB_PATH: join(folder, "electric.sqlite3") }, stdio: "ignore",
  });
  await expect.poll(async () => { try { return (await fetch("http://127.0.0.1:8002/electric")).status; } catch { return 0; } }).toBe(200);
});
test.afterAll(() => { server?.kill(); });

test("electrical fault, queue growth, crew repair and verified restoration", async ({ page }) => {
  // Use a disposable real backend; do not mutate the operator's saved world.
  await page.route("http://127.0.0.1:8001/electric**", async route => {
    const response = await route.fetch({ url: route.request().url().replace(":8001", ":8002") });
    await route.fulfill({ response });
  });
  await page.goto("/electric-command");
  await expect(page.getByRole("heading", { name: "Electric Command", exact: true })).toBeVisible();
  await expect(page.getByText("6,300", { exact: true })).toBeVisible();
  await expect.poll(async () => Number(await page.getByLabel("Synthetic electrical network map", { exact: true }).getAttribute("data-visible-assets")), { timeout: 30000 }).toBeGreaterThan(0);

  await page.getByLabel("Find asset by ID").fill("F-001");
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await page.getByText("Advanced: inject an equipment fault", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Inject synthetic fault at F-001", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Inject synthetic fault at F-001", exact: true }).click();
  expect(await page.getByLabel("Fault operator", { exact: true }).evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
  await page.getByLabel("Fault operator", { exact: true }).fill("Command test");
  await page.getByLabel("Fault reason", { exact: true }).fill("Synthetic feeder failure exercise");
  await page.getByRole("button", { name: "Inject synthetic fault at F-001", exact: true }).click();
  await expect(page.getByText("WITHOUT SUPPLY", { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "Advance simulation by 1 minute" }).click();
  await expect(page.getByText("12 modeled queued vehicles", { exact: false })).toBeVisible();
  await page.getByLabel("Assign to crew").fill("Crew Alpha");
  await page.getByRole("button", { name: "Assign crew", exact: true }).click();
  await page.getByRole("link", { name: "Lineman", exact: true }).click();
  await page.getByLabel("Operator", { exact: true }).fill("Crew Alpha");
  await page.getByLabel("Reason / repair evidence").fill("Inspected synthetic feeder; exercise repair complete");
  await page.getByRole("button", { name: "Start repair" }).click();
  await page.getByRole("button", { name: "Submit repair for verification" }).click();
  await expect(page.getByText("AWAITING VERIFICATION", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Electric Command", exact: true }).click();
  await page.getByLabel("Operator", { exact: true }).fill("Command test");
  await page.getByLabel("Reason / repair evidence").fill("Synthetic restoration checked");
  await page.getByRole("button", { name: "Verify repair and restore" }).click();
  await expect(page.getByText("RESTORED", { exact: true })).toBeVisible();
  await expect(page.getByText("12 modeled queued vehicles", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Advance simulation by 1 minute" }).click();
  await expect(page.getByText("0 modeled queued vehicles", { exact: false })).toBeVisible();
  await page.reload();
  await expect(page.getByText("RESTORED", { exact: true })).toBeVisible();
  const snapshot = await (await fetch("http://127.0.0.1:8002/electric")).json();
  expect(snapshot.off_ids).toHaveLength(0);
  expect(snapshot.seconds).toBe(120);
  await expect.poll(async () => Number(await page.getByLabel("Synthetic electrical network map", { exact: true }).getAttribute("data-visible-assets")), { timeout: 30000 }).toBeGreaterThan(0);
  await page.screenshot({ path: "test-results/electric-command.png", fullPage: true });
  await page.getByLabel("Find asset by ID").fill("PT-001-1");
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(page.getByLabel("Synthetic electrical network map", { exact: true })).toHaveAttribute("data-visible-kinds", /POWER_TRANSFORMER/, { timeout: 30000 });
  await expect(page.getByLabel("Synthetic electrical network map", { exact: true })).toHaveAttribute("data-visible-kinds", /SUBSTATION/);
  await expect(page.getByLabel("Electrical asset symbols")).toBeVisible();
  await page.locator(".electric-panel").first().screenshot({ path: "test-results/electric-symbols.png" });
  await page.getByRole("button", { name: "City overview" }).click();
  await expect.poll(async () => Number(await page.getByLabel("Synthetic electrical network map", { exact: true }).getAttribute("data-visible-assets")), { timeout: 30000 }).toBe(20);
  await page.screenshot({ path: "test-results/electric-city-overview.png", fullPage: true });

});

test("load controls trip and reset protection; polygon rainfall changes connected systems", async ({ page }) => {
  await page.route("http://127.0.0.1:8001/electric**", async route => {
    const response = await route.fetch({ url: route.request().url().replace(":8001", ":8002") });
    await route.fulfill({ response });
  });
  await page.goto("/electric-command");
  await page.getByLabel("Find asset by ID").fill("DT-00001");
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  const controls = page.getByLabel("Asset load controls");
  await expect(controls).toContainText("DT-00001");
  await controls.getByRole("button", { name: "200% load", exact: true }).click();
  await expect(controls.getByText("OVERLOADED", { exact: true })).toBeVisible();
  await page.getByLabel("Simulation speed", { exact: true }).selectOption("5");
  await page.getByRole("button", { name: "Run simulation", exact: true }).click();
  await expect(controls.getByText("TRIPPED", { exact: true })).toBeVisible({ timeout: 20000 });
  await controls.getByRole("button", { name: "100% load", exact: true }).click();
  await controls.getByRole("button", { name: "Reset protection", exact: true }).click();
  await expect(controls.getByText("SUPPLIED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Pause simulation", exact: true }).click();
  await page.getByRole("button", { name: "Draw rainfall polygon", exact: true }).click();
  const map = page.getByLabel("Synthetic electrical network map", { exact: true });
  await map.scrollIntoViewIfNeeded();
  const box = (await map.boundingBox())!;
  for (const [dx,dy] of [[-100,-100],[100,-100],[100,100],[-100,100]]) await page.mouse.click(box.x+box.width/2+dx,box.y+box.height/2+dy);
  await page.getByRole("button", { name: "Apply rainfall to polygon", exact: true }).click();
  await expect(page.getByText("Electricity +12%", { exact: true })).toBeVisible();
  await expect(page.getByText("Road travel ×1.6", { exact: true })).toBeVisible();
  await expect(page.getByText("Metro demand index 136", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run simulation", exact: true }).click();
  await expect.poll(async () => {
    const state = await (await fetch("http://127.0.0.1:8002/electric")).json();
    return state.rain_effects[0]?.water_mm || 0;
  }, { timeout: 15000 }).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Pause simulation", exact: true }).click();
  await page.screenshot({ path: "test-results/realtime-rainfall.png", fullPage: true });
  await page.getByRole("button", { name: "Stop rain; allow drainage", exact: true }).click();
  await expect(page.getByLabel("Area 1 intensity", { exact: true })).toHaveValue("0");
});
