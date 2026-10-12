"""DeepEval regression suite: fails if mean faithfulness drops below a threshold.

    python -m eval.regression --dataset halden

Reads the cached agent responses from the last `python -m eval.run` and exits
with status 1 if mean faithfulness is below EVAL_FAITHFULNESS_THRESHOLD.
"""

import argparse
import json
import sys
from pathlib import Path

from eval.judge import DeepEvalJudge, JudgeClient

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def deepeval_faithfulness(rows: list[dict], judge: JudgeClient, threshold: float) -> dict:
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.test_case import LLMTestCase

    model = DeepEvalJudge(judge)
    scores: dict[str, float] = {}
    for row in rows:
        metric = FaithfulnessMetric(threshold=threshold, model=model, include_reason=False, async_mode=False)
        case = LLMTestCase(input=row["question"], actual_output=row["answer"],
                           retrieval_context=[c["text"] for c in row["retrieved"]])
        metric.measure(case)
        scores[row["id"]] = float(metric.score)
    mean = sum(scores.values()) / len(scores) if scores else None
    return {
        "value": mean,
        "n": len(scores),
        "threshold": threshold,
        "passed": mean is not None and mean >= threshold,
        "below_threshold": sorted(k for k, v in scores.items() if v < threshold),
        "scores": scores,
    }


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from eval.run import eval_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args(argv)
    cache = RESULTS_DIR / args.dataset / "cache" / "responses.json"
    if not cache.exists():
        print(f"No cached responses at {cache}. Run python -m eval.run --dataset {args.dataset} first.")
        return 2
    rows = [r for r in json.loads(cache.read_text(encoding="utf-8")).values() if not r["escalated"]]
    es = eval_settings()
    s = get_settings()
    judge = JudgeClient(api_key=s.llm_api_key, base_url=s.llm_base_url, models=es["judge_models"],
                        reasoning_effort=s.llm_reasoning_effort)
    result = deepeval_faithfulness(rows, judge, es["threshold"])
    status = "PASSED" if result["passed"] else "FAILED"
    print(f"DeepEval faithfulness {result['value']:.3f} over {result['n']} answers, threshold {es['threshold']}: {status}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
