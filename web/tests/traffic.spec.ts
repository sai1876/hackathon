import { test, expect } from "@playwright/test";

test("coverage overlay is visible, toggleable, and available for presentation", async ({ page }) => {
  await page.goto("/traffic");
  const toggle = page.getByRole("button", { name: /^Coverage / });
  await expect(toggle).toBeEnabled({ timeout: 30000 });
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  const map = page.getByTestId("traffic-map");
  await expect(map).toHaveAttribute("data-coverage-features", /^[1-9]\d*$/, { timeout: 30000 });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect(map).toHaveAttribute("data-coverage-features", "0");
  await toggle.click();
  await page.getByRole("button", { name: "View all coverage" }).click();
  await expect(map).toHaveAttribute("data-coverage-features", /^[1-9]\d*$/);
  await expect(page.getByText("Approximate imported coverage")).toBeVisible();
  await expect(page.locator(".start-marker")).toHaveCount(0);
});

test("coverage download failure is explicit and leaves the map usable", async ({ page }) => {
  await page.route("**/data/road-coverage.geojson", route => route.fulfill({ status: 503, body: "Unavailable" }));
  await page.goto("/traffic");
  await expect(page.getByText("Coverage layer unavailable")).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("button", { name: /^Coverage / })).toBeDisabled();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
});

