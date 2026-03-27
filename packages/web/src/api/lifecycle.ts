import api from "./index";

export interface RetentionPolicy {
  type_name: string;
  retention_days: number;
  description: string;
}

export interface StorageStats {
  total_step_records: number;
  total_alerts: number;
  total_material_checks: number;
  total_completion_checks: number;
  total_override_logs: number;
  expired_counts: Record<string, number>;
}

export interface CleanupLog {
  id: number;
  cleanup_type: string;
  records_cleaned: number;
  objects_deleted: number;
  bytes_freed: number;
  status: string;
  error_message: string;
  started_at: string;
  completed_at: string | null;
}

export interface CleanupRunResult {
  log_id: number;
  status: string;
  records_cleaned: number;
  objects_deleted: number;
  message: string;
}

export const lifecycleApi = {
  getPolicies: () => api.get<{ policies: RetentionPolicy[] }>("/lifecycle/policies"),
  getStats: () => api.get<StorageStats>("/lifecycle/stats"),
  runCleanup: (dryRun: boolean = false) =>
    api.post<CleanupRunResult>(`/lifecycle/run?dry_run=${dryRun}`),
  getHistory: (params?: { skip?: number; limit?: number }) =>
    api.get<CleanupLog[]>("/lifecycle/history", { params }),
};
