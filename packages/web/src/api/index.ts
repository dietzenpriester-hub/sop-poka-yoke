import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
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
      window.location.href = "/login";
    }
    if (import.meta.env.DEV) {
      console.error("API Error:", error.response?.status, error.config?.url);
    }
    return Promise.reject(error);
  }
);

export default api;
