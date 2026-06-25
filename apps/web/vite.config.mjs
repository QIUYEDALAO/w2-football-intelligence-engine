import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:18000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/ops/": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/v1": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
