# Torque-Tune Platform — Code Map

## Backend

### `backend/api/` — HTTP doors (FastAPI routers)

| File | Responsibility |
|---|---|
| `agents.py` | Customer chat endpoints (tuning chat / rescue / build + status pollers) |
| `sourcing.py` | Graph 1 operator actions (start / supplier event / auto-step) |
| `warranty.py` | Graph 2 warranty dispute operator endpoints |
| `graphs.py` | Fleet-rescue provider webhook (Accept / Reject) |
| `hitl.py` | Approval queue (list / decide) |
| `tickets.py` | Failure tickets (list / resolve) |
| `runs.py` | Runs table + Story timeline |
| `tools.py` | Enable/disable MCP tools on the live server |
| `resources.py` | RAG document management (add / remove / re-ingest) |

### `backend/services/` — Business logic (no HTTP)

#### Customer-facing concierges

| File | Responsibility |
|---|---|
| `concierge_service.py` | Fleet-rescue chat facade (Graph 3) |
| `build_concierge.py` | Performance-build chat facade (Graph 1) |
| `warranty_concierge.py` | Warranty dispute chat facade (Graph 2) |

#### Graph bridges & adapters

| File | Responsibility |
|---|---|
| `graph_service.py` | Central registry: run / status / event dispatch |
| `sourcing_adapter.py` | Wraps `SourcingInstallGraph` in the 4-method contract |
| `warranty_adapter.py` | Wraps `Graph2Warranty` in the 4-method contract |

#### Live wiring

| File | Responsibility |
|---|---|
| `live_sourcing.py` | Simulated supplier client + LangChain chat wrapper |

#### Admin data services

| File | Responsibility |
|---|---|
| `hitl_service.py` | Approval queue management |
| `ticket_service.py` | Failure ticket management |
| `run_service.py` | Run history & status |
| `timeline_service.py` | Story timeline generation |
| `tool_registry_service.py` | MCP tool enable/disable |
| `resource_service.py` | RAG document ingestion |

#### Shared utilities

| File | Responsibility |
|---|---|
| `customer_service.py` | Client / vehicle verification |
| `agent_service.py` | Tuning-technician chat (Sessions 1–3 agent) |

### `backend/` — Core application

| File | Responsibility |
|---|---|
| `deps.py` | Single wiring point — builds the whole live stack once |
| `auth.py` | Passcode → in-memory bearer tokens |
| `main.py` | Router assembly + static frontend serving |

---

## Frontend

### `frontend/`

| File | Responsibility |
|---|---|
| `index.html` + `js/customer.js` | Customer console (3 chat agents) |
| `admin.html` + `js/admin.js` | Operations console (HITL / tickets / runs) |
| `js/api.js` | Fetch + token helpers |
| `css/style.css` | Shared styles |

---

## Adding a New Graph

When adding **Graph N**:

1. Create `services/<name>_adapter.py` to wrap the graph in the 4-method contract.
2. Create `services/<name>_concierge.py` for customer-facing chat, if needed.
3. Add `api/<name>.py` for operator endpoints.
4. Register the graph in `deps.py` and `graph_service._wf`.
5. Add a card in `admin.html` and, if customer-facing, in `index.html`.

**Shared infrastructure** such as HITL, tickets, runs, Story, and pollers does not need to be recreated for each graph.