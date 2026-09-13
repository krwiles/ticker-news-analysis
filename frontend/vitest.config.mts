import { defineConfig } from "vitest/config";

// Standalone test runner, same relationship to the app as pytest has to
// uvicorn -- webpack.config.js (the real build) is untouched by this.
export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/vitest.setup.ts"],
  },
});
