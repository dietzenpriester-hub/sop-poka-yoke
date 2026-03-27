import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
  // 默认 10s；大文件上传建议单独建 axios 实例并设更长 timeout 或配合 onUploadProgress
  timeout: 10000,
});

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("sop_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem("sop_token");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    if (import.meta.env.DEV) {
      console.error("API Error:", error.response?.status, error.config?.url);
    }
    return Promise.reject(error);
  }
);

const apiUpload = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
  timeout: 300000,
});

apiUpload.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("sop_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiUpload.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem("sop_token");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    if (import.meta.env.DEV) {
      console.error("API Error:", error.response?.status, error.config?.url);
    }
    return Promise.reject(error);
  }
);

export { apiUpload };
export default api;
