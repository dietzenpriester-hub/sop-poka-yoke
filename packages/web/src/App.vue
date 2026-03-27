<script setup lang="ts">
import { RouterView, useRouter } from "vue-router";
import { ref, onMounted, onUnmounted } from "vue";
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
} from "@element-plus/icons-vue";
import { alertApi } from "@/api/alert";

const router = useRouter();
const isCollapse = ref(false);
const unacknowledgedCount = ref(0);
let badgeTimer: ReturnType<typeof setInterval> | null = null;

const menuItems = [
  { path: "/", label: "实时监控", icon: Monitor },
  { path: "/sop", label: "SOP 配置", icon: Setting },
  { path: "/learning", label: "标准学习", icon: Reading },
  { path: "/stations", label: "工位管理", icon: Platform },
  { path: "/workorders", label: "工单管理", icon: List },
  { path: "/material-check", label: "物料校验", icon: Box },
  { path: "/completion-check", label: "完工检验", icon: CircleCheck },
  { path: "/alerts", label: "报警管理", icon: Bell },
  { path: "/replay", label: "视频回放", icon: VideoPlay },
  { path: "/report", label: "统计报表", icon: DataAnalysis },
  { path: "/override-log", label: "放行审计", icon: Stamp },
  { path: "/users", label: "用户管理", icon: User },
  { path: "/lifecycle", label: "数据管理", icon: Delete },
];

async function refreshBadge() {
  try {
    const { data } = await alertApi.unacknowledgedCount();
    unacknowledgedCount.value = data.count;
  } catch {
    /* ignore when not logged in */
  }
}

function handleLogout() {
  sessionStorage.removeItem("sop_token");
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
  <el-container style="height: 100vh">
    <el-aside :width="isCollapse ? '64px' : '200px'" style="transition: width 0.3s">
      <div style="padding: 16px; text-align: center; font-weight: bold; font-size: 16px; color: #409eff">
        <span v-if="!isCollapse">SOP 防呆系统</span>
        <span v-else>SOP</span>
      </div>
      <el-menu
        router
        :collapse="isCollapse"
        :default-active="$route.path"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#409eff"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #eee">
        <el-button text @click="isCollapse = !isCollapse">
          <el-icon :size="18"><component :is="isCollapse ? Expand : Fold" /></el-icon>
        </el-button>
        <div style="display: flex; align-items: center; gap: 16px">
          <el-badge :value="unacknowledgedCount" :hidden="unacknowledgedCount === 0" type="danger">
            <el-button text @click="router.push('/alerts')">
              <el-icon :size="20"><Bell /></el-icon>
            </el-button>
          </el-badge>
          <span style="color: #999; font-size: 14px">SOP 防呆系统 v2.0</span>
          <el-button text type="danger" size="small" @click="handleLogout">退出</el-button>
        </div>
      </el-header>

      <el-main>
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
body {
  margin: 0;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.el-aside {
  background-color: #001529;
  overflow: hidden;
}
</style>
