/**
 * 预留：后续接入 WebSocket 实时数据（工位状态、告警推送等）时使用。
 * 当前未被引用，保留 Pinia store 定义以免重复设计。
 */
import { defineStore } from "pinia";
import { computed, ref, type Ref } from "vue";

export interface StationStatus {
  station_id: string;
  status: string;
  current_step: string;
  work_order_sn: string;
  updated_at: number;
}

export interface RealtimeAlert {
  id: number;
  alert_type: string;
  severity: string;
  message: string;
  step_index: number;
  station_id: string;
  timestamp: number;
  acknowledged: boolean;
}

export const useRealtimeStore = defineStore("realtime", () => {
  const stations: Ref<Map<string, StationStatus>> = ref(new Map());
  const alerts: Ref<RealtimeAlert[]> = ref([]);

  const unacknowledgedCount = computed(() =>
    alerts.value.filter((a) => !a.acknowledged).length
  );

  function updateStation(data: StationStatus) {
    stations.value.set(data.station_id, data);
  }

  function addAlert(alert: RealtimeAlert) {
    alerts.value.unshift(alert);
    if (alerts.value.length > 200) {
      alerts.value = alerts.value.slice(0, 200);
    }
  }

  function acknowledgeAlert(alertId: number) {
    const found = alerts.value.find((a) => a.id === alertId);
    if (found) found.acknowledged = true;
  }

  function clearAlerts() {
    alerts.value = [];
  }

  return { stations, alerts, unacknowledgedCount, updateStation, addAlert, acknowledgeAlert, clearAlerts };
});
