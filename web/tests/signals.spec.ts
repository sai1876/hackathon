import { test, expect } from "@playwright/test";
test("database traffic signals have distinct markers, unknown phases and unresolved names", async ({ page }) => {
  await page.goto("/command");
  await expect(page.getByText("112 mapped OSM signal nodes", {exact:false})).toBeVisible({timeout:40000});
  await expect(page.locator(".traffic-signal-pin")).toHaveCount(112);
  await page.getByRole("button",{name:"Traffic signals · ON",exact:true}).click();
  await expect(page.locator(".traffic-signal-pin")).toHaveCount(0);
  await page.getByRole("button",{name:"Traffic signals · OFF",exact:true}).click();
  await expect(page.locator(".traffic-signal-pin")).toHaveCount(112);
  await page.getByText("60 named junctions awaiting coordinates",{exact:true}).click();
  await page.getByLabel("Find junction awaiting coordinates").fill("Cyber Towers");
  await expect(page.locator(".traffic-signals-control li")).toHaveCount(1);
  await expect(page.locator(".traffic-signals-control li")).toContainText("Cyber Towers");
  await page.getByText("60 named junctions awaiting coordinates",{exact:true}).click();
  const pins = page.locator(".traffic-signal-pin");
  let clicked = false;
  for (let i=0;i<await pins.count();i++) {
    try { await pins.nth(i).click({timeout:500}); clicked=true; break; } catch {}
  }
  expect(clicked).toBeTruthy();
  await expect(page.locator(".signal-popup")).toContainText("Signal phase: UNKNOWN");
  await page.screenshot({path:"test-results/command-signals.png",fullPage:true});
  await page.goto("/traffic");
  await expect(page.locator(".traffic-signal-pin")).toHaveCount(112,{timeout:40000});
  await page.getByRole("button",{name:"Traffic signals · ON",exact:true}).click();
  await expect(page.locator(".traffic-signal-pin")).toHaveCount(0);
});
