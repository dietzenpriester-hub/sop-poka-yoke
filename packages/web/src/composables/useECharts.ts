import * as echarts from "echarts";
import { onUnmounted, ref, type Ref } from "vue";

export function useECharts(): {
  chartRef: Ref<HTMLDivElement | undefined>;
  setOption: (option: echarts.EChartsOption) => void;
  resize: () => void;
} {
  const chartRef = ref<HTMLDivElement>();
  let chart: echarts.ECharts | null = null;

  const ensure = () => {
    if (!chartRef.value) return;
    if (!chart) {
      chart = echarts.init(chartRef.value);
      window.addEventListener("resize", resize);
    }
  };

  const setOption = (option: echarts.EChartsOption) => {
    ensure();
    chart?.setOption(option, true);
  };

  const resize = () => {
    chart?.resize();
  };

  onUnmounted(() => {
    window.removeEventListener("resize", resize);
    chart?.dispose();
    chart = null;
  });

  return { chartRef, setOption, resize };
}
