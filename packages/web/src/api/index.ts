import axios, { type AxiosInstance } from "axios";
import {
  STORAGE_TOKEN_KEY,
  LOGIN_PATH,
  API_TIMEOUT_MS,
  UPLOAD_TIMEOUT_MS,
} from "@/utils/constants";

function clearSession() {
  sessionStorage.removeItem(STORAGE_TOKEN_KEY);
  if (!window.location.pathname.startsWith(LOGIN_PATH)) {
    window.location.href = LOGIN_PATH;
  }
}

function attachInterceptors(instance: AxiosInstance): void {
  instance.interceptors.request.use((config) => {
    const token = sessionStorage.getItem(STORAGE_TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  instance.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        clearSession();
      }
      if (import.meta.env.DEV) {
        console.error("API Error:", error.response?.status, error.config?.url);
      }
      return Promise.reject(error);
    }
  );
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
  timeout: API_TIMEOUT_MS,
});
attachInterceptors(api);

const apiUpload = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
  timeout: UPLOAD_TIMEOUT_MS,
});
attachInterceptors(apiUpload);

export { apiUpload };
export default api;
