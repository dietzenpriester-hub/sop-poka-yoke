import api from "./index";

export interface LearningStep {
  index: number;
  name: string;
  description: string;
  required_objects: string[];
  action_type: string;
  timeout_seconds: number;
  is_optional: boolean;
  reference_frame_url: string;
  ok_criteria: string;
  ng_criteria: string;
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
    api.post<{ task_id: string; status: string }>(
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
  deleteTask: (taskId: string) => api.delete(`/learning/task/${taskId}`),
};
