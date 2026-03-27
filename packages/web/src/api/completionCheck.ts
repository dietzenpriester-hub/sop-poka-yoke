import api from "./index";

export interface CompletionCheckItem {
  id: number;
  workorder_id: number;
  result: string;
  check_items: Record<string, unknown>[] | null;
  completion_photo_url: string;
  reference_photo_url: string;
  similarity_score: number;
  defects: string;
  checked_at: string;
}

export interface CompletionCheckStats {
  total: number;
  pass_count: number;
  fail_count: number;
  rework_count: number;
  pass_rate: number;
}

export interface CompletionCheckListResult {
  items: CompletionCheckItem[];
  total: number;
}

export const completionCheckApi = {
  list: (params?: { workorder_id?: number; result?: string; skip?: number; limit?: number }) =>
    api.get<CompletionCheckListResult>("/completion-check/", { params }),
  create: (data: Omit<CompletionCheckItem, "id" | "checked_at">) =>
    api.post<CompletionCheckItem>("/completion-check/", data),
  get: (id: number) => api.get<CompletionCheckItem>(`/completion-check/${id}`),
  byWorkorder: (workorderId: number) =>
    api.get<CompletionCheckItem[]>(`/completion-check/workorder/${workorderId}`),
  stats: (params?: { workorder_id?: number }) =>
    api.get<CompletionCheckStats>("/completion-check/stats", { params }),
};
