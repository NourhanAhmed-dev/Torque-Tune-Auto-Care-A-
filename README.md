# Redline Tuning Garage — MCP Server

## The problem
Redline is a performance/tuning garage chain. Front-desk staff and
technicians both want an LLM assistant that can look up clients, vehicles,
appointments, and tuning history, and let technicians log work and invoice
clients — without raw database access. The catch: some tuning work
(ECU remaps, catalytic converter/DPF removal) can void a vehicle's emissions
warranty and affect road-legal compliance. That work must never be logged as
"done" without an explicit technician sign-off confirming the client was
told. That's the genuine risk this server is built around, and it's what
justifies every protocol concern below — not one of them is decorative.

## Database
See `db/schema.sql`, `db/seed.sql`, and the ERD for the full schema
(clients, vehicles, technicians, appointments, tuning_logs, parts_catalog,
invoices). We extended `tuning_logs` with two columns beyond the original
ERD — `category` (`cosmetic` / `performance` / `emissions_affecting`) and
`description` — because the elicitation gate and the sampling call both need
something to reason about; a bare `status` field wasn't enough to tell a
harmless mod from a risky one.

## How each protocol concern shows up

| Concern | Where | Why it's genuine |
|---|---|---|
| **Capability negotiation** | `mcp_server/server.py` → `list_tools()` | Checks the client's declared `elicitation` capability (captured at `initialize`). A client that can't elicit never sees `log_tuning_modification` — it gets `flag_tuning_modification_for_review` instead, which just records the request for a human instead of silently completing or silently refusing it. |
| **Notifications** | `_handle_authenticate_technician` | A session starts as `front_desk` (read-only + `authenticate_technician`). Once a technician authenticates, the server calls `session.send_tool_list_changed()` — write tools appear without a reconnect. |
| **Elicitation** | `_handle_log_tuning_modification` | For `category == "emissions_affecting"`, the server calls `session.elicit(...)` mid-call and pauses for an explicit technician confirmation before marking the log `complete`. A decline leaves it `awaiting_signoff`. Cosmetic/performance mods skip this entirely. |
| **Sampling** | `_handle_log_tuning_modification` | Before eliciting, the server asks the *client's* model (`session.create_message(...)`) to draft a one-sentence risk summary for that specific modification, instead of a hardcoded string — falls back to a static sentence if the client didn't declare sampling support. |
| **Resources** | `list_resources()` / `read_resource()` | The emissions/warranty policy (`policy.md`) is a static document exposed via `resources/read`, not wrapped in a tool — the model reads it once and reasons over it. |
| **Prompts** | `mcp_server/prompts.py` | `tuning_disclosure` and `appointment_confirmation` are parameterized templates a host can surface as canned starting points. |
| **Progress tracking** | `_handle_generate_service_report` | Pulls a client's full cross-table history (vehicles → tuning logs → parts → appointments → invoices) and reports progress at each stage via `send_progress_notification`, instead of leaving the client blocked. |
| **Defensive tool design** | `_handle_create_invoice`, `_handle_log_tuning_modification` | Real JSON Schema constraints (`exclusiveMinimum`, `enum`, `additionalProperties: false`) in `schemas.py`, re-validated server-side with `jsonschema.validate()` independent of the client's claims, plus handler-level checks the schema can't express: the client/vehicle must actually exist, and a technician can only log work under their **own** authenticated `tech_id` — not whatever integer the model sends. |
| **Transport** | `run_stdio.py` (dev) / `run_http.py` (deployment) | Local development runs on stdio. A multi-location chain needs several front-desk/technician clients reaching one server over the network, so deployment moves to Streamable HTTP (`mcp_server/run_http.py`, Starlette + `StreamableHTTPSessionManager`) — same `create_server()` either way, only the transport changes. |

## Read-only vs. write tools

| Tool | Access | Notes |
|---|---|---|
| `get_client`, `get_vehicle`, `list_client_vehicles`, `list_appointments`, `get_invoice`, `list_tuning_logs` | Read-only, all sessions | No auth required |
| `authenticate_technician` | Read-only (auth check) | Unlocks the tools below via `tools/list_changed` |
| `generate_service_report` | Read-only | Long-running; progress-tracked |
| `create_appointment`, `mark_tuning_complete` | Write, technician-only | Handler checks authenticated role |
| `create_invoice` | Write, technician-only | Schema + existence + role checks |
| `log_tuning_modification` | Write, technician-only, **elicitation-gated** for `emissions_affecting` | Only offered if the client declared elicitation support |
| `flag_tuning_modification_for_review` | Write (log-only), technician-only | Fallback offered instead of `log_tuning_modification` when the client can't elicit |

## What happens if a client lacks a capability
- **No elicitation support:** `log_tuning_modification` is never listed; the
  client only ever sees `flag_tuning_modification_for_review`, which records
  the modification as `awaiting_signoff` for manual follow-up rather than
  performing or refusing it silently.
- **No sampling support:** the emissions-risk summary falls back to a static,
  pre-written sentence instead of a model-drafted one — elicitation still
  fires normally.

## Running it
```bash
pip install -r requirements.txt
python db/init_db.py            # builds db/redline.db from schema.sql + seed.sql
python -m agent.client           # full-featured demo client
python -m agent.client --limited # demo client without elicitation/sampling
python -m mcp_server.run_http    # Streamable HTTP deployment, http://localhost:8000/mcp
```
Demo transcripts of both runs are in `demo/`.
