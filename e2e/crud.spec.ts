import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("CRUD 操作", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("工单列表页面加载成功", async ({ page }) => {
    await page.goto("/workorder");
    await page.waitForLoadState("networkidle");
    const body = await page.textContent("body");
    expect(body).not.toContain("Internal Server Error");
    expect(page.url()).toContain("/workorder");
  });

  test("报警列表页面加载成功", async ({ page }) => {
    await page.goto("/alert");
    await page.waitForLoadState("networkidle");
    const body = await page.textContent("body");
    expect(body).not.toContain("Internal Server Error");
    expect(page.url()).toContain("/alert");
  });

  test("用户管理页面加载成功", async ({ page }) => {
    await page.goto("/user-manage");
    await page.waitForLoadState("networkidle");
    const body = await page.textContent("body");
    expect(body).not.toContain("Internal Server Error");
    expect(page.url()).toContain("/user-manage");
  });

  test("仪表盘页面加载无错误", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);

    expect(errors).toHaveLength(0);
    expect(page.url()).toContain("/dashboard");
  });

  test("SOP 配置页面可访问", async ({ page }) => {
    await page.goto("/sop-config");
    await page.waitForLoadState("networkidle");
    const body = await page.textContent("body");
    expect(body).not.toContain("Internal Server Error");
  });

  test("API 登录端点可访问", async ({ request }) => {
    const resp = await request.post("http://127.0.0.1:8000/api/auth/login", {
      data: { username: "admin", password: "admin123" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("access_token");
  });

  test("API 通过 Nginx 代理可访问", async ({ request }) => {
    const resp = await request.post("http://127.0.0.1:8080/api/auth/login", {
      data: { username: "admin", password: "admin123" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("access_token");
  });
});
