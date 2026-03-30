import axios, { type AxiosInstance } from "axios";

function clearSession() {
  sessionStorage.removeItem("sop_token");
  if (!window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

function attachInterceptors(instance: AxiosInstance): void {
  instance.interceptors.request.use((config) => {
    const token = sessionStorage.getItem("sop_token");
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
  timeout: 10000,
});
attachInterceptors(api);

const apiUpload = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
  timeout: 300000,
});
attachInterceptors(apiUpload);

export { apiUpload };
export default api;
