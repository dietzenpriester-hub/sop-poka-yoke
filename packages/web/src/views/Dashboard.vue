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

const { chartRef: trendChartRef, setOption: setTrendOption, resize: resizeTrend } = useECharts();

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
    tooltip: { trigger: "axis" },
    legend: { data: ["OK", "NG"], top: 12, right: 20, textStyle: { fontSize: 12 } },
    grid: { left: 48, right: 20, bottom: 32, top: 48 },
    xAxis: { type: "category", boundaryGap: false, data: trend.hours, axisLine: { lineStyle: { color: "#e5e6eb" } }, axisLabel: { color: "#86909c", fontSize: 11 } },
    yAxis: { type: "value", name: "次数", nameTextStyle: { color: "#86909c" }, splitLine: { lineStyle: { type: "dashed", color: "#f0f0f0" } }, axisLabel: { color: "#86909c" } },
    series: [
      {
        name: "OK",
        type: "line",
        smooth: true,
        showSymbol: false,
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(103,194,58,0.25)" }, { offset: 1, color: "rgba(103,194,58,0.02)" }] } },
        lineStyle: { width: 2.5 },
        color: "#67c23a",
        data: trend.ok,
      },
      {
        name: "NG",
        type: "line",
        smooth: true,
        showSymbol: false,
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(245,108,108,0.25)" }, { offset: 1, color: "rgba(245,108,108,0.02)" }] } },
        lineStyle: { width: 2.5 },
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

    if (ovRes.status === "fulfilled") overview.value = ovRes.value.data;
    if (stRes.status === "fulfilled") {
      stationStatus.value = stRes.value.data;
    }
    if (alRes.status === "fulfilled") recentAlerts.value = alRes.value.data;
    if (trRes.status === "fulfilled") applyTrendChart(trRes.value.data);

    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) ElMessage.warning(`部分仪表盘数据加载失败（${failed}/4）`);
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

interface StatItem {
  icon: typeof Odometer;
  label: string;
  key: keyof DashboardOverview;
  color: string;
  bg: string;
  suffix?: string;
}

const statItems: StatItem[] = [
  { icon: Odometer, label: "活跃工单", key: "active_orders", color: "#409eff", bg: "rgba(64,158,255,0.08)" },
  { icon: SuccessFilled, label: "今日 OK", key: "today_ok", color: "#67c23a", bg: "rgba(103,194,58,0.08)" },
  { icon: CircleClose, label: "今日 NG", key: "today_ng", color: "#f56c6c", bg: "rgba(245,108,108,0.08)" },
  { icon: TrendCharts, label: "合格率", key: "ok_rate", color: "#e6a23c", bg: "rgba(230,162,60,0.08)", suffix: "%" },
  { icon: WarningFilled, label: "未确认报警", key: "unacknowledged_alerts", color: "#f56c6c", bg: "rgba(245,108,108,0.08)" },
  { icon: Bell, label: "今日报警", key: "today_alerts", color: "#e6a23c", bg: "rgba(230,162,60,0.08)" },
];
</script>

<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>实时监控仪表盘</h2>
      <div class="page-header-actions">
        <el-text type="info" size="small">每 15 秒自动刷新</el-text>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col v-for="s in statItems" :key="s.key" :xs="12" :sm="8" :md="4">
        <div class="dash-stat-card" :style="{ '--card-accent': s.color, '--card-bg': s.bg }">
          <div class="dash-stat-icon">
            <el-icon :size="22" :color="s.color"><component :is="s.icon" /></el-icon>
          </div>
          <div class="dash-stat-info">
            <span class="dash-stat-label">{{ s.label }}</span>
            <span class="dash-stat-value" :style="{ color: s.color }">
              {{ overview != null ? (overview[s.key] ?? "—") : "—" }}{{ s.suffix || "" }}
            </span>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :lg="16">
        <el-card class="section-card">
          <template #header>
            <span style="font-weight: 600; font-size: 14px">今日 OK / NG 趋势</span>
          </template>
          <div ref="trendChartRef" style="width: 100%; height: 340px" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card class="section-card">
          <template #header>
            <span style="font-weight: 600; font-size: 14px">最近报警</span>
            <el-tag size="small" type="info" style="margin-left: 8px">10 条</el-tag>
          </template>
          <el-scrollbar max-height="340px">
            <el-empty v-if="recentAlerts.length === 0" description="暂无报警" :image-size="80" />
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

    <div style="margin-top: 20px">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px">
        <h3 style="margin: 0; font-size: 15px; font-weight: 600">工位状态</h3>
        <el-tag size="small" type="info">{{ stationStatus.length }} 个</el-tag>
      </div>
      <el-row :gutter="16">
        <el-col v-for="s in stationStatus" :key="s.id" :xs="24" :sm="12" :md="8" :lg="6">
          <div class="station-card">
            <div class="station-card-top">
              <div>
                <div class="station-name">{{ s.name }}</div>
                <div class="station-line">产线：{{ s.line_id || "—" }}</div>
              </div>
              <el-tag :type="s.status === 'busy' ? 'warning' : 'success'" size="small" effect="dark" round>
                {{ s.status === "busy" ? "忙碌" : "空闲" }}
              </el-tag>
            </div>
            <div class="station-card-bottom">
              活跃工单：<strong>{{ s.active_orders }}</strong>
            </div>
          </div>
        </el-col>
      </el-row>
      <el-empty v-if="!loading && stationStatus.length === 0" description="暂无工位数据" :image-size="80" />
    </div>
  </div>
</template>

<style scoped>
.dash-stat-card {
  background: var(--card-bg);
  border-radius: var(--sop-radius-lg);
  padding: 18px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
  transition: transform var(--sop-transition), box-shadow var(--sop-transition);
  cursor: default;
}

.dash-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.dash-stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.dash-stat-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.dash-stat-label {
  font-size: 12px;
  color: #86909c;
  white-space: nowrap;
}

.dash-stat-value {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.5px;
  line-height: 1.1;
}

.station-card {
  background: #fff;
  border-radius: var(--sop-radius-lg);
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: var(--sop-shadow-sm);
  transition: transform var(--sop-transition), box-shadow var(--sop-transition);
}

.station-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--sop-shadow-md);
}

.station-card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.station-name {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.station-line {
  font-size: 12px;
  color: #86909c;
  margin-top: 2px;
}

.station-card-bottom {
  margin-top: 12px;
  font-size: 14px;
  color: #4e5969;
  padding-top: 10px;
  border-top: 1px solid #f2f3f5;
}
</style>
