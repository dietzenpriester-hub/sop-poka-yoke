import { Page } from "@playwright/test";

export async function login(page: Page, username = "admin", password = "admin123") {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");

  await page.locator(".el-input input").first().fill(username);
  await page.locator(".el-input input").nth(1).fill(password);

  await page.locator("button.login-btn").click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 10_000 });
}
