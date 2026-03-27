<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { ElMessage } from "element-plus";
import { useECharts } from "@/composables/useECharts";
import { reportApi, type ReportSummary } from "@/api/report";

const days = ref(7);
const summary = ref<ReportSummary | null>(null);
const loading = ref(false);
let requestSeq = 0;

const { chartRef: trendChartRef, setOption: setTrendOption } = useECharts();
const { chartRef: alertChartRef, setOption: setAlertOption } = useECharts();
const { chartRef: stationChartRef, setOption: setStationOption } = useECharts();

async function loadData() {
  const seq = ++requestSeq;
  loading.value = true;
  try {
    const results = await Promise.allSettled([
      reportApi.summary(days.value),
      reportApi.dailyTrend(days.value),
      reportApi.alertDistribution(days.value),
      reportApi.stationComparison(days.value),
    ]);
    if (seq !== requestSeq) return;

    const [sumRes, trendRes, alertRes, stationRes] = results;

    if (sumRes.status === "fulfilled") {
      summary.value = sumRes.value.data;
    }

    if (trendRes.status === "fulfilled") {
      const td = trendRes.value.data;
      setTrendOption({
      title: { text: `步骤结果趋势（近 ${days.value} 天）`, left: "center" },
      tooltip: { trigger: "axis" },
      legend: { bottom: 0 },
      grid: { left: 60, right: 30, bottom: 40 },
      xAxis: { type: "category", data: td.dates },
      yAxis: { type: "value", name: "次数" },
      series: [
        { name: "OK", type: "bar", stack: "total", data: td.ok, color: "#67c23a" },
        { name: "NG", type: "bar", stack: "total", data: td.ng, color: "#f56c6c" },
        { name: "SKIP", type: "bar", stack: "total", data: td.skip, color: "#909399" },
        { name: "OVERRIDE", type: "bar", stack: "total", data: td.override, color: "#e6a23c" },
      ],
    });
    }

    if (alertRes.status === "fulfilled") {
      setAlertOption({
        title: { text: "报警类型分布", left: "center" },
        tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
        legend: { bottom: 0 },
        series: [{
          type: "pie",
          radius: ["40%", "70%"],
          data: alertRes.value.data.items,
          emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: "rgba(0,0,0,0.5)" } },
        }],
      });
    }

    if (stationRes.status === "fulfilled") {
      const sd = stationRes.value.data;
      setStationOption({
        title: { text: "工位报警对比", left: "center" },
        tooltip: { trigger: "axis" },
        grid: { left: 80, right: 30, bottom: 40 },
        xAxis: { type: "category", data: sd.stations, axisLabel: { rotate: 30 } },
        yAxis: { type: "value", name: "报警数" },
        series: [
          { name: "报警数", type: "bar", data: sd.alert_counts, color: "#f56c6c" },
        ],
      });
    }

    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) ElMessage.warning(`${failed} 个报表接口加载失败`);
  } finally {
    loading.value = false;
  }
}

onMounted(() => loadData());
watch(days, () => loadData());
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>统计报表</h2>
      <div>
        <el-radio-group v-model="days" size="small">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="14">近 14 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 概览卡片 -->
    <el-row :gutter="16" style="margin-top: 16px" v-loading="loading">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>合格率</template>
          <div style="font-size: 32px; font-weight: bold" :style="{ color: (summary?.ok_rate ?? 0) >= 95 ? '#67c23a' : '#f56c6c' }">
            {{ summary?.ok_rate ?? 0 }}%
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>工单数</template>
          <div style="font-size: 32px; font-weight: bold; color: #409eff">
            {{ summary?.total_orders ?? 0 }}
            <span style="font-size: 14px; color: #999">（完成 {{ summary?.done_orders ?? 0 }}）</span>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>NG 次数</template>
          <div style="font-size: 32px; font-weight: bold; color: #f56c6c">{{ summary?.ng_count ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>报警数</template>
          <div style="font-size: 32px; font-weight: bold; color: #e6a23c">{{ summary?.alert_count ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 -->
    <el-card style="margin-top: 16px">
      <div ref="trendChartRef" style="width: 100%; height: 360px" />
    </el-card>

    <!-- 报警分布 + 工位对比 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :md="12">
        <el-card>
          <div ref="alertChartRef" style="width: 100%; height: 340px" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card>
          <div ref="stationChartRef" style="width: 100%; height: 340px" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
