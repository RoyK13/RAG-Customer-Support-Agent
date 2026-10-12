"""Writes the evaluation results table into README.md from eval/results/<name>/latest.json.

    python -m eval.readme_table

Replaces the text between the results markers in README.md, so the numbers in the
README always come from the saved results and are never typed by hand.
"""

import json
import sys
from pathlib import Path

from app.config import ROOT_DIR
from app.datasets import all_datasets

START, END = "<!-- results:start -->", "<!-- results:end -->"
COLUMNS = [
    ("faithfulness", "Faithfulness (Ragas)"),
    ("context_precision", "Context precision (Ragas)"),
    ("answer_relevancy", "Answer relevancy (Ragas)"),
    ("deepeval_faithfulness", "Faithfulness (DeepEval)"),
    ("citation_accuracy", "Citation accuracy"),
    ("escalation_accuracy", "Escalation accuracy"),
    ("retrieval_hit_rate", "Retrieval hit rate"),
]


def fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render() -> str:
    lines = ["| Dataset | " + " | ".join(label for _, label in COLUMNS) + " |", "| --- |" + " --- |" * len(COLUMNS)]
    notes = []
    for name, cfg in all_datasets().items():
        path = ROOT_DIR / "eval" / "results" / name / "latest.json"
        if not path.exists():
            lines.append(f"| {cfg.display_name} | Evaluation not run yet |" + " |" * (len(COLUMNS) - 1))
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        m = r["metrics"]
        lines.append(f"| {cfg.display_name} | " + " | ".join(fmt(m[key]["value"]) for key, _ in COLUMNS) + " |")
        c = r["config"]
        graders = ", ".join(f"`{g}`" for g in (c.get("judge_models_used") or c["judge_models"][:1]))
        notes.append(
            f"- {cfg.display_name}: {r['counts']['questions']} questions, run {r['generated_at'][:10]}. "
            f"Chat model `{c['chat_model']}`, grader {graders}, embeddings `{c['embedding']}`, "
            f"reranker {('`' + c['reranker'] + '`') if c.get('reranker') else 'none'}. "
            f"Answered {r['counts']['answered']}, escalated {r['counts']['escalated']}. "
            f"Citations supported: {m['citation_accuracy']['supported']} of {m['citation_accuracy']['total']}. "
            f"Escalations: {m['escalation_accuracy']['missed_escalations']} missed, {m['escalation_accuracy']['false_escalations']} false. "
            f"Median latency {r['latency_ms']['median']} ms. Full report: [`eval/results/{name}/latest.md`](eval/results/{name}/latest.md)."
        )
    return "\n".join(lines + [""] + notes)


def main() -> int:
    readme = ROOT_DIR / "README.md"
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("README.md has no results markers", file=sys.stderr)
        return 1
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    readme.write_text(f"{before}{START}\n{render()}\n{END}{after}", encoding="utf-8")
    print("README.md results table updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
