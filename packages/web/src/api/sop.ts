import api from "./index";

export interface SOPTemplate {
  id: number;
  name: string;
  version: string;
  steps: Record<string, unknown>[];
  product_model: string | null;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const sopApi = {
  list: () => api.get<SOPTemplate[]>("/sop/"),
  get: (id: number) => api.get<SOPTemplate>(`/sop/${id}`),
  create: (data: Partial<SOPTemplate>) => api.post<SOPTemplate>("/sop/", data),
  update: (id: number, data: Partial<SOPTemplate>) => api.put<SOPTemplate>(`/sop/${id}`, data),
  delete: (id: number) => api.delete(`/sop/${id}`),
};
