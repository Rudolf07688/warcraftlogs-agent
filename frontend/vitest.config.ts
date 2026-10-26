import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Feature 031: component tests run in jsdom. Kept apart from vite.config.ts so the build and
// dev-server config stay unchanged; tests import from "vitest" explicitly (no globals).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx"],
  },
});
