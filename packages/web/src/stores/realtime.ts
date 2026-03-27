import { defineStore } from "pinia";
import { ref, type Ref } from "vue";

export interface StationStatus {
  station_id: string;
  status: string;
  current_step: string;
  work_order_sn: string;
  updated_at: number;
}

export const useRealtimeStore = defineStore("realtime", () => {
  const stations: Ref<Map<string, StationStatus>> = ref(new Map());
  const alerts: Ref<unknown[]> = ref([]);

  function updateStation(data: StationStatus) {
    stations.value.set(data.station_id, data);
  }

  function addAlert(alert: unknown) {
    alerts.value.unshift(alert);
    if (alerts.value.length > 100) {
      alerts.value = alerts.value.slice(0, 100);
    }
  }

  return { stations, alerts, updateStation, addAlert };
});
