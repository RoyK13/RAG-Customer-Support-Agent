// Captures real screenshots of /chat in light and dark themes for the landing page and README.
// Needs the API and the web app running (docker compose up, or the dev server on WEB_URL).
//   WEB_URL=http://localhost:5173 node scripts/screenshots.mjs
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const WEB_URL = process.env.WEB_URL || "http://localhost:5173";
const QUESTION = "How long is the warranty on the dishwasher pump motor?";
mkdirSync("public/screenshots", { recursive: true });

const browser = await chromium.launch();
for (const theme of ["light", "dark"]) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: theme, reducedMotion: "reduce" });
  await context.addInitScript((t) => localStorage.setItem("theme", t), theme);
  const page = await context.newPage();
  await page.goto(`${WEB_URL}/chat?dataset=halden`);
  await page.getByRole("button", { name: QUESTION }).click();
  const answer = page.getByRole("article", { name: "Agent response" });
  await answer.waitFor({ timeout: 120_000 });
  if ((await page.getByTestId("escalation").count()) > 0) throw new Error("the agent escalated; screenshot needs a cited answer");
  await page.getByRole("button", { name: "Show source 1" }).first().click();
  await page.getByRole("region", { name: "Warranty Policy" }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `public/screenshots/chat-${theme}.png` });
  console.log(`wrote public/screenshots/chat-${theme}.png`);
  await context.close();
}
await browser.close();
