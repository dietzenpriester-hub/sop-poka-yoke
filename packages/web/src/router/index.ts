import { createRouter, createWebHistory } from "vue-router";

function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return Date.now() / 1000 > payload.exp;
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/login", name: "login", component: () => import("@/views/Login.vue"), meta: { public: true } },
    { path: "/", name: "dashboard", component: () => import("@/views/Dashboard.vue") },
    { path: "/sop", name: "sop", component: () => import("@/views/SOPConfig.vue") },
    { path: "/learning", name: "learning", component: () => import("@/views/SOPLearning.vue") },
    { path: "/alerts", name: "alerts", component: () => import("@/views/AlertList.vue") },
    { path: "/replay", name: "replay", component: () => import("@/views/Replay.vue") },
    { path: "/report", name: "report", component: () => import("@/views/Report.vue") },
    { path: "/stations", name: "stations", component: () => import("@/views/StationMonitor.vue") },
    { path: "/workorders", name: "workorders", component: () => import("@/views/WorkOrder.vue") },
    { path: "/material-check", name: "material-check", component: () => import("@/views/MaterialCheck.vue") },
    { path: "/completion-check", name: "completion-check", component: () => import("@/views/CompletionCheck.vue") },
    { path: "/override-log", name: "override-log", component: () => import("@/views/OverrideLog.vue"), meta: { requiresAdmin: true } },
    { path: "/users", name: "users", component: () => import("@/views/UserManage.vue"), meta: { requiresAdmin: true } },
    { path: "/lifecycle", name: "lifecycle", component: () => import("@/views/DataLifecycle.vue"), meta: { requiresAdmin: true } },
  ],
});

router.beforeEach((to) => {
  const token = sessionStorage.getItem("sop_token");
  if (to.name === "login" && token && !isTokenExpired(token)) {
    return { name: "dashboard" };
  }
  if (!to.meta?.public && (!token || isTokenExpired(token))) {
    sessionStorage.removeItem("sop_token");
    return { name: "login" };
  }
  if (to.meta?.requiresAdmin && token) {
    const payload = parseJwtPayload(token);
    if (!payload || payload.role !== "admin") return { name: "dashboard" };
  }
});

export default router;
