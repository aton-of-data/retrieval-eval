import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      // help.ts is literal text and cli.ts's process entry point cannot run under the suite.
      exclude: ["src/help.ts"],
      reporter: ["text-summary", "lcov"],
      // Floors, set just below what the suite reaches today. Raise them, never lower them.
      thresholds: { lines: 90, functions: 90, branches: 78, statements: 90 },
    },
  },
});
