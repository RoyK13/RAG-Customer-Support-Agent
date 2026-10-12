"""Evaluate the running API on a dataset's questions.

    python -m eval.run --dataset halden
    python -m eval.run --dataset all

Calls POST /chat for every question in data/<name>/questions.jsonl, reads the
retrieved chunks for each turn from the Postgres conversation log, and reports:

- Ragas: faithfulness, context precision, answer relevancy
- DeepEval: faithfulness regression suite with a configurable threshold
- Citation accuracy: share of citations whose chunk supports the claim it is attached to
- Escalation accuracy: whether the agent escalated exactly when it should have
- Retrieval hit rate: share of answerable questions whose expected section was retrieved

Writes eval/results/<name>/latest.json, latest.md, and a timestamped JSON copy.
Agent responses and grader replies are cached, so a run interrupted by a quota
limit resumes where it stopped. Use --fresh to call the API again.
"""

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import ROOT_DIR, get_settings
from app.datasets import all_datasets
from eval.judge import JudgeClient, QuotaExhausted, is_daily_quota_error, ragas_components
from eval.metrics import escalation_summary, judge_citations, retrieval_hit
from eval.regression import deepeval_faithfulness

RESULTS_DIR = Path(__file__).resolve().parent / "results"


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    eval_api_url: str = "http://localhost:8000"
    eval_judge_model: str = "gemini-3.1-flash-lite"
    eval_judge_fallback_models: str = "gemini-flash-lite-latest"
    eval_faithfulness_threshold: float = 0.8
    eval_request_delay_seconds: float = 12.0
    admin_token: str = ""


def eval_settings() -> dict:
    s = EvalSettings()
    models = [s.eval_judge_model] + [m.strip() for m in s.eval_judge_fallback_models.split(",") if m.strip()]
    return {"api_url": s.eval_api_url.rstrip("/"), "judge_models": models, "threshold": s.eval_faithfulness_threshold,
            "delay": s.eval_request_delay_seconds, "admin_token": s.admin_token}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def row_key(row: dict) -> str:
    """Cache key for a scored row: question ID plus a hash of the answer and retrieved context,
    so cached scores are never reused for a different answer."""
    blob = json.dumps([row["answer"], [c["chunk_id"] for c in row["retrieved"]]], ensure_ascii=False)
    return f"{row['id']}:{hashlib.sha1(blob.encode('utf-8')).hexdigest()[:12]}"


def mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and not math.isnan(v)]
    return sum(clean) / len(clean) if clean else None


class StopRun(RuntimeError):
    pass


def collect_responses(name: str, questions: list[dict], es: dict, fresh: bool) -> dict:
    from app.db import get_db

    cache_path = RESULTS_DIR / name / "cache" / "responses.json"
    cache = {} if fresh else load_json(cache_path)
    db = get_db()
    headers = {"X-Admin-Token": es["admin_token"]} if es["admin_token"] else {}
    with httpx.Client(base_url=es["api_url"], timeout=180, headers=headers) as client:
        for i, q in enumerate(questions, 1):
            if q["id"] in cache:
                continue
            started = time.perf_counter()
            r = client.post("/chat", json={"question": q["question"], "dataset": name, "session_id": f"eval-{name}"})
            if r.status_code != 200:
                save_json(cache_path, cache)
                raise StopRun(f"/chat returned {r.status_code} on {q['id']}: {r.text[:300]}. "
                              f"{len(cache)}/{len(questions)} responses saved; re-run to resume.")
            body = r.json()
            turn = db.get_turn(body["trace_id"])
            retrieved = db.get_chunks(list(turn["retrieved_chunk_ids"])) if turn else []
            cache[q["id"]] = {
                **q,
                "answer": body["answer"],
                "citations": body["citations"],
                "escalated": body["escalated"],
                "trace_id": body["trace_id"],
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "retrieved": [{k: c[k] for k in ("chunk_id", "doc_id", "section_path", "text")} for c in retrieved],
            }
            save_json(cache_path, cache)
            print(f"  [{i}/{len(questions)}] {q['id']} escalated={body['escalated']} ({cache[q['id']]['latency_ms']} ms)")
            time.sleep(es["delay"])
    return cache


