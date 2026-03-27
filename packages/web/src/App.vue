<script setup lang="ts">
import { RouterView } from "vue-router";
import { ref } from "vue";
import {
  Monitor,
  Setting,
  VideoPlay,
  DataAnalysis,
  User,
  Platform,
  Reading,
} from "@element-plus/icons-vue";

const isCollapse = ref(false);

const menuItems = [
  { path: "/", label: "实时监控", icon: Monitor },
  { path: "/sop", label: "SOP 配置", icon: Setting },
  { path: "/learning", label: "标准学习", icon: Reading },
  { path: "/stations", label: "工位管理", icon: Platform },
  { path: "/replay", label: "视频回放", icon: VideoPlay },
  { path: "/report", label: "统计报表", icon: DataAnalysis },
  { path: "/users", label: "用户管理", icon: User },
];
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
        <el-button :icon="isCollapse ? 'Expand' : 'Fold'" text @click="isCollapse = !isCollapse" />
        <span style="color: #999; font-size: 14px">SOP 防呆系统 v2.0</span>
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
