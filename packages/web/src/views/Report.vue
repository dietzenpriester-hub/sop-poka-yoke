<script setup lang="ts">
import { onMounted } from "vue";
import { useECharts } from "@/composables/useECharts";

const { chartRef, setOption } = useECharts();

onMounted(() => {
  setOption({
    title: { text: "异常趋势（近 7 天）" },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: ["周一", "周二", "周三", "周四", "周五", "周六", "周日"] },
    yAxis: { type: "value" },
    series: [
      { name: "NG 次数", type: "bar", data: [5, 8, 3, 12, 6, 2, 4], color: "#f56c6c" },
      { name: "OVERRIDE", type: "bar", data: [1, 2, 0, 3, 1, 0, 1], color: "#e6a23c" },
    ],
  });
});
</script>

<template>
  <div>
    <h2>统计报表</h2>
    <el-card style="margin-top: 20px">
      <div ref="chartRef" style="width: 100%; height: 400px" />
    </el-card>
  </div>
</template>
