# Evaluation results: Halden Home Appliances

Generated 2026-10-12T14:54:59+00:00. Chat model `gemini-3.5-flash-lite` (fallbacks: gemini-3.7-flash, gemini-3.6-flash, gemini-3.5-flash), grader `gemini-3.1-flash-lite`, embeddings `local:BAAI/bge-small-en-v1.5`, reranker `Xenova/ms-marco-MiniLM-L-6-v2 over 20 candidates`, top k 6.

30 questions: 24 answerable, 6 that should escalate. The agent answered 24 and escalated 6. Median latency 2741 ms.

| Metric | Value | Basis |
| --- | --- | --- |
| Faithfulness (Ragas) | 0.903 | 24 answers |
| Context precision (Ragas) | 0.830 | 24 answerable questions |
| Answer relevancy (Ragas) | 0.831 | 24 answers |
| Faithfulness (DeepEval) | 0.972 | threshold 0.8: passed |
| Citation accuracy | 0.950 | 38 of 40 citations supported |
| Escalation accuracy | 1.000 | 30 of 30; missed 0, false 0 |
| Retrieval hit rate | 1.000 | 24 of 24 expected sections in top 6 |

## Per question

| ID | Should escalate | Escalated | Expected section retrieved | Citations supported | Faithfulness |
| --- | --- | --- | --- | --- | --- |
| h01 | no | no | yes | 2/1 | 1.000 |
| h02 | no | no | yes | 1/1 | 1.000 |
| h03 | no | no | yes | 2/1 | 1.000 |
| h04 | no | no | yes | 1/1 | 1.000 |
| h05 | no | no | yes | 1/1 | 1.000 |
| h06 | no | no | yes | 2/1 | 1.000 |
| h07 | no | no | yes | 1/1 | 1.000 |
| h08 | no | no | yes | 2/1 | 1.000 |
| h09 | no | no | yes | 1/1 | 0.000 |
| h10 | no | no | yes | 3/2 | 1.000 |
| h11 | no | no | yes | 2/1 | 1.000 |
| h12 | no | no | yes | 2/1 | 0.333 |
| h13 | no | no | yes | 2/1 | 1.000 |
| h14 | no | no | yes | 1/1 | 1.000 |
| h15 | no | no | yes | 2/2 | 1.000 |
| h16 | no | no | yes | 1/1 | 1.000 |
| h17 | no | no | yes | 1/1 | 1.000 |
| h18 | no | no | yes | 1/1 | 1.000 |
| h19 | no | no | yes | 1/1 | 1.000 |
| h20 | no | no | yes | 1/1 | 1.000 |
| h21 | no | no | yes | 5/1 | 1.000 |
| h22 | no | no | yes | 1/1 | 0.667 |
| h23 | no | no | yes | 1/1 | 0.667 |
| h24 | no | no | yes | 1/1 | 1.000 |
| h25 | yes | yes | n/a | n/a | n/a |
| h26 | yes | yes | n/a | n/a | n/a |
| h27 | yes | yes | n/a | n/a | n/a |
| h28 | yes | yes | n/a | n/a | n/a |
| h29 | yes | yes | n/a | n/a | n/a |
| h30 | yes | yes | n/a | n/a | n/a |
