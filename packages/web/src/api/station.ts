import api from "./index";

export interface StationItem {
  id: number;
  name: string;
  line_id: string;
  edge_device_id: string;
  rtsp_url: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface StationStats {
  station_id: number;
  name: string;
  workorder_count: number;
  alert_count: number;
}

export const stationApi = {
  list: (params?: { line_id?: string; skip?: number; limit?: number }) =>
    api.get<StationItem[]>("/station/", { params }),

  get: (id: number) => api.get<StationItem>(`/station/${id}`),

  create: (data: {
    name: string;
    line_id: string;
    edge_device_id: string;
    rtsp_url: string;
    description: string;
  }) => api.post<StationItem>("/station/", data),

  update: (
    id: number,
    data: Partial<{
      name: string;
      line_id: string;
      edge_device_id: string;
      rtsp_url: string;
      description: string;
    }>
  ) => api.put<StationItem>(`/station/${id}`, data),

  delete: (id: number) => api.delete(`/station/${id}`),

  stats: (id: number) => api.get<StationStats>(`/station/${id}/stats`),
};
