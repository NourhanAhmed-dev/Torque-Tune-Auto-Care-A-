# Torque-Tune Auto Care — MCP Server + Memory & Grounded Knowledge

> This project spans two labs on the same company, same repo, same database, same MCP server:
> - **Session 1 (MCP Server Lab):** Built the baseline server with elicitation, sampling, notifications, and defensive tool design.
> - **Session 3 (Memory & RAG Lab):** Extended the same server with long-term memory and grounded retrieval.
>
> Nothing from Session 1 was duplicated or rebuilt — every Session-3 concern imports from and builds on top of the existing `mcp_server/` and `db/`.

---

## Part I: The Problem We Solve

### Session-1 problem (still live)
Torque-Tune is a performance/tuning garage chain. Front-desk staff and technicians both need an LLM assistant that can look up clients, vehicles, appointments, and tuning history, and let technicians log work and invoice clients — without raw database access. The catch: some tuning work (ECU remaps, catalytic converter/DPF removal) can void a vehicle's emissions warranty and affect road-legal compliance. That work must never be logged as "done" without an explicit technician sign-off confirming the client was told. That's the genuine risk the server is built around, and it's what justifies every MCP protocol concern below.

### Session-3 problems (what we added)
Once real usage started on the Session-1 server, two new problems appeared:

**Problem 1: Memory loss across sessions.**
Mechanics re-explain vehicle history (e.g., *"this car has an aftermarket radiator from an accident"*) every visit. The short-term buffer forgets the moment a session ends, which costs us rework and — worse — wrong parts ordered (an OEM radiator for a car that was modified).

**Problem 2: Knowledge buried in ungoverned documents.**
Critical service procedures, torque specs, and compliance policies live in a 40-page binder of service bulletins (`TSB-*`), policy manuals (`POL-*`), and parts specs (`PT-*`). Nobody wants to turn these into 40 new MCP tools. When the agent hallucinates a spec, it's a safety and liability issue.

**Why forgetting/hallucinating costs us:**
- Forgetting an aftermarket modification → wrong OEM part ordered → rework + warranty dispute
- Fabricating a torque spec → engine damage + liability
- Missing an emissions-affecting modification → regulatory non-compliance

---

## Part II: How Each Concern Shows Up (Grader Map)

### MCP Server concerns (Session 1 — still live)

| Concern | Where | Why it's genuine |
|---|---|---|
| **Capability negotiation** | `mcp_server/server.py` → `list_tools()` | Client declares elicitation support at init; without it, write tools degrade to `flag_*_for_review`. |
| **Notifications** | `authenticate_technician` handler | Session starts read-only; on auth, server calls `send_tool_list_changed()` — write tools appear without reconnect. |
| **Elicitation** | `log_tuning_modification` | For `category == "emissions_affecting"`, server calls `session.elicit(...)` mid-call and pauses for explicit confirmation before marking `complete`. Decline leaves it `awaiting_signoff`. |
| **Sampling** | `log_tuning_modification` | Before eliciting, server asks client model (`session.create_message`) to draft a risk summary for that specific modification; falls back to a static sentence if sampling unsupported. |
| **Resources** | `list_resources()` / `read_resource()` | Emissions/warranty policy exposed via `resources/read`, not wrapped in a tool. |
| **Prompts** | `mcp_server/prompts.py` | `tuning_disclosure` and `appointment_confirmation` — parameterized templates. |
| **Progress tracking** | `generate_service_report` | Cross-table history pull (vehicles → tuning_logs → parts → appointments → invoices) with `send_progress` at each stage. |
| **Defensive tool design** | `schemas.py` + handlers | Real JSON Schema (`enum`, `additionalProperties: false`) + server-side `jsonschema.validate()` + role checks (technician can only log under their own `tech_id`). |
| **Transport** | `run_stdio.py` (dev) / `run_http.py` (deploy) | Local dev on stdio; multi-location chain on Streamable HTTP via Starlette + `StreamableHTTPSessionManager`. Same `create_server()` either way. |

### Memory & Retrieval concerns (Session 3 — this lab)

| Concern | Where | How to find it |
|---|---|---|
| **Short-term buffer + scratchpad** | `memory/short_term.py`, `memory/scratchpad.py` | Rolling buffer, pruned; scratchpad survives pruning |
| **Context window — 4 strategies** | `context_eval/{sliding_window,observation_masking,recursive_summarization,zone_pruning}.py` | Pure `prune(transcript, **cfg) -> transcript` |
| **Promote-or-drop routing** | `memory/router.py` → `MemoryRouter.route()` | Fires on overflow only → forget/episodic; never writes semantic; reasoning in `memory/logs/router.log` |
| **Consolidation layer** | `memory/consolidation.py` → `ConsolidationEngine.consolidate()` + `_supersede()` | Periodic pass, never at write time; versioned conflict resolution |
| **Vector database** | `rag/vector_store.py` | HNSW index + metadata payload store + pre-filter via metadata index |
| **Naive / Hybrid / Agentic RAG** | `rag/{naive_rag,hybrid_rag,agentic_rag}.py` | Each exposes `.answer(query)` |
| **Self-RAG verification** | `rag/verifier.py` → `SelfRAGVerifier.check()` | Applied to both RAG answers AND memory recall |
| **7 integration hooks** | `agent/client.py` → `run_turn()` | Labeled `HOOK 1..7` — visibly reuse existing loop |

---

## Part III: Benchmark Tables & Final Choices

### Table 1 — Context window management (15 points)

