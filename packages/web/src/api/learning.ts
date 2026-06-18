import api, { apiUpload } from "./index";

export interface LearningStep {
  index: number;
  name: string;
  description: string;
  required_objects: string[];
  action_type: string;
  timeout_seconds: number;
  is_optional: boolean;
  reference_frame_url: string;
  reference_frame_b64: string;
  reference_frame_timestamp: number;
  ok_criteria: string;
  ng_criteria: string;
  start_sec: number;
  end_sec: number;
  segment_ids: number[];
  review_status: "pending" | "confirmed" | "ignored" | "needs_rework";
  evidence_status: "supported" | "weak" | "missing" | "";
  confirmation_note: string;
  human_reviewed: boolean;
  reviewed_at: string;
  grounding_supported?: boolean | null;
  grounding_confidence?: number | null;
  grounding_issue?: string;
  source_confidence?: number | null;
}

export interface LearningTask {
  id: number;
  task_id: string;
  product_model: string;
  process_name: string;
  video_path: string;
  status: string;
  progress: number;
  steps: LearningStep[];
  analysis_detail: Record<string, unknown>;
  error_message: string;
  template_id: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface LearningTaskListResult {
  items: LearningTask[];
  total: number;
}

export const learningApi = {
  uploadVideo: (formData: FormData, productModel: string, processName: string) =>
    apiUpload.post<{ task_id: string; status: string }>(
      `/learning/upload-video?product_model=${encodeURIComponent(productModel)}&process_name=${encodeURIComponent(processName)}`,
      formData
    ),
  listTasks: (params?: { skip?: number; limit?: number }) =>
    api.get<LearningTaskListResult>("/learning/tasks", { params }),
  getTask: (taskId: string) => api.get<LearningTask>(`/learning/task/${taskId}`),
  updateSteps: (taskId: string, steps: LearningStep[]) =>
    api.put(`/learning/task/${taskId}/steps`, { steps }),
  confirmTask: (taskId: string) =>
    api.post<{ template_id: number; name: string; step_count: number }>(`/learning/task/${taskId}/confirm`),
  retryTask: (taskId: string) => api.post<LearningTask>(`/learning/task/${taskId}/retry`),
  deleteTask: (taskId: string) => api.delete(`/learning/task/${taskId}`),
};
