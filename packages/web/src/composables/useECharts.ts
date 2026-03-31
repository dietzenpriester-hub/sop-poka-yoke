import * as echarts from "echarts";
import { onUnmounted, ref, type Ref } from "vue";

export function useECharts(): {
  chartRef: Ref<HTMLDivElement | undefined>;
  setOption: (option: echarts.EChartsOption) => void;
  resize: () => void;
} {
  const chartRef = ref<HTMLDivElement>();
  let chart: echarts.ECharts | null = null;
  let listening = false;

  const resize = () => {
    chart?.resize();
  };

  const ensure = () => {
    if (!chartRef.value) return;
    if (!chart) {
      chart = echarts.init(chartRef.value);
    }
    if (!listening) {
      window.addEventListener("resize", resize);
      listening = true;
    }
  };

  const setOption = (option: echarts.EChartsOption) => {
    ensure();
    chart?.setOption(option, true);
  };

  onUnmounted(() => {
    if (listening) {
      window.removeEventListener("resize", resize);
      listening = false;
    }
    chart?.dispose();
    chart = null;
  });

  return { chartRef, setOption, resize };
}
