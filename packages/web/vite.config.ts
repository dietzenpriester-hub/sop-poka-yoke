import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

const apiUrl = process.env.VITE_API_URL || "http://localhost:8000";
const wsTarget = apiUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiUrl,
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: wsTarget,
        ws: true,
      },
      "/mjpeg": {
        target: process.env.VITE_MJPEG_URL || "http://localhost:8766",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/mjpeg/, ""),
      },
    },
  },
});
