import { defineConfig, devices } from "@playwright/test";

// The tests mock the API at http://api.mock, so no backend is needed.
export default defineConfig({
  testDir: "tests",
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:4173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npx vite --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: false,
    env: { VITE_API_URL: "http://api.mock" },
    timeout: 120_000,
  },
});
