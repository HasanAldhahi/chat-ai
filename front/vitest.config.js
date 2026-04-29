import { defineConfig } from "vitest/config";

/** Keeps tests on Node; full Vite UI config still used for `npm run dev`. */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{js,mjs,jsx}"],
    passWithNoTests: false,
  },
});