Benchmarked 4 strategies against a **frozen** suite of 10 synthetic long-context transcripts (~30k tokens each), where a critical aftermarket-radiator fact in turn 1 is buried under 25–34 turns of tool JSON noise.

| Strategy | Detail recalled | Avg input tokens/run | Avg output tokens/run | Avg latency |
|---|---|---|---|---|
| Sliding window (last 10 turns) | 1/10 | 10,547 | 289 | 2.4s |
| **Observation masking (keep last 3)** | **8/10** | **3,929** | **19** | **2.2s** |
| Recursive summarization (every 15 turns) | 10/10 | 7,699 | 104 | 4.1s |
| Zone-based pruning (4 zones) | 10/10 | 10,808 | 69 | 4.1s |

**Shipped:** Observation masking.

**Justification (from the table, not intuition):**
- Lowest cost by far: 3,929 input tokens (63% reduction vs sliding window) and 19 output tokens — zero LLM generation overhead.
- Lowest latency: 2.2s vs 4.1s for the two 10/10 strategies. On live mechanic calls where someone is waiting on the phone, this matters.
- 8/10 recall: The 2 failures (cases 7 and 9 in the frozen suite) happen specifically when the critical fact was buried *inside* an old tool JSON payload rather than the dialogue. In our real domain, mechanics state modifications explicitly in conversation; facts buried inside old tool payloads are rare.
- Why not Recursive/Zone? Both achieved 10/10 but at 4× the latency and (for Recursive) 5× the output tokens. The marginal 2 extra cases recovered didn't justify the live-call latency cost for our traffic mix.

**Test suite guardrail:** `context_eval/test_cases.py` was frozen after the first run; changing cases between runs invalidates the table.

### Table 2 — Retrieval Architectures (15 points)

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
---

## Part IV: Memory System Details

### Short-term buffer + scratchpad
- `memory/short_term.py`: rolling deque with `maxlen`. **Pruning never touches the scratchpad.**
- `memory/scratchpad.py`: active goal, sub-goals, working state. Kept as a separate block in the Gemini context.

### Promote-or-drop routing (forget/episodic only)
- `MemoryRouter.route(message)` fires on buffer overflow. Returns `EpisodicMemory` or `None` (forget).
- **Does NOT write to semantic memory** — only the periodic consolidation pass does.
- Every decision logged to `memory/logs/router.log` with the importance score and reason.

### Consolidation layer (periodic, separate)
- `ConsolidationEngine.consolidate()` runs every 10 turns (configurable).
- **Explicitly resolves conflicts:** detects contradictions between episodes for the same `(vehicle_id, client_id)` entity (e.g., `5W-30` vs `0W-20` oil spec), bumps version on the new fact, and deactivates the old one — **never silently overwrites**.
- Old versions are kept, dated, and flagged `active=False`. The grader can see both in `memory/storage/semantic.json`.

**Real conflict we resolve (demonstrated in demo section 11):**
- Episode A: "Vehicle 4's service manual specifies 5W-30 oil"
→ semantic v1 active=false (superseded, dated)
- Episode B: "Vehicle 4's manual updated — now specifies 0W-20 oil"
→ semantic v2 active=true


---

## Part V: Self-RAG-Style Verification

- `SelfRAGVerifier.check(query, sources, answer)` → `(supported: bool, critique: str)`.
- Two reflection dimensions: **relevant** (is the retrieval on-topic?) and **supported** (is the claim in the evidence?).
- Applied to **both** RAG answers and recalled memories — not just retrieval.
- **Visible consequence on failure:** answer prefixed with `[Low confidence — <critique>]`. The demo (section 12) shows both a pass and an explicit catch.

---

## Part VI: Demo Evidence

`agent/demo.py --auto` produces a 14-section transcript covering every required moment:

1. **Capability negotiation** with MCP server
2. **Baseline tool set** before authentication
3. **Authentication + `tools/list_changed`** notification
4. **Defensive tool design** (validation on cosmetic modification)
5. **Elicitation + sampling** on emissions-affecting modification
6. **Invoice creation with authorization check**
7. **Progress tracking** on service report generation
8. **Resources + prompts** verification
9. **Gemini reasoning loop** — real tool calls, grounded answer
10. **Memory: item survives promote-or-drop** — radiator note routed to episodic (see `memory/logs/router.log`)
11. **Consolidation: real contradiction resolved** — 5W-30 vs 0W-20 oil, versioned and dated
12. **Self-RAG: grounded pass vs unsupported catch** — low-confidence flag fires on out-of-corpus question
13. **Context management: all 4 strategies on frozen suite** — table printed
14. **Retrieval architectures: same question, 3 ways** — naive/hybrid/agentic answers compared

Run it: `python -m agent.demo --auto`

---

## Part VII: Setup & Run

```bash
# 1. Environment
python -m venv .venv
.venv\Scripts\activate                  # Windows
# source .venv/bin/activate             # macOS/Linux
python -m pip install -r requirements.txt

# 2. Secrets (NEVER commit .env — it's in .gitignore)
# Create .env with:
#   GEMINI_API_KEY=your_key_here

# 3. Run the MCP server (pick one transport)
python -m mcp_server.run_stdio          # local dev
python -m mcp_server.run_http           # deploy on http://localhost:8000/mcp

# 4. Run the demo (covers all concerns from both labs)
python -m agent.demo --auto

# 5. Build the vector index, then run evaluations
python -m rag.ingest
python -m context_eval.evaluate         # context window table (~5 min)
python -m rag.evaluation --architecture naive
python -m rag.evaluation --architecture hybrid
# Agentic RAG is run separately because the free-tier request limit is low.
