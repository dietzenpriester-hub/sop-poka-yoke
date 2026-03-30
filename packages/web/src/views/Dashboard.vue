<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from "vue";
import { ElMessage } from "element-plus";
import {
  Odometer,
  SuccessFilled,
  CircleClose,
  TrendCharts,
  Bell,
  WarningFilled,
} from "@element-plus/icons-vue";
import { useECharts } from "@/composables/useECharts";
import { useStationWebSocket } from "@/composables/useWebSocket";
import {
  dashboardApi,
  type DashboardOverview,
  type HourlyTrend,
  type RecentAlert,
  type StationStatusItem,
} from "@/api/dashboard";
import { severityTagType } from "@/utils/severity";

const overview = ref<DashboardOverview | null>(null);
const stationStatus = ref<StationStatusItem[]>([]);
const recentAlerts = ref<RecentAlert[]>([]);
const loading = ref(false);

/** 用于 WebSocket：取首个工位 ID，避免硬编码 */
const wsStationId = ref("");

const { chartRef: trendChartRef, setOption: setTrendOption, resize: resizeTrend } = useECharts();

const { ready: wsReady } = useStationWebSocket(wsStationId, () => {
  /* 实时推送由其它页面消费；此处仅展示连接状态 */
});

let refreshTimer: ReturnType<typeof setInterval> | null = null;
let requestSeq = 0;

function formatAlertTime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN");
  } catch {
    return iso;
  }
}

function applyTrendChart(trend: HourlyTrend) {
  setTrendOption({
    title: { text: "今日逐小时 OK / NG 趋势", left: "center" },
    tooltip: { trigger: "axis" },
    legend: { data: ["OK", "NG"], bottom: 0 },
    grid: { left: 50, right: 24, bottom: 48, top: 48 },
    xAxis: { type: "category", boundaryGap: false, data: trend.hours },
    yAxis: { type: "value", name: "次数" },
    series: [
      {
        name: "OK",
        type: "line",
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.25 },
        lineStyle: { width: 2 },
        color: "#67c23a",
        data: trend.ok,
      },
      {
        name: "NG",
        type: "line",
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.25 },
        lineStyle: { width: 2 },
        color: "#f56c6c",
        data: trend.ng,
      },
    ],
  });
  nextTick(() => resizeTrend());
}