def run_ragas(name: str, rows: list[dict], es: dict, metric_cache: dict) -> set[str]:
    """Scores every row with Ragas and returns the grader models that produced the scores."""
    from ragas.metrics.collections import AnswerRelevancy, ContextPrecisionWithReference, Faithfulness

    s = get_settings()
    cache_path = RESULTS_DIR / name / "cache" / "metrics.json"
    models = list(es["judge_models"])

    def build(model: str):
        llm, emb = ragas_components(api_key=s.llm_api_key, base_url=s.llm_base_url, model=model,
                                    reasoning_effort=s.llm_reasoning_effort)
        return {
            "faithfulness": Faithfulness(llm=llm),
            "context_precision": ContextPrecisionWithReference(llm=llm),
            # strictness=1 generates one question per answer instead of three, to save grader quota.
            "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=emb, strictness=1),
        }

    metrics = build(models[0])
    used: set[str] = set()
    jobs = []
    for row in rows:
        contexts = [c["text"] for c in row["retrieved"]]
        if not row["escalated"]:
            jobs.append(("faithfulness", row, dict(user_input=row["question"], response=row["answer"], retrieved_contexts=contexts)))
            jobs.append(("answer_relevancy", row, dict(user_input=row["question"], response=row["answer"])))
        if not row["should_escalate"] and contexts:
            jobs.append(("context_precision", row, dict(user_input=row["question"], reference=row["expected_answer"], retrieved_contexts=contexts)))

    for metric_name, row, kwargs in jobs:
        key = f"ragas:{metric_name}:{row_key(row)}"
        if key in metric_cache:
            used.add(metric_cache.get(f"model:{key}", models[0]))
            continue
        while True:
            try:
                result = asyncio.run(metrics[metric_name].ascore(**kwargs))
                metric_cache[key] = float(result.value) if result.value is not None else None
                metric_cache[f"model:{key}"] = models[0]
                used.add(models[0])
                break
            except Exception as exc:
                if is_daily_quota_error(exc) and len(models) > 1:
                    models.pop(0)
                    print(f"  ragas grader switched to {models[0]}")
                    metrics = build(models[0])
                    continue
                save_json(cache_path, metric_cache)
                raise StopRun(f"Ragas {metric_name} failed on {row['id']}: {type(exc).__name__}: {str(exc)[:300]}") from exc
        save_json(cache_path, metric_cache)
        print(f"  ragas {metric_name} {row['id']}: {metric_cache[key]}")
    return used


def summarize_ragas(rows: list[dict], metric_cache: dict) -> dict:
    out = {}
    for metric in ("faithfulness", "context_precision", "answer_relevancy"):
        values = [metric_cache.get(f"ragas:{metric}:{row_key(r)}") for r in rows]
        scored = [v for v in values if v is not None and not math.isnan(v)]
        out[metric] = {"value": mean(scored), "n": len(scored), "source": "ragas"}
    return out


def run_dataset(name: str, args, es: dict) -> int:
    cfg = all_datasets()[name]
    qfile = cfg.path / "questions.jsonl"
    questions = [json.loads(line) for line in qfile.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        questions = questions[: args.limit]
    s = get_settings()
    print(f"[{name}] {len(questions)} questions against {es['api_url']}")

    responses = collect_responses(name, questions, es, args.fresh)
    rows = [responses[q["id"]] for q in questions]
    answered = [r for r in rows if not r["escalated"]]
    answerable = [r for r in rows if not r["should_escalate"]]

    metric_cache_path = RESULTS_DIR / name / "cache" / "metrics.json"
    metric_cache = load_json(metric_cache_path)
    judge = JudgeClient(api_key=s.llm_api_key, base_url=s.llm_base_url, models=es["judge_models"],
                        reasoning_effort=s.llm_reasoning_effort)

    print(f"[{name}] citation accuracy")
    supported = total = 0
    for r in answered:
        key = f"citations:{row_key(r)}"
        if key not in metric_cache:
            metric_cache[key] = judge_citations(judge, r["answer"], r["citations"])
            save_json(metric_cache_path, metric_cache)
        supported += sum(metric_cache[key])
        total += len(metric_cache[key])
        r["citation_verdicts"] = metric_cache[key]

    print(f"[{name}] Ragas")
    ragas_models = run_ragas(name, rows, es, metric_cache)

    print(f"[{name}] DeepEval regression suite")
    deepeval = deepeval_faithfulness(answered, judge, es["threshold"])

    hits = [retrieval_hit(r.get("expected_source"), r["retrieved"]) for r in answerable]
    metrics = {
        **summarize_ragas(rows, metric_cache),
        "deepeval_faithfulness": {k: v for k, v in deepeval.items() if k != "scores"},
        "citation_accuracy": {"value": supported / total if total else None, "supported": supported, "total": total},
        "escalation_accuracy": escalation_summary(rows),
        "retrieval_hit_rate": {"value": sum(hits) / len(hits) if hits else None, "hits": sum(hits), "total": len(hits)},
    }
    latencies = sorted(r["latency_ms"] for r in rows)
    result = {
        "dataset": name,
        "display_name": cfg.display_name,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {
            "chat_model": s.llm_model,
            "chat_fallback_models": s.fallback_models,
            "judge_models": es["judge_models"],
            "judge_models_used": sorted(ragas_models | judge.models_used),
            "embedding": f"{s.embedding_provider}:{s.embedding_model}",
            "top_k": s.retrieval_top_k,
            "reranker": f"{s.reranker_model} over {s.rerank_candidates} candidates" if s.rerank_candidates > s.retrieval_top_k else None,
            "faithfulness_threshold": es["threshold"],
        },
        "counts": {
            "questions": len(rows),
            "answerable": len(answerable),
            "unanswerable": len(rows) - len(answerable),
            "answered": len(answered),
            "escalated": len(rows) - len(answered),
        },
        "latency_ms": {"median": latencies[len(latencies) // 2], "max": latencies[-1]},
        "metrics": metrics,
        "regression": {"passed": deepeval["passed"], "threshold": es["threshold"]},
        "per_question": [
            {
                "id": r["id"],
                "question": r["question"],
                "should_escalate": r["should_escalate"],
                "escalated": r["escalated"],
                "retrieval_hit": retrieval_hit(r.get("expected_source"), r["retrieved"]),
                "citations": len(r["citations"]),
                "citations_supported": sum(r.get("citation_verdicts", [])),
                "faithfulness": metric_cache.get(f"ragas:faithfulness:{row_key(r)}"),
                "context_precision": metric_cache.get(f"ragas:context_precision:{row_key(r)}"),
                "answer_relevancy": metric_cache.get(f"ragas:answer_relevancy:{row_key(r)}"),
                "deepeval_faithfulness": deepeval["scores"].get(r["id"]),
                "answer": r["answer"],
                "trace_id": r["trace_id"],
            }
            for r in rows
        ],
    }
    if args.limit:
        print(f"[{name}] --limit was used, so results are not written to latest.json")
        print(json.dumps(metrics, indent=2))
        return 0 if deepeval["passed"] else 1

    out_dir = RESULTS_DIR / name
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    save_json(out_dir / "latest.json", result)
    save_json(out_dir / f"{stamp}.json", result)
    (out_dir / "latest.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"[{name}] wrote {out_dir / 'latest.json'}")
    print(render_markdown(result).split("## Per question")[0])
    return 0 if deepeval["passed"] else 1


def fmt(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def render_markdown(r: dict) -> str:
    m = r["metrics"]
    c = r["config"]
    reranker = f"`{c['reranker']}`" if c.get("reranker") else "none"
    lines = [
        f"# Evaluation results: {r['display_name']}",
        "",
        f"Generated {r['generated_at']}. Chat model `{c['chat_model']}` (fallbacks: {', '.join(c['chat_fallback_models']) or 'none'}), "
        f"grader {', '.join(f'`{m}`' for m in c.get('judge_models_used') or c['judge_models'][:1])}, embeddings `{c['embedding']}`, "
        f"reranker {reranker}, top k {c['top_k']}.",
        "",
        f"{r['counts']['questions']} questions: {r['counts']['answerable']} answerable, "
        f"{r['counts']['unanswerable']} that should escalate. The agent answered {r['counts']['answered']} "
        f"and escalated {r['counts']['escalated']}. Median latency {r['latency_ms']['median']} ms.",
        "",
        "| Metric | Value | Basis |",
        "| --- | --- | --- |",
        f"| Faithfulness (Ragas) | {fmt(m['faithfulness']['value'])} | {m['faithfulness']['n']} answers |",
        f"| Context precision (Ragas) | {fmt(m['context_precision']['value'])} | {m['context_precision']['n']} answerable questions |",
        f"| Answer relevancy (Ragas) | {fmt(m['answer_relevancy']['value'])} | {m['answer_relevancy']['n']} answers |",
        f"| Faithfulness (DeepEval) | {fmt(m['deepeval_faithfulness']['value'])} | threshold {m['deepeval_faithfulness']['threshold']}: "
        f"{'passed' if m['deepeval_faithfulness']['passed'] else 'FAILED'} |",
        f"| Citation accuracy | {fmt(m['citation_accuracy']['value'])} | {m['citation_accuracy']['supported']} of {m['citation_accuracy']['total']} citations supported |",
        f"| Escalation accuracy | {fmt(m['escalation_accuracy']['value'])} | {m['escalation_accuracy']['correct']} of {m['escalation_accuracy']['total']}; "
        f"missed {m['escalation_accuracy']['missed_escalations']}, false {m['escalation_accuracy']['false_escalations']} |",
        f"| Retrieval hit rate | {fmt(m['retrieval_hit_rate']['value'])} | {m['retrieval_hit_rate']['hits']} of {m['retrieval_hit_rate']['total']} expected sections in top {c['top_k']} |",
        "",
        "## Per question",
        "",
        "| ID | Should escalate | Escalated | Expected section retrieved | Citations supported | Faithfulness |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for q in r["per_question"]:
        hit = "n/a" if q["retrieval_hit"] is None else ("yes" if q["retrieval_hit"] else "no")
        cites = f"{q['citations_supported']}/{q['citations']}" if q["citations"] else "n/a"
        lines.append(f"| {q['id']} | {'yes' if q['should_escalate'] else 'no'} | {'yes' if q['escalated'] else 'no'} | {hit} | {cites} | {fmt(q['faithfulness'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the support agent API.")
    parser.add_argument("--dataset", required=True, help="dataset name, or 'all'")
    parser.add_argument("--fresh", action="store_true", help="ignore cached API responses")
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions (results not saved)")
    args = parser.parse_args(argv)

    datasets = all_datasets()
    names = list(datasets) if args.dataset == "all" else [args.dataset]
    unknown = [n for n in names if n not in datasets]
    if unknown:
        print(f"Unknown dataset {unknown[0]!r}. Available: {', '.join(datasets)}", file=sys.stderr)
        return 2

    from app.db import get_db

    es = eval_settings()
    status = 0
    try:
        for name in names:
            try:
                status |= run_dataset(name, args, es)
            except (StopRun, QuotaExhausted) as exc:
                print(f"[{name}] stopped: {exc}", file=sys.stderr)
                status |= 3
    finally:
        get_db().close()
    return status


if __name__ == "__main__":
    sys.exit(main())
