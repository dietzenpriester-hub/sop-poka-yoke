import api from "./index";

export interface OverrideLogItem {
  id: number;
  workorder_id: number;
  step_index: number;
  operator_badge: string;
  reason: string;
  video_url: string;
  created_at: string;
}

export interface OverrideLogListResult {
  items: OverrideLogItem[];
  total: number;
}

export interface OverrideStats {
  total: number;
  top_operators: { badge: string; count: number }[];
  daily_counts: { date: string; count: number }[];
}

export const overrideLogApi = {
  list: (params?: {
    workorder_id?: number;
    operator_badge?: string;
    start_date?: string;
    end_date?: string;
    skip?: number;
    limit?: number;
  }) => api.get<OverrideLogListResult>("/override-log/", { params }),
  create: (data: Omit<OverrideLogItem, "id" | "created_at">) =>
    api.post<OverrideLogItem>("/override-log/", data),
  get: (id: number) => api.get<OverrideLogItem>(`/override-log/${id}`),
  byWorkorder: (workorderId: number) =>
    api.get<OverrideLogItem[]>(`/override-log/workorder/${workorderId}`),
  stats: () => api.get<OverrideStats>("/override-log/stats"),
};
