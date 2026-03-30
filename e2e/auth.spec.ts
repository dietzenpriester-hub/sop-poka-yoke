import { test, expect } from "@playwright/test";

test.describe("登录流程", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
  });

  test("页面包含登录表单", async ({ page }) => {
    await expect(page.locator(".el-input input").first()).toBeVisible();
    await expect(page.locator(".el-input input").nth(1)).toBeVisible();
    await expect(page.locator("button.login-btn")).toBeVisible();
  });

  test("正确凭据可以登录", async ({ page }) => {
    await page.locator(".el-input input").first().fill("admin");
    await page.locator(".el-input input").nth(1).fill("admin123");
    await page.locator("button.login-btn").click();

    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 10_000 });
    expect(page.url()).not.toContain("/login");
  });

  test("错误凭据显示提示", async ({ page }) => {
    await page.locator(".el-input input").first().fill("admin");
    await page.locator(".el-input input").nth(1).fill("wrongpassword");
    await page.locator("button.login-btn").click();

    const msg = page.locator(".el-message").first();
    await expect(msg).toBeVisible({ timeout: 5_000 });
  });

  test("未登录访问受保护页面跳转登录", async ({ page }) => {
    await page.context().clearCookies();
    await page.evaluate(() => sessionStorage.clear());
    await page.goto("/dashboard");
    await page.waitForURL((url) => url.pathname.includes("/login"), { timeout: 5_000 });
    expect(page.url()).toContain("/login");
  });
});
