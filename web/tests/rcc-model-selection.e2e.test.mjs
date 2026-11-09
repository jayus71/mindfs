import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer } from "vite";

test("RCC aliases and runtime default are selectable before any session", async () => {
  const server = await createServer({ root: fileURLToPath(new URL("../", import.meta.url)), server: { host: "127.0.0.1", port: 0 } });
  let browser;
  try {
    await server.listen();
    browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
    const page = await browser.newPage({ locale: "zh-CN" });
    let sessions = 0;
    await page.route("**/api/**", async (route) => {
      if (route.request().url().includes("/api/agents")) {
        return route.fulfill({ json: [{ name: "rcc", protocol: "rcc", installed: true, available: true,
          models: ["sonnet", "opus", "fable"].map(id => ({ id, name: `${id}（运行端别名）`, description: "由运行端官方 Claude Code 解析" })) }] });
      }
      if (route.request().url().includes("session")) sessions++;
      return route.fulfill({ json: {} });
    });
    await page.goto(`${server.resolvedUrls.local[0]}tests/model-pins.html`);
    const trigger = page.locator("main button").first();
    for (const alias of ["sonnet", "opus", "fable"]) {
      await trigger.click();
      await page.getByRole("button", { name: "展开 rcc 模型列表", exact: true }).click();
      await page.getByRole("button", { name: `${alias}（运行端别名） 由运行端官方 Claude Code 解析`, exact: true }).click();
      assert.equal(await page.getByTestId("selection").textContent(), `rcc:${alias}`);
    }
    await trigger.click();
    await page.getByRole("button", { name: "展开 rcc 模型列表", exact: true }).click();
    await page.getByRole("button").filter({ hasText: /^默认模型/ }).click();
    assert.equal(await page.getByTestId("selection").textContent(), "rcc:");
    assert.equal(sessions, 0, "opening model choices must not start a remote session");
  } finally {
    await browser?.close();
    await server.close();
  }
});
