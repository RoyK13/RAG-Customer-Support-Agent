// Builds the favicon from the brand mark (brackets around a source block, see src/components/Logo.tsx)
// and renders PNG fallbacks with Playwright.
import { writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const ACCENT = "#00d4a4";
const FG = "#0a0a0a";
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="${ACCENT}"/><path d="M12.5 9H9.5V23H12.5M19.5 9H22.5V23H19.5" fill="none" stroke="${FG}" stroke-width="2.25" stroke-linecap="square"/><rect x="13.75" y="13.75" width="4.5" height="4.5" rx="1" fill="${FG}"/></svg>\n`;
writeFileSync("public/favicon.svg", svg);

const browser = await chromium.launch();
const page = await browser.newPage();
for (const [name, size] of [["favicon-32.png", 32], ["apple-touch-icon.png", 180], ["icon-192.png", 192], ["icon-512.png", 512]]) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(`<html><body style="margin:0;background:transparent">${svg.replace("<svg ", `<svg width="${size}" height="${size}" `)}</body></html>`);
  await page.locator("svg").screenshot({ path: `public/${name}`, omitBackground: true });
}
await browser.close();
console.log("wrote public/favicon.svg and PNG fallbacks");
