import { expect, test } from "@playwright/test";

test("home keeps one primary action and one compact savings summary", async ({ page }) => {
  await page.goto("/?demo=1");
  await expect(page.getByRole("button", { name: "Prepare a message", exact: true })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Estimated tokens avoided" })).toBeVisible();
  await expect(page.getByText("Provider usage captured")).toBeVisible();
  await expect(page.getByText("Common tasks")).toHaveCount(0);
});

test("prepares an exact message, shows the result first, and recovers an omitted source", async ({ page }) => {
  const exactMessage = "Review src/context_loom/hydration/service.py.\n\nKeep  both spaces and max_input_tokens=4000.";
  await page.goto("/?demo=1");
  await expect(page.getByRole("heading", { name: "Context Loom", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Prepare" }).first().click();
  await expect(page.getByRole("heading", { name: "Prepare message" })).toBeVisible();
  await page.getByRole("textbox", { name: "What do you want to do?" }).fill(exactMessage);
  await page.getByRole("button", { name: "Prepare request" }).click();

  await expect(page.getByTestId("hydration-inspector")).toBeVisible();
  await expect(page.locator("#prepared-request-result")).toBeFocused();
  await expect(page.getByRole("status").filter({ hasText: "Prepared request ready" })).toHaveText("Prepared request ready. Review it, then copy it when you are ready.");
  await expect(page.getByRole("heading", { name: "Prepared request" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy prepared request" })).toBeVisible();
  await expect(page.getByText("Nothing is sent automatically")).toBeVisible();
  await expect(page.getByText("Review full prepared request")).toBeVisible();
  await expect(page.getByText("Message and sources checked")).toBeVisible();
  await expect(page.getByText("Estimated input saved")).toBeVisible();

  await page.getByText("Message integrity and technical details").click();
  await expect(page.getByTestId("exact-message")).toHaveText(exactMessage);

  const evidence = page.locator(".evidence-item--selected").filter({ hasText: "src/context_loom/hydration/service.py" }).first();
  await evidence.locator("summary").first().click();
  await evidence.getByText("Ranking and source integrity").click();
  await expect(evidence.getByText("Source hash")).toBeVisible();
  await expect(evidence.getByText("max_input_tokens=4000")).toBeVisible();

  await page.getByRole("tab", { name: /Not included/ }).click();
  const omitted = page.locator(".evidence-item--omitted").filter({ hasText: "docs/architecture.md" });
  await omitted.getByRole("button", { name: "Open sanitized source" }).click();
  await expect(omitted.getByText("Context Loom keeps one canonical local runtime")).toBeVisible();
});

test("keeps confidence tiers distinct and accepts honest provider usage", async ({ page }) => {
  await page.goto("/threads?demo=1");
  await expect(page.getByRole("heading", { name: "Savings" })).toBeVisible();
  await expect(page.getByText("Expected savings").first()).toBeVisible();
  await expect(page.getByText("Actual input used").first()).toBeVisible();
  await expect(page.getByText("Measured savings").first()).toBeVisible();

  await page.getByRole("button", { name: /New harness thread/ }).click();
  await expect(page.getByText("Unknown").first()).toBeVisible();
  await page.getByRole("button", { name: "Add provider usage" }).click();
  await page.getByLabel("Provider").fill("OpenAI");
  await page.getByLabel("Model").fill("gpt-5");
  await page.getByLabel("Input tokens", { exact: true }).fill("1900");
  await page.getByRole("button", { name: "Save usage" }).click();
  await expect(page.getByText("1,900").first()).toBeVisible();
  await expect(page.getByText("Unknown").first()).toBeVisible();
});

test("adds, selects, and scans a second project from the interface", async ({ page }) => {
  await page.goto("/?demo=1");
  await page.getByRole("button", { name: "Add project" }).click();
  const projectDialog = page.getByRole("dialog");
  await expect(projectDialog).toBeVisible();
  await projectDialog.getByRole("textbox", { name: "Project folder", exact: true }).fill("/workspace/design-system");
  await page.getByRole("button", { name: "Add and scan project" }).click();
  await expect(page.getByText("Project ready")).toBeVisible();
  await expect(page.getByRole("dialog")).toBeHidden({ timeout: 3_000 });
  await expect(page.locator(".sidebar").getByRole("combobox", { name: "Current project" })).toHaveValue("ws-demo-design-system");

  await page.getByRole("link", { name: "Project files" }).click();
  await expect(page.getByRole("heading", { name: "Project files" })).toBeVisible();
  await expect(page.getByText("No files match this view")).toBeVisible();
});

test("keeps project file paths readable in the desktop table", async ({ page }) => {
  await page.goto("/resources?demo=1");
  const filePath = page.getByText("src/context_loom/hydration/service.py", { exact: true });
  await expect(filePath).toBeVisible();
  const bounds = await filePath.boundingBox();
  expect(bounds?.width ?? 0).toBeGreaterThan(180);
});

test("connections lead with truthful methods and theme radios support arrows", async ({ page }) => {
  await page.goto("/integrations?demo=1");
  await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Copy and paste" })).toBeVisible();
  await expect(page.getByText("Recommended")).toBeVisible();
  const mcp = page.locator(".connection-method").filter({ hasText: "MCP connection" });
  await mcp.getByText("View setup").click();
  await expect(mcp.getByText("context-loom adapter preview codex")).toBeVisible();
  const localApi = page.locator(".connection-method").filter({ hasText: "Local API" });
  await localApi.getByText("View endpoint").click();
  await expect(localApi.getByText("POST http://127.0.0.1:4173/api/v1/hydrations")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("adapter preview openai_responses");
  await page.getByText("Advanced output formats").click();
  await expect(page.getByText("Provider-shaped output only")).toBeVisible();

  await page.goto("/settings?demo=1");
  await expect(page.getByText("Not retained", { exact: true })).toBeVisible();
  const dark = page.getByRole("radio", { name: "Dark" });
  await dark.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await dark.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "System" })).toBeFocused();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme-preference", "system");
});

test("320px mobile navigation remains readable, complete, and free of horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/?demo=1");
  const navigation = page.getByRole("navigation", { name: "Mobile primary" });
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole("link")).toHaveCount(4);
  await navigation.getByText("Prepare", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "What do you want to do?" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "What do you want to do?" })).not.toBeFocused();
  const prepareButton = page.getByRole("button", { name: "Prepare request" });
  const prepareBounds = await prepareButton.boundingBox();
  expect((prepareBounds?.y ?? 9999) + (prepareBounds?.height ?? 0)).toBeLessThanOrEqual(568);
  await page.getByRole("button", { name: "Project and app controls" }).click();
  await expect(page.getByRole("combobox", { name: "Current project" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Scan Context Loom for changes/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add project" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connections" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Settings" })).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("textbox", { name: "What do you want to do?" }).fill("Review the mobile layout and preserve the exact message.");
  await page.getByRole("button", { name: "Prepare request" }).click();
  const preparedResult = page.locator("#prepared-request-result");
  await expect(preparedResult).toBeFocused();
  await expect(preparedResult).toBeInViewport();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const labels = await navigation.locator("span").allTextContents();
  expect(labels).toEqual(["Home", "Prepare", "Files", "Savings"]);
});
