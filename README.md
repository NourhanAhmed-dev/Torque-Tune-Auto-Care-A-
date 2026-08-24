# Torque-Tune Auto Care

Torque-Tune is an automotive service platform that combines an MCP server, AI agents, memory/RAG, planning, and state-graph workflows behind a usable customer and operations interface.

## Problems We Solve

### 1. MCP Server
Technicians need an AI assistant that can safely access clients, vehicles, appointments, tuning history, and service records without direct database access.

High-risk emissions-related work is protected by MCP elicitation/sampling and explicit customer disclosure before consequential records can be completed.

### 2. Memory & RAG
The agent needs to:
- remember important vehicle modifications across sessions
- retrieve trusted technical information from service documents
- reduce hallucinations around parts, procedures, and specifications

### 3. Planning Gate
Before the memory/RAG agent executes a high-risk request, the planning layer decides whether the request can proceed.

The planning gate uses task decomposition, planning-method routing, grounded SQLite evidence, and reflection to produce a guarded decision such as **PROCEED**, **HOLD**, or **ESCALATE**.

### 4. State-Graph Workflows

The final platform contains three operational workflows:

- **Graph 1 — Multi-Supplier Build:** tracks required parts, supplier events, cancellations, and installation ordering. Uses **task decomposition** to break the build into required parts/tasks and **RAG** for compatibility and technical information.

- **Graph 2 — Warranty Dispute:** handles warranty/contract checks, authorization, and human escalation when required. Uses **RAG** for warranty and contract information and **constrained ReAct** with whitelisted MCP tools for controlled actions.

- **Graph 3 — Fleet Rescue:** handles roadside rescue from request through provider selection, approval, external waiting, repair, and completion. Uses **RAG** for contract/authorization information and **constrained ReAct** over whitelisted MCP tools for provider search and controlled actions.

All graphs share checkpointing, HITL approvals, failure tickets, run tracking, and timeline/history.

## Fleet Rescue Workflow

```text
REQUESTED
   ↓
VALIDATING
   ↓
SERVICE_ASSESSMENT
   ↓
AUTHORIZATION_CHECK
   ├── invalid/rejected → CANCELLED
   └── approval needed → WAITING_FOR_APPROVAL (HITL)
                              ↓
                       PROVIDER_SEARCH
                              ↓
                   WAITING_FOR_PROVIDER
                       ├── rejected → PROVIDER_SEARCH
                       └── accepted
                              ↓
                     RESCUE_IN_PROGRESS
                              ↓
                          COMPLETED
```

## Final Platform

### Customer Console
A real end user can switch between the live agents available in the platform and chat with the one they need.

### Operations / Admin Console
The admin console provides shared visibility into:
- agents and MCP tools
- HITL approval requests
- failure tickets
- state-graph runs and timelines
- RAG resources

MCP tools can be enabled or disabled at runtime, and RAG resources can be managed from the platform.

## Architecture

```text
Frontend
├── Customer Console
└── Admin Console
        ↓
FastAPI API
        ↓
Services
├── MCP / Agent
├── Memory & RAG
├── Planning Gate
├── Graph 1 Adapter
├── Graph 2 Adapter
├── Graph 3 Concierge
└── Shared HITL / Tickets / Runs / Timeline
        ↓
MCP Server + SQLite + RAG
```

`backend/deps.py` is the main wiring point, while `graph_service.py` provides the common graph run/status/event interface.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Create `.env`:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash
MCP_TRANSPORT=stdio / http
MCP_SERVER_URL=http://localhost:8000/mcp
```

## Run

### MCP Server

```bash
python -m mcp_server.run_stdio
```

### Platform

Run the FastAPI application using the project's configured entry point, then open the customer or admin console in the browser.

### Planning Gate Demo

```bash
python -m agent.planning_demo
```

## Docker

Docker packages the application and its dependencies into a reproducible container so the platform can run without manually recreating the Python environment.

The repository includes Docker configuration for containerized deployment.
