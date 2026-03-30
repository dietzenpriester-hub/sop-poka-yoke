import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PAGES = [
  { path: "/dashboard", title: "仪表盘" },
  { path: "/workorder", title: "工单" },
  { path: "/station-monitor", title: "工位监控" },
  { path: "/alert", title: "报警" },
  { path: "/sop-config", title: "SOP配置" },
  { path: "/sop-learning", title: "SOP学习" },
  { path: "/material-check", title: "物料校验" },
  { path: "/completion-check", title: "完工检查" },
  { path: "/override-log", title: "放行记录" },
  { path: "/report", title: "报告" },
  { path: "/replay", title: "操作回放" },
  { path: "/data-lifecycle", title: "数据生命周期" },
  { path: "/user-manage", title: "用户管理" },
];

test.describe("页面导航", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  for (const { path, title } of PAGES) {
    test(`${title} 页面 (${path}) 可正常加载`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      expect(page.url()).toContain(path);
      const body = await page.textContent("body");
      expect(body).not.toContain("Internal Server Error");
    });
  }

  test("连续切换 6 个页面无 JS 错误", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    for (const { path } of PAGES.slice(0, 6)) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(300);
    }

    expect(errors).toHaveLength(0);
  });
});
