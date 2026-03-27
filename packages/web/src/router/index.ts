import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", name: "dashboard", component: () => import("@/views/Dashboard.vue") },
    { path: "/sop", name: "sop", component: () => import("@/views/SOPConfig.vue") },
    { path: "/learning", name: "learning", component: () => import("@/views/SOPLearning.vue") },
    { path: "/replay", name: "replay", component: () => import("@/views/Replay.vue") },
    { path: "/report", name: "report", component: () => import("@/views/Report.vue") },
    { path: "/stations", name: "stations", component: () => import("@/views/StationMonitor.vue") },
    { path: "/users", name: "users", component: () => import("@/views/UserManage.vue") },
  ],
});

export default router;
