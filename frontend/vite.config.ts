import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser talks to the Vite dev server, which proxies /api and /ws to the
// backend. Target is the backend container in Docker, or localhost on bare metal.
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend, changeOrigin: true, ws: true },
    },
  },
});
