import api from "./index";

export interface WorkOrder {
  id: number;
  sn: string;
  station_id: number | null;
  sop_template_id: number | null;
  status: string;
  operator_id: number | null;
  start_time: string;
  end_time: string | null;
}

export const workorderApi = {
  list: (stationId?: number) =>
    api.get<WorkOrder[]>("/workorder/", { params: stationId ? { station_id: stationId } : {} }),
  get: (id: number) => api.get<WorkOrder>(`/workorder/${id}`),
  create: (data: Partial<WorkOrder>) => api.post<WorkOrder>("/workorder/", data),
};
