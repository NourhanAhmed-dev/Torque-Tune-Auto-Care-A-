# Torque-Tune Auto Care — MCP Server + Memory + Planning Gate

> This project spans three labs on the same company, same repo, same database, same MCP server.
> Each layer imports from and builds on top of the previous.

---

## Part I: The Problems We Solve

### Session 1 — MCP Server
Technicians and front-desk staff need an LLM assistant that can look up clients, vehicles, appointments, tuning history, and log work — without raw database access. The genuine risk: emissions-affecting work (ECU remaps, decat) must never be logged complete without an explicit customer disclosure sign-off. That risk justifies every MCP protocol concern below.

### Session 3 — Memory & RAG
Once live usage started, two new problems appeared:
1. **Memory loss across sessions** → mechanics re-explain aftermarket modifications; wrong OEM parts get ordered.
2. **Knowledge buried in ungoverned documents** → 40-page binder of TSB/POL/PT docs; hallucinated torque specs = liability.

### Week 4 — Planning Gate (this lab)
**Problem we found on top of the existing system:** the MCP agent authenticates, elicits, and writes records — but *nothing decides* whether an emissions-affecting job may proceed before consequential writes. Today that decision is implicit in free-form LLM output, which can RELEASE a decat without disclosure evidence. This is real: a remap without signed customer disclosure is a regulatory violation, and our seeded SQLite + MCP session state give us ground truth to gate on.

**Who owns it:** a planning gate built on the forked toolkit (`planning_toolkit/`, forked from AmrSheta22/task_decomposition_and_planning) that runs BEFORE the memory/RAG agent executes a high-risk case. The memory/RAG code path (`run_turn`) is reused for execution only, never duplicated.

---

## Part II: Concern Map (Grrader Locator)

### MCP Server concerns (Session 1 — still live)

| Concern | Where |
|---|---|
| Capability negotiation | `mcp_server/server.py` → `list_tools()` |
| Notifications | `authenticate_technician` → `send_tool_list_changed()` |
| Elicitation | `log_tuning_modification` (emissions_affecting branch) |
| Sampling | `log_tuning_modification` → `session.create_message` |
| Resources / Prompts | `list_resources()`, `mcp_server/prompts.py` |
| Progress tracking | `generate_service_report` → `send_progress` |
| Defensive tool design | `schemas.py` + `jsonschema.validate` |
| Transport | `run_stdio.py` (dev) / `run_http.py` (deploy) |

### Memory & Retrieval concerns (Session 3)

| Concern | Where |
|---|---|
| Short-term buffer + scratchpad | `memory/short_term.py`, `memory/scratchpad.py` |
| 4 context strategies | `context_eval/{sliding_window,observation_masking,recursive_summarization,zone_pruning}.py` |
| Promote-or-drop routing | `memory/router.py` (forget/episodic only) |
| Consolidation layer | `memory/consolidation.py` (periodic, versioned conflict resolution) |
| Vector DB + RAG variants | `rag/{vector_store,naive_rag,hybrid_rag,agentic_rag}.py` |
| Self-RAG verification | `rag/verifier.py` (applies to RAG answers AND memory recall) |
| 7 integration hooks | `agent/client.py` → `run_turn()` (labeled HOOK 1..7) |

### Planning concerns (Week 4) — every concern locatable without reading the whole file

| Concern | Where |
|---|---|
| DAG construction + cycle check | `planning_toolkit/planning_lab/models.py` → `Plan.validate_dag` (NetworkX) |
| Decomposition-first vs dynamic branch | `planning_toolkit/planning_lab/cli.py` (`--mode dag` vs `--mode dynamic`) |
| Routing PS vs ToT vs LATS | `planning_toolkit/planning_lab/algorithms/router.py` → `route_subtask` |
| Grounded environment (real feedback) | `planning/torque_tune_environment.py` (SQLite evidence + compliance rules) |
| Self-Refine critique | `planning_toolkit/planning_lab/algorithms/self_refine.py` |
| Reflexion critique + memory | `planning_toolkit/planning_lab/algorithms/reflexion.py` |

---

## Part III: Benchmark Tables (frozen suites, shipped choices)

### Table 1 — Context window (Session 3)
10 synthetic long-context transcripts (~30k tokens each); critical aftermarket-radiator fact buried under 25–34 turns of tool JSON noise.

| Strategy | Detail recalled | Avg input tokens | Avg latency |
|---|---|---|---|
| Sliding window (last 10) | 1/10 | 10,547 | 2.4s |
| **Observation masking (last 3)** | **8/10** | **3,929** | **2.2s** |
| Recursive summarization | 10/10 | 7,699 | 4.1s |
| Zone-based pruning | 10/10 | 10,808 | 4.1s |

**Shipped: Observation masking** — 63% token reduction vs sliding window, 2.2s latency, and the 2 misses only occur when the fact is buried inside old tool payloads (rare in our real dialogue-driven domain).

### Table 2 — Retrieval architectures (Session 3)
6 fixed evaluation questions.

