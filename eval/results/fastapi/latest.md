# Evaluation results: FastAPI documentation

Generated 2026-10-12T15:09:18+00:00. Chat model `gemini-3.5-flash-lite` (fallbacks: gemini-3.7-flash, gemini-3.6-flash, gemini-3.5-flash), grader `gemini-3.1-flash-lite`, `gemini-flash-lite-latest`, embeddings `local:BAAI/bge-small-en-v1.5`, reranker `Xenova/ms-marco-MiniLM-L-6-v2 over 20 candidates`, top k 6.

30 questions: 24 answerable, 6 that should escalate. The agent answered 24 and escalated 6. Median latency 5200 ms.

| Metric | Value | Basis |
| --- | --- | --- |
| Faithfulness (Ragas) | 0.990 | 24 answers |
| Context precision (Ragas) | 0.746 | 24 answerable questions |
| Answer relevancy (Ragas) | 0.899 | 24 answers |
| Faithfulness (DeepEval) | 1.000 | threshold 0.8: passed |
| Citation accuracy | 0.882 | 45 of 51 citations supported |
| Escalation accuracy | 1.000 | 30 of 30; missed 0, false 0 |
| Retrieval hit rate | 1.000 | 24 of 24 expected sections in top 6 |

## Per question

| ID | Should escalate | Escalated | Expected section retrieved | Citations supported | Faithfulness |
| --- | --- | --- | --- | --- | --- |
| f01 | no | no | yes | 1/1 | 0.750 |
| f02 | no | no | yes | 2/3 | 1.000 |
| f03 | no | no | yes | 2/1 | 1.000 |
| f04 | no | no | yes | 2/1 | 1.000 |
| f05 | no | no | yes | 2/2 | 1.000 |
| f06 | no | no | yes | 1/1 | 1.000 |
| f07 | no | no | yes | 1/1 | 1.000 |
| f08 | no | no | yes | 1/1 | 1.000 |
| f09 | no | no | yes | 6/2 | 1.000 |
| f10 | no | no | yes | 2/1 | 1.000 |
| f11 | no | no | yes | 2/1 | 1.000 |
| f12 | no | no | yes | 2/2 | 1.000 |
| f13 | no | no | yes | 3/2 | 1.000 |
| f14 | no | no | yes | 0/2 | 1.000 |
| f15 | no | no | yes | 2/1 | 1.000 |
| f16 | no | no | yes | 1/1 | 1.000 |
| f17 | no | no | yes | 2/2 | 1.000 |
| f18 | no | no | yes | 3/2 | 1.000 |
| f19 | no | no | yes | 1/1 | 1.000 |
| f20 | no | no | yes | 4/2 | 1.000 |
| f21 | no | no | yes | 1/1 | 1.000 |
| f22 | no | no | yes | 1/1 | 1.000 |
| f23 | no | no | yes | 1/1 | 1.000 |
| f24 | no | no | yes | 2/1 | 1.000 |
| f25 | yes | yes | n/a | n/a | n/a |
| f26 | yes | yes | n/a | n/a | n/a |
| f27 | yes | yes | n/a | n/a | n/a |
| f28 | yes | yes | n/a | n/a | n/a |
| f29 | yes | yes | n/a | n/a | n/a |
| f30 | yes | yes | n/a | n/a | n/a |
