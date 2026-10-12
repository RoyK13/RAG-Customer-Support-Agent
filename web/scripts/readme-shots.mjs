// Captures real screenshots of the running app for the README (docs/screenshots).
// Needs the API and web app running with a working model key:
//   WEB_URL=http://localhost:5173 node scripts/readme-shots.mjs
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const WEB_URL = process.env.WEB_URL || "http://localhost:5173";
const OUT = "../docs/screenshots";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();

async function open(path, { theme = "light", width = 1440, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, colorScheme: theme });
  await context.addInitScript((t) => localStorage.setItem("theme", t), theme);
  const page = await context.newPage();
  await page.goto(WEB_URL + path);
  await page.waitForLoadState("networkidle");
  return { context, page };
}

async function ask(page, question) {
  const input = page.getByLabel("Your question");
  await input.fill(question);
  await input.press("Enter");
  await page.getByRole("article", { name: "Agent response" }).last().waitFor({ timeout: 120_000 });
  await page.waitForTimeout(500);
}

async function shot(page, name, options = {}) {
  await page.screenshot({ path: `${OUT}/${name}.png`, ...options });
  console.log(`wrote docs/screenshots/${name}.png`);
}

// 1. Landing hero
{
  const { context, page } = await open("/");
  await page.waitForTimeout(1600); // entrance animation
  await shot(page, "landing-hero");
  // 2. How it works, mid-stack
  const top = await page.locator("#how-it-works").evaluate((e) => e.getBoundingClientRect().top + window.scrollY);
  await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), top + 700);
  await page.waitForTimeout(400);
  await shot(page, "how-it-works");
  // 3. Evaluation results
  await page.locator("#results").scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shot(page, "evaluation-results", { clip: await page.locator("#results").boundingBox() });
  await context.close();
}

// 4. FastAPI answer with code, and the source panel linking to the real docs page
{
  const { context, page } = await open("/chat?dataset=fastapi");
  await ask(page, "How do I make a query parameter required?");
  await page.getByRole("button", { name: "Show source 1" }).first().click();
  await page.waitForTimeout(500);
  await shot(page, "chat-fastapi-code");
  await context.close();
}

// 5. Escalation: a question the documents cannot answer
{
  const { context, page } = await open("/chat?dataset=halden");
  await ask(page, "Do you offer a student discount?");
  await shot(page, "chat-escalation");
  await context.close();
}

// 6. Phone, dark theme: the source panel as a bottom sheet
{
  const { context, page } = await open("/chat?dataset=halden", { theme: "dark", width: 390, height: 844 });
  await ask(page, "My washer shows error F02. What should I do?");
  await page.getByRole("button", { name: "Show source 1" }).first().click();
  await page.getByRole("dialog").waitFor();
  await page.waitForTimeout(600);
  await shot(page, "mobile-source-sheet");
  await context.close();
}

await browser.close();