async function loadDashboard() {
  const seq = ++requestSeq;
  loading.value = true;
  try {
    const results = await Promise.allSettled([
      dashboardApi.overview(),
      dashboardApi.stationStatus(),
      dashboardApi.recentAlerts(),
      dashboardApi.hourlyTrend(),
    ]);
    if (seq !== requestSeq) return;

    const [ovRes, stRes, alRes, trRes] = results;

    if (ovRes.status === "fulfilled") {
      overview.value = ovRes.value.data;
    }
    if (stRes.status === "fulfilled") {
      stationStatus.value = stRes.value.data;
      if (!wsStationId.value && stRes.value.data.length > 0) {
        wsStationId.value = String(stRes.value.data[0].id);
      }
    }
    if (alRes.status === "fulfilled") {
      recentAlerts.value = alRes.value.data;
    }
    if (trRes.status === "fulfilled") {
      applyTrendChart(trRes.value.data);
    }

    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      ElMessage.warning(`部分仪表盘数据加载失败（${failed}/4）`);
    }
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

onMounted(() => {
  loadDashboard();
  refreshTimer = setInterval(loadDashboard, 15_000);
});

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<template>
  <div v-loading="loading">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px">
      <h2 style="margin: 0">实时监控仪表盘</h2>
      <el-text type="info" size="small">每 15 秒自动刷新</el-text>
    </div>

    <!-- 6 张概览卡片 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card shadow="hover">
          <template #header>
            <span style="display: inline-flex; align-items: center; gap: 6px">
              <el-icon><Odometer /></el-icon>
              活跃工单
            </span>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #409eff">
            {{ overview?.active_orders ?? "—" }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card shadow="hover">
          <template #header>
            <span style="display: inline-flex; align-items: center; gap: 6px">
              <el-icon><SuccessFilled /></el-icon>
              今日 OK
            </span>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #67c23a">
            {{ overview?.today_ok ?? "—" }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card shadow="hover">
          <template #header>
            <span style="display: inline-flex; align-items: center; gap: 6px">
              <el-icon><CircleClose /></el-icon>
              今日 NG
            </span>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #f56c6c">
            {{ overview?.today_ng ?? "—" }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card shadow="hover">
          <template #header>
            <span style="display: inline-flex; align-items: center; gap: 6px">
              <el-icon><TrendCharts /></el-icon>
              合格率
            </span>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #e6a23c">
            {{ overview != null ? `${overview.ok_rate}%` : "—" }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card shadow="hover">
          <template #header>
            <span style="display: inline-flex; align-items: center; gap: 6px">
              <el-icon><WarningFilled /></el-icon>
              未确认报警
            </span>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #f56c6c">
            {{ overview?.unacknowledged_alerts ?? "—" }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card shadow="hover">
          <template #header>
            <span style="display: inline-flex; align-items: center; gap: 6px">
              <el-icon><Bell /></el-icon>
              今日报警
            </span>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #e6a23c">
            {{ overview?.today_alerts ?? "—" }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 + 最近报警 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never">
          <div ref="trendChartRef" style="width: 100%; height: 360px" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never">
          <template #header>最近报警（10 条）</template>
          <el-scrollbar max-height="360px">
            <el-empty v-if="recentAlerts.length === 0" description="暂无报警" />
            <el-timeline v-else>
              <el-timeline-item
                v-for="a in recentAlerts"
                :key="a.id"
                :timestamp="formatAlertTime(a.created_at)"
                placement="top"
              >
                <div style="margin-bottom: 4px">
                  <el-tag size="small" :type="severityTagType(a.severity)">{{ a.severity }}</el-tag>
                  <el-tag size="small" type="info" style="margin-left: 6px">{{ a.alert_type }}</el-tag>
                  <el-tag
                    v-if="a.acknowledged === '0'"
                    size="small"
                    type="warning"
                    style="margin-left: 6px"
                  >
                    未确认
                  </el-tag>
                  <el-tag v-else size="small" type="success" style="margin-left: 6px">已确认</el-tag>
                </div>
                <div style="font-size: 13px; color: #606266">{{ a.message || "—" }}</div>
                <div style="font-size: 12px; color: #909399; margin-top: 4px">
                  工位：{{ a.station_code || "—" }}
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-scrollbar>
        </el-card>
      </el-col>
    </el-row>

    <!-- WebSocket 状态 -->
    <el-card style="margin-top: 16px">
      <template #header>
        <span>实时连接</span>
        <el-tag :type="wsReady ? 'success' : 'danger'" style="margin-left: 12px">
          {{ wsReady ? "在线" : "离线" }}
        </el-tag>
      </template>
      <p style="margin: 0 0 8px">
        WebSocket：{{ wsReady ? "已连接" : "未连接" }}
        <span v-if="wsStationId">（工位 ID：{{ wsStationId }}）</span>
        <span v-else>（暂无工位，请先配置工位）</span>
      </p>
    </el-card>

    <!-- 工位状态 -->
    <h3 style="margin: 24px 0 12px">工位状态</h3>
    <el-row :gutter="16">
      <el-col v-for="s in stationStatus" :key="s.id" :xs="24" :sm="12" :md="8" :lg="6">
        <el-card shadow="hover" style="margin-bottom: 16px">
          <div style="display: flex; justify-content: space-between; align-items: flex-start">
            <div>
              <div style="font-size: 16px; font-weight: 600">{{ s.name }}</div>
              <el-text size="small" type="info">产线：{{ s.line_id || "—" }}</el-text>
            </div>
            <el-tag :type="s.status === 'busy' ? 'warning' : 'success'" size="small">
              {{ s.status === "busy" ? "忙碌" : "空闲" }}
            </el-tag>
          </div>
          <div style="margin-top: 12px; font-size: 14px">
            活跃工单：<strong>{{ s.active_orders }}</strong>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-if="!loading && stationStatus.length === 0" description="暂无工位数据" />
  </div>
</template>
