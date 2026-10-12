// Copies evaluation results into the web app at build time.
// Reads data/<name>/dataset.yaml and eval/results/<name>/latest.json. Numbers are copied as-is.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const dataDir = join(root, "data");
const resultsDir = join(root, "eval", "results");
const out = join(root, "web", "src", "generated", "eval.json");

const datasets = readdirSync(dataDir, { withFileTypes: true })
  .filter((d) => d.isDirectory() && existsSync(join(dataDir, d.name, "dataset.yaml")))
  .map((d) => {
    const cfg = parse(readFileSync(join(dataDir, d.name, "dataset.yaml"), "utf8"));
    const file = join(resultsDir, d.name, "latest.json");
    const result = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : null;
    return {
      name: cfg.name,
      display_name: cfg.display_name,
      notice: cfg.notice ?? null,
      result: result && {
        generated_at: result.generated_at,
        config: result.config,
        counts: result.counts,
        metrics: result.metrics,
      },
    };
  });

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify({ datasets }, null, 2) + "\n");
console.log(`eval results: ${datasets.map((d) => `${d.name}=${d.result ? "found" : "missing"}`).join(", ")}`);
