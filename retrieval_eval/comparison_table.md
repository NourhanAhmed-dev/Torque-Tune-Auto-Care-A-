| Architecture | Completed runs | Accuracy (mean %) | Tokens/query (mean) | Latency/query (mean s) | Evaluation status |
|---|---:|---:|---:|---:|---|
| **Naive RAG** | 6/6 | **81.12** | **1460.3** | 5.406 | Complete |
| Hybrid RAG | 6/6 | 81.12 | 1478.8 | **5.321** | Complete |
| Agentic RAG | 2/6 | 100.0* | 1397.5* | 13.801* | Incomplete - excluded from decision |

\* Agentic RAG was not included in the shipping decision because only 2 of 6
fixed evaluation questions completed. The Gemini free-tier project enforced a
5 generate-requests-per-minute limit; Agentic RAG makes multiple generation
requests per question for planning and final answer generation. Continuing
would have produced an incomplete and biased comparison, so the run was
stopped rather than reporting partial results as a full benchmark.

**Shipped default: Naive RAG.**

Naive and Hybrid RAG achieved the same measured accuracy (81.12%) on the same
six fixed questions. Naive used fewer tokens per query (1460.3 vs 1478.8).
Hybrid's latency advantage was only 0.085 seconds, which is too small in this
six-question sample to justify its additional retrieval complexity. Agentic
RAG remains implemented and demonstrated, but its incomplete benchmark was
not used for the production decision.