| Strategy | Detail recalled | Avg input tokens/run | Avg output tokens/run | Avg latency |
|---|---|---|---|---|
| Sliding window (last 10 turns) | 1/10 | 10,547 | 289 | 2.4s |
| Observation masking (keep last 3) | 8/10 | 3,929 | 19 | 2.2s |
| Recursive summarization (every 15 turns) | 10/10 | 7,699 | 104 | 4.1s |
| Zone-based pruning (4 zones) | 10/10 | 10,808 | 69 | 4.1s |
