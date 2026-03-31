<script setup lang="ts">
import { RouterView, useRouter, useRoute } from "vue-router";
import { ref, computed, onMounted, onUnmounted } from "vue";
import {
  Monitor,
  Setting,
  VideoPlay,
  DataAnalysis,
  User,
  Platform,
  Reading,
  Bell,
  List,
  Box,
  CircleCheck,
  Stamp,
  Expand,
  Fold,
  Delete,
  SwitchButton,
  Aim,
} from "@element-plus/icons-vue";
import { alertApi } from "@/api/alert";
import { useAuthStore } from "@/stores/auth";
import { getJwtRole } from "@/utils/jwt";
import { STORAGE_TOKEN_KEY } from "@/utils/constants";

const router = useRouter();
const route = useRoute();
const isCollapse = ref(false);
const unacknowledgedCount = ref(0);
let badgeTimer: ReturnType<typeof setInterval> | null = null;

type MenuItem = {
  path: string;
  label: string;
  icon: typeof Monitor;
  meta?: { requiresAdmin?: boolean };
};

const allMenuItems: MenuItem[] = [
  { path: "/", label: "实时监控", icon: Monitor },
  { path: "/live", label: "作业检测", icon: Aim },
  { path: "/sop", label: "SOP 配置", icon: Setting },
  { path: "/learning", label: "标准学习", icon: Reading },
  { path: "/stations", label: "工位管理", icon: Platform },
  { path: "/workorders", label: "工单管理", icon: List },
  { path: "/material-check", label: "物料校验", icon: Box },
  { path: "/completion-check", label: "完工检验", icon: CircleCheck },
  { path: "/alerts", label: "报警管理", icon: Bell },
  { path: "/replay", label: "视频回放", icon: VideoPlay },
  { path: "/report", label: "统计报表", icon: DataAnalysis },
  { path: "/override-log", label: "放行审计", icon: Stamp, meta: { requiresAdmin: true } },
  { path: "/users", label: "用户管理", icon: User, meta: { requiresAdmin: true } },
  { path: "/lifecycle", label: "数据管理", icon: Delete, meta: { requiresAdmin: true } },
  { path: "/notification", label: "通知配置", icon: Bell, meta: { requiresAdmin: true } },
  { path: "/audit", label: "审计日志", icon: List, meta: { requiresAdmin: true } },
];

function jwtRole(): string | null {
  const token = sessionStorage.getItem(STORAGE_TOKEN_KEY);
  if (!token) return null;
  return getJwtRole(token);
}

const isLoginPage = computed(() => route.path === "/login");

const isAdmin = computed(() => {
  void route.fullPath;
  return jwtRole() === "admin";
});

const menuItems = computed(() =>
  allMenuItems.filter((item) => !item.meta?.requiresAdmin || isAdmin.value)
);

const currentPageTitle = computed(() => {
  const found = allMenuItems.find((m) => m.path === route.path);
  return found?.label || "";
});

const auth = useAuthStore();

async function refreshBadge() {
  if (!sessionStorage.getItem(STORAGE_TOKEN_KEY)) return;
  try {
    const { data } = await alertApi.unacknowledgedCount();
    unacknowledgedCount.value = data.count;
  } catch {
    /* ignore when not logged in */
  }
}

function handleLogout() {
  auth.logout();
  router.push("/login");
}

onMounted(() => {
  refreshBadge();
  badgeTimer = setInterval(refreshBadge, 10000);
});

onUnmounted(() => {
  if (badgeTimer) clearInterval(badgeTimer);
});
</script>

