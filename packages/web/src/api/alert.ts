import api from "./index";

export interface AlertItem {
  id: number;
  workorder_id: number | null;
  station_id: number | null;
  step_index: number;
  alert_type: string;
  severity: "INFO" | "WARN" | "ERROR" | "CRITICAL";
  message: string;
  video_url: string;
  acknowledged: string;
  created_at: string;
}

export interface AlertStats {
  total: number;
  unacknowledged: number;
  by_severity: Record<string, number>;
}

export const alertApi = {
  list: (params?: {
    station_id?: number;
    severity?: string;
    alert_type?: string;
    acknowledged?: string;
    skip?: number;
    limit?: number;
  }) => api.get<{ items: AlertItem[]; total: number }>("/alert/", { params }),

  get: (id: number) => api.get<AlertItem>(`/alert/${id}`),

  stats: (stationId?: number) =>
    api.get<AlertStats>("/alert/stats", { params: stationId ? { station_id: stationId } : {} }),

  unacknowledgedCount: (stationId?: number) =>
    api.get<{ count: number }>("/alert/unacknowledged-count", {
      params: stationId ? { station_id: stationId } : {},
    }),

  acknowledge: (id: number) => api.put(`/alert/${id}/acknowledge`),

  batchAcknowledge: (ids: number[]) =>
    api.put("/alert/batch-acknowledge", { alert_ids: ids }),
};
