import { test, expect } from "@playwright/test";
test.use({ actionTimeout: 15000 });
test("main command reads database and department views have no scenario injection", async ({ page }) => {
  let roadRequests = 0;
  page.on("request", req => { if(req.url().includes("/command/roads?")) roadRequests++; });
  await page.goto("/command");
  await expect(page.getByRole("heading", { name: "AegisGrid Command Center", exact: true })).toBeVisible();
  await expect(page.getByText("374,988", {exact:true}).first()).toBeVisible({timeout:30000});
  expect(roadRequests).toBe(0);
  await expect(page.getByRole("button", {name:"Show road sample",exact:true})).toHaveCount(0);
  for (let i=0;i<4;i++) {
    await page.getByRole("button", {name:"Zoom in",exact:true}).click();
    await page.waitForTimeout(400);
  }
  await expect.poll(async()=>Number(await page.getByLabel("Database road map",{exact:true}).getAttribute("data-roads")), {timeout:60000}).toBeGreaterThan(0);
  await expect(page.locator(".main-map-status")).toContainText("grey = no traffic reading");
  expect(roadRequests).toBeGreaterThan(0);
  for (let i=0;i<4;i++) {
    await page.getByRole("button", {name:"Zoom out",exact:true}).click();
    await page.waitForTimeout(400);
  }
  await expect.poll(async()=>Number(await page.getByLabel("Database road map",{exact:true}).getAttribute("data-roads"))).toBe(0);
  const zoomedOutRequests = roadRequests;
  await page.getByRole("button", {name:"Zoom out",exact:true}).click();
  await page.waitForTimeout(400);
  expect(roadRequests).toBe(zoomedOutRequests);
  await expect(page.getByRole("button",{name:"Run scenario",exact:true})).toBeDisabled();
  await page.screenshot({path:"test-results/main-command.png",fullPage:true});
  await page.getByRole("link",{name:"Electric Command",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Electric Command",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Apply rainfall to polygon",exact:true})).toHaveCount(0);
  await expect(page.getByLabel("Demand multiplier",{exact:true})).toHaveCount(0);
  await expect(page.getByText("6,300",{exact:true})).toHaveCount(0);
  await page.getByRole("link",{name:"Traffic",exact:true}).click();
  await expect(page.getByRole("button",{name:"Inject backend event",exact:true})).toHaveCount(0);
});
