import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // The static showcase does not ship the backend-dependent embed loader.
  publicDir: mode === "showcase" ? false : "public",
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    restoreMocks: true,
  },
  server: {
    port: 5173,
  },
}));