<template>
  <template v-if="isLoginPage">
    <RouterView />
  </template>

  <el-container v-else class="app-layout">
    <el-aside :width="isCollapse ? '64px' : '220px'" class="app-sidebar">
      <div class="sidebar-brand">
        <span class="sidebar-tc-logo">
          <span class="tc-thunder">T</span><span class="tc-comm">c</span>
        </span>
        <transition name="brand-fade">
          <span v-if="!isCollapse" class="sidebar-brand-text">SOP 防呆</span>
        </transition>
      </div>

      <el-scrollbar class="sidebar-scroll">
        <el-menu
          router
          :collapse="isCollapse"
          :default-active="$route.path"
          background-color="transparent"
          text-color="rgba(255,255,255,0.65)"
          active-text-color="#ffffff"
          :collapse-transition="false"
          class="sidebar-menu"
        >
          <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.label }}</template>
          </el-menu-item>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container class="app-main-container">
      <el-header class="app-header">
        <div class="header-left">
          <el-button text class="collapse-btn" @click="isCollapse = !isCollapse">
            <el-icon :size="18"><component :is="isCollapse ? Expand : Fold" /></el-icon>
          </el-button>
          <span class="header-page-title">{{ currentPageTitle }}</span>
        </div>

        <div class="header-right">
          <el-badge :value="unacknowledgedCount" :hidden="unacknowledgedCount === 0" type="danger">
            <el-button text class="header-icon-btn" @click="router.push('/alerts')">
              <el-icon :size="18"><Bell /></el-icon>
            </el-button>
          </el-badge>
          <el-tag
            size="small"
            :type="isAdmin ? 'warning' : 'info'"
            effect="plain"
            round
            class="header-role-tag"
          >
            {{ isAdmin ? "管理员" : "操作员" }}
          </el-tag>
          <el-button text type="danger" class="header-logout-btn" @click="handleLogout">
            <el-icon :size="16" style="margin-right: 4px"><SwitchButton /></el-icon>
            退出
          </el-button>
        </div>
      </el-header>

      <el-main class="app-content">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
body {
  margin: 0;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
}

.app-layout {
  height: 100vh;
}

.app-sidebar {
  background: linear-gradient(180deg, #001529 0%, #001d3d 100%);
  overflow: hidden;
  transition: width var(--sop-transition);
  border-right: 1px solid rgba(255, 255, 255, 0.04);
}

.sidebar-brand {
  height: var(--sop-header-h);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-tc-logo {
  flex-shrink: 0;
  font-size: 22px;
  line-height: 1;
}

.tc-thunder {
  font-weight: 700;
  font-style: italic;
  color: #e31b23;
}

.tc-comm {
  font-weight: 400;
  color: #e31b23;
}

.sidebar-brand-text {
  font-size: 16px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 2px;
  white-space: nowrap;
}

.brand-fade-enter-active,
.brand-fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.brand-fade-enter-from,
.brand-fade-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

.sidebar-scroll {
  height: calc(100vh - var(--sop-header-h));
}

.sidebar-menu {
  border-right: none !important;
  padding: 8px;
}

.sidebar-menu .el-menu-item {
  border-radius: 8px;
  margin-bottom: 2px;
  height: 44px;
  line-height: 44px;
  font-size: 14px;
  transition: all 0.2s;
}

.sidebar-menu .el-menu-item:hover {
  background: rgba(255, 255, 255, 0.06) !important;
}

.sidebar-menu .el-menu-item.is-active {
  background: rgba(64, 158, 255, 0.15) !important;
  color: #409eff !important;
  font-weight: 600;
}

.sidebar-menu .el-menu-item.is-active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: #409eff;
}

.app-header {
  height: var(--sop-header-h) !important;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px !important;
  background: #ffffff;
  border-bottom: 1px solid #f0f0f0;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.collapse-btn {
  color: #606266 !important;
  padding: 6px !important;
  border-radius: 6px !important;
}

.collapse-btn:hover {
  background: #f5f5f5 !important;
}

.header-page-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon-btn {
  color: #606266 !important;
  padding: 6px !important;
  border-radius: 6px !important;
}

.header-icon-btn:hover {
  background: #f5f5f5 !important;
}

.header-role-tag {
  font-size: 12px !important;
}

.header-logout-btn {
  font-size: 13px !important;
}

.app-content {
  background: var(--sop-bg);
  padding: 20px !important;
  overflow-y: auto;
}

.app-content::-webkit-scrollbar {
  width: 6px;
}

.app-content::-webkit-scrollbar-thumb {
  background: #d4d4d4;
  border-radius: 3px;
}

.app-content::-webkit-scrollbar-thumb:hover {
  background: #b0b0b0;
}

@media (max-width: 768px) {
  .header-role-tag,
  .header-page-title {
    display: none;
  }
}
</style>