| Architecture | Completed | Accuracy | Tokens/query | Latency |
|---|---|---|---|---|
| **Naive RAG** | 6/6 | **81.12%** | **1460.3** | 5.406s |
| Hybrid RAG | 6/6 | 81.12% | 1478.8 | 5.321s |
| Agentic RAG | 2/6 | 100%* | 1397.5* | 13.801s* |

\* Excluded — free-tier rate limit prevented completing all 6 questions.

**Shipped: Naive RAG** — same accuracy as Hybrid at fewer tokens; Hybrid's 0.085s latency edge does not justify the added complexity.

### Table 3 — Planning methods (Week 4)
Frozen 7-case suite; gemini-3.1-flash-lite; every method scored by the same grounded validator (real SQLite evidence + compliance rules).

| Method | Grounded success | Env self-success | Avg calls | Avg tokens | Avg latency s | Est cost/run |
|---|---|---|---|---|---|---|
| **lats** | **6/7** | **6/7** | 2.7 | 1067 | 13.2 | **$0.0005** |
| plan_and_solve | 4/7 | 4/7 | 1.0 | 1040 | 10.7 | $0.0005 |
| decomposition_first | 4/7 | 3/7 | 7.0 | 3130 | 36.7 | $0.0016 |
| reflexion | 4/7 | 3/7 | 3.0 | 1407 | 15.1 | $0.0007 |
| dynamic | 2/7 | 2/7 | 6.0 | 2892 | 30.0 | $0.0014 |
| tree_of_thoughts | 2/7 | 3/7 | 9.0 | 4866 | 59.1 | $0.0024 |
| lats_ungrounded | 4/7 | **7/7** | 2.0 | 669 | 11.5 | $0.0003 |
| reflexion_ungrounded | 2/7 | **7/7** | 1.0 | 417 | 8.0 | $0.0002 |

**Method choice per sub-task (driven by these numbers):**

- **Final release decision → LATS + grounded env** (6/7 at $0.0005). The ungrounded row proves the guardrail: LATS ungrounded self-approves 7/7 yet scores only 4/7 grounded — external SQLite/MCP validation is precisely what earns the gap.
- **Sequential verification → Plan-and-Solve** (4/7 at 1 call, $0.0005) — same accuracy as decomposition-first at 1/7 the cost.
- **Decision comparison → Tree-of-Thoughts** only when the deliverable is an explicit comparison; honest note: wave-1 numbers (2/7, $0.0024) do not justify general use.
- **Pressure cases → Reflexion** (4/7, carries reflections across trials; ungrounded variant self-approves 7/7 while scoring 2/7 grounded).
- **Top level → Decomposition-first** for fully mechanical boards; **dynamic** when mid-plan surprises are expected (divergence visible in transcript).

---

## Part IV: Demo Transcript

`python -m agent.planning_demo` runs the Week-4 guard in front of the existing memory/RAG agent. The transcript shows:

1. **High-risk detection** on the catalytic-converter-delete request.
2. **Decomposition** into 4 batches: `[['t1', 't2'], ['t3'], ['t4']]`.
3. **Routing per sub-task** via `route_subtask`: verification sub-tasks → Plan-and-Solve; comparison sub-task → Tree-of-Thoughts; final decision → LATS.
4. **Reflexion** over 3 trials with grounded SQLite feedback (vehicle 3 ∈ client 2, technician 2 exists, appointment 3 matches).
5. **Guard note injected** into the agent's system prompt.
6. **TorqueTuneAgent executes** with the guard respected: HOLD/ESCALATE decision honored, no `log_tuning_modification` or `create_invoice` on emissions-affecting work without disclosure.

`python -m planning_toolkit.planning_lab.cli --mode <mode>` runs every planning algorithm with the real grounded environment. Artifacts saved under `planning_toolkit/artifacts/run-*.json` (Self-Refine `critique` + `grounded_issues` visible in dag-mode artifacts; LATS tree with `reflections` per failed branch; Reflexion memory across trials).

---

## Part V: Setup & Run

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt

# .env (gitignored)
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
MCP_TRANSPORT=stdio / http
MCP_SERVER_URL=http://xxxxxx:8000/mcp

# MCP server
python -m mcp_server.run_stdio      # dev
python -m mcp_server.run_http       # deploy

# Existing demos (Sessions 1 + 3)
python -m agent.demo --auto

# Week 4: planning gate + memory/RAG agent
python -m agent.planning_demo

# Week 4: run individual planning methods with real grounded environment
python -m planning_toolkit.planning_lab.cli "<goal>" --mode dag   --technician-authenticated
python -m planning_toolkit.planning_lab.cli "<goal>" --mode dynamic --technician-authenticated
python -m planning_toolkit.planning_lab.cli "<goal>" --mode ps
python -m planning_toolkit.planning_lab.cli "<goal>" --mode tot
python -m planning_toolkit.planning_lab.cli "<goal>" --mode lats --technician-authenticated
python -m planning_toolkit.planning_lab.cli "<goal>" --mode reflexion --technician-authenticated

# Week 4: frozen evaluation suite
python -m planning_eval.evaluate --resume          # runs 8 methods × 7 cases, resumes partial runs
python -m planning_eval.evaluate --table-only      # rebuilds comparison table from artifacts, 0 API calls