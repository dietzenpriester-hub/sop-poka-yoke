import api from "./index";

export interface UserItem {
  id: number;
  username: string;
  display_name: string;
  role: string;
  badge_id: string;
  created_at: string;
  updated_at: string;
}

export const userApi = {
  list: (params?: { role?: string; skip?: number; limit?: number }) =>
    api.get<UserItem[]>("/user/", { params }),

  get: (id: number) => api.get<UserItem>(`/user/${id}`),

  create: (data: { username: string; display_name: string; role: string; badge_id: string; password: string }) =>
    api.post<UserItem>("/user/", data),

  update: (id: number, data: { display_name?: string; role?: string; badge_id?: string }) =>
    api.put<UserItem>(`/user/${id}`, data),

  changePassword: (id: number, newPassword: string) =>
    api.put(`/user/${id}/password`, { new_password: newPassword }),

  delete: (id: number) => api.delete(`/user/${id}`),
};
