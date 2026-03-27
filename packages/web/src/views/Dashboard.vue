<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useStationWebSocket } from "@/composables/useWebSocket";

const stationId = ref("ST-01");

const { ready } = useStationWebSocket(stationId.value, (data) => {
  console.log("实时数据:", data);
});

const stats = ref({
  activeOrders: 0,
  todayOk: 0,
  todayNg: 0,
  okRate: "0%",
});

onMounted(() => {
  stats.value = {
    activeOrders: 3,
    todayOk: 482,
    todayNg: 18,
    okRate: "96.4%",
  };
});
</script>

<template>
  <div>
    <h2>实时监控仪表盘</h2>
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>活跃工单</template>
          <div style="font-size: 32px; font-weight: bold; color: #409eff">{{ stats.activeOrders }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>今日 OK</template>
          <div style="font-size: 32px; font-weight: bold; color: #67c23a">{{ stats.todayOk }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>今日 NG</template>
          <div style="font-size: 32px; font-weight: bold; color: #f56c6c">{{ stats.todayNg }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>合格率</template>
          <div style="font-size: 32px; font-weight: bold; color: #e6a23c">{{ stats.okRate }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 20px">
      <template #header>
        <span>系统状态</span>
        <el-tag :type="ready ? 'success' : 'danger'" style="margin-left: 12px">
          {{ ready ? "在线" : "离线" }}
        </el-tag>
      </template>
      <p>WebSocket 连接状态：{{ ready ? "已连接" : "断开" }}</p>
      <p>当前监控工位：{{ stationId }}</p>
    </el-card>
  </div>
</template>
