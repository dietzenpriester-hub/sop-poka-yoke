import api from "./index";

export interface MaterialCheckItem {
  id: number;
  workorder_id: number;
  bom_item: string;
  detected_material: string;
  result: string;
  confidence: number;
  snapshot_url: string;
  detail: string;
  checked_at: string;
}

export interface MaterialCheckStats {
  total: number;
  ok_count: number;
  ng_count: number;
  warn_count: number;
  pass_rate: number;
}

export interface MaterialCheckListResult {
  items: MaterialCheckItem[];
  total: number;
}

export const materialCheckApi = {
  list: (params?: {
    workorder_id?: number;
    result?: string;
    bom_item?: string;
    skip?: number;
    limit?: number;
  }) => api.get<MaterialCheckListResult>("/material-check/", { params }),
  create: (data: Omit<MaterialCheckItem, "id" | "checked_at">) =>
    api.post<MaterialCheckItem>("/material-check/", data),
  get: (id: number) => api.get<MaterialCheckItem>(`/material-check/${id}`),
  byWorkorder: (workorderId: number) =>
    api.get<MaterialCheckItem[]>(`/material-check/workorder/${workorderId}`),
  stats: (params?: { workorder_id?: number }) =>
    api.get<MaterialCheckStats>("/material-check/stats", { params }),
};
