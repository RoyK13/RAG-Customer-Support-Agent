// Renders pages at desktop and phone widths in both themes for visual review, and reports console errors.
//   node scripts/review.mjs <outDir>
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const out = process.argv[2] || "review";
const base = process.env.WEB_URL || "http://localhost:5173";
const pages = (process.env.PAGES || "/,/chat,/privacy,/terms").split(",");
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const errors = [];
for (const theme of ["light", "dark"]) {
  for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
    const ctx = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: process.env.MOTION === "on" ? "no-preference" : "reduce" });
    await ctx.addInitScript((t) => localStorage.setItem("theme", t), theme);
    const page = await ctx.newPage();
    page.on("console", (m) => m.type() === "error" && errors.push(`${theme}/${label}: ${m.text()}`));
    page.on("pageerror", (e) => errors.push(`${theme}/${label}: ${e.message}`));
    for (const path of pages) {
      await page.goto(base + path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1500); // let entrance animations finish
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      if (overflow) errors.push(`${theme}/${label} ${path}: horizontal overflow`);
      const name = path === "/" ? "home" : path.slice(1);
      await page.screenshot({ path: `${out}/${name}-${label}-${theme}.png`, fullPage: true });
    }
    await ctx.close();
  }
}
await browser.close();
console.log(errors.length ? errors.join("\n") : "no console errors, no horizontal overflow");
