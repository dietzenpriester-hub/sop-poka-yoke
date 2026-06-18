import api from "./index";

export interface WorkOrderItem {
  id: number;
  sn: string;
  station_id: number | null;
  sop_template_id: number | null;
  status: string;
  operator_id: number | null;
  extra: Record<string, unknown> | null;
  start_time: string;
  end_time: string | null;
}

export interface StepRecordItem {
  id: number;
  workorder_id: number;
  step_index: number;
  step_name: string;
  result: string;
  confidence: string;
  snapshot_url: string;
  video_url: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export const workorderApi = {
  list: (params?: {
    station_id?: number;
    status?: string;
    sn?: string;
    start_date?: string;
    end_date?: string;
    skip?: number;
    limit?: number;
  }) => api.get<{ items: WorkOrderItem[]; total: number }>("/workorder/", { params }),
  get: (id: number) => api.get<WorkOrderItem>(`/workorder/${id}`),
  create: (data: { sn: string; station_id?: number; sop_template_id?: number; operator_id?: number }) =>
    api.post<WorkOrderItem>("/workorder/", data),
  start: (id: number) => api.post<{ message: string; edge_device_id: string | null }>(`/workorder/${id}/start`),
  complete: (id: number) => api.put(`/workorder/${id}/complete`),
  steps: (id: number) => api.get<StepRecordItem[]>(`/workorder/${id}/steps`),
  delete: (id: number) => api.delete(`/workorder/${id}`),
};
