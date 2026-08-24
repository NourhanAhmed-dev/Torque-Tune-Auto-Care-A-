"""Shared live stack — built ONCE, used by every service."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from state_graph import db
from state_graph.live_bridge import build_live_stack
from state_graph.failure_node import FailureNode
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.hitl.hitl_manager import HitlManager
from state_graph.hitl.approval_service import ApprovalService
from state_graph.tickets.ticket_manager import TicketManager
from state_graph.tickets.ticket_service import TicketService

# Graph 3 — fleet rescue
from state_graph.graphs.graph3_fleet_rescue.nodes import (
    FleetRescueNodes, FleetAuthorizationNode)
from state_graph.graphs.graph3_fleet_rescue.workflow import FleetRescueWorkflow

# Graph 1 — multi-supplier sourcing
from state_graph.graphs.graph1_multi_supplier.workflow import SourcingInstallGraph
from state_graph.graphs.graph1_multi_supplier.nodes import (
    BuildConfigurationNode, CompatibilityRagNode, PriceCheckNode,
    SubstituteCheckNode, SupplierOrderNode, TaskDecompositionNode)
from state_graph.graphs.graph1_multi_supplier.repository import SourcingRepository
from state_graph.hitl_node import HitlNode

# ▶ Graph 2 — warranty dispute (note: folder name is graph2_dispute_resolution)
from state_graph.graphs.graph2_dispute_resolution.workflow import Graph2Warranty

from .services.sourcing_adapter import SourcingAdapter
from .services.warranty_adapter import WarrantyAdapter  # ▶
from rag.naive_rag import NaiveRAG
from .services.live_sourcing import LiveChatModel, LiveSupplierClient, ResilientAgenticRAG

ROOT = Path(__file__).resolve().parents[2]
SOURCING_DB = str(ROOT / "db" / "redline.db")


@dataclass
class Stack:
    mcp: object
    llm: object
    rag: object
    checkpoints: CheckpointManager
    hitl: HitlManager
    tickets: TicketManager
    rescue_wf: FleetRescueWorkflow
    sourcing_wf: SourcingAdapter
    warranty_wf: object     # ▶ add this line


_stack: Stack | None = None


def get_stack() -> Stack:
    global _stack
    if _stack is None:
        mcp, llm, rag = build_live_stack()

        cp = CheckpointManager(graph_type="fleet_rescue")
        tm = TicketManager(checkpoints=cp, tickets=TicketService())
        hm = HitlManager(checkpoints=cp, approvals=ApprovalService())

        wf = FleetRescueWorkflow(
            nodes=FleetRescueNodes(failure_node=FailureNode(manager=tm),
                                   fleet_auth_node=FleetAuthorizationNode(manager=hm),
                                   llm_client=llm, mcp_client=mcp, rag_retriever=rag),
            checkpoints=cp, hitl_manager=hm, ticket_manager=tm)

        # ---- Graph 1: sourcing ----
        with sqlite3.connect(SOURCING_DB) as c:
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("INSERT OR IGNORE INTO tuning_logs "
                      "(log_id, status, category, description, vehicle_id, tech_id) "
                      "VALUES (999, 'completed', 'build', 'sourcing demo seed', 1, 1)")
            for pid, name in ((101, 'Stage 2 Turbocharger Kit'),
                              (102, 'Front-Mount Intercooler Kit'),
                              (103, 'Stage 2 ECU Tune'),
                              (104, '3-Inch High-Flow Downpipe'),
                              (105, '1000cc Fuel Injectors (Set of 4)'),
                              (106, 'Electronic Boost Controller')):
                c.execute("INSERT OR IGNORE INTO parts_catalog (part_id, log_id, part_name) "
                          "VALUES (?, 999, ?)", (pid, name))
            c.execute("PRAGMA foreign_keys = ON")

        repo = SourcingRepository(SOURCING_DB)
        failure1 = FailureNode(manager=tm)
        hitl_node = HitlNode(manager=hm)
        client = LiveSupplierClient(SOURCING_DB)
        with sqlite3.connect(SOURCING_DB) as c:
            c.row_factory = sqlite3.Row
            catalog = {r["part_id"]: {"name": r["part_name"]} for r in c.execute(
                "SELECT DISTINCT part_id, part_name FROM build_part_requirements")}
        compat = CompatibilityRagNode(
             agentic_rag=NaiveRAG(), 
            parts_catalog=catalog
            )
        decomp = TaskDecompositionNode(llm=LiveChatModel(llm=llm), rag=compat,
                                       failure=failure1, repo=repo, max_steps=1)
        sourcing_wf = SourcingAdapter(
            SourcingInstallGraph(
                order_node=SupplierOrderNode(client=client, failure=failure1, repo=repo),
                decomposition_node=decomp,
                price_check_node=PriceCheckNode(hitl=hitl_node, repo=repo),
                substitute_check_node=SubstituteCheckNode(hitl=hitl_node, repo=repo),
                build_config_node=BuildConfigurationNode(failure=failure1,
                                                         db_path=SOURCING_DB),
                repo=repo,
                checkpoint_manager=CheckpointManager(graph_type="graph1_multi_supplier")),
            checkpoints=CheckpointManager(graph_type="graph1_multi_supplier"),
            hitl=hm, tickets=tm)

        # ▶ Graph 2: warranty dispute (separate checkpoint/manager set)
        cp2 = CheckpointManager(graph_type="warranty_dispute")
        tm2 = TicketManager(checkpoints=cp2, tickets=TicketService())
        hm2 = HitlManager(checkpoints=cp2, approvals=ApprovalService())
        warranty_wf = WarrantyAdapter(
            Graph2Warranty(checkpoint_manager=cp2, ticket_manager=tm2,
                           hitl_manager=hm2,
                           rag=NaiveRAG()),
            checkpoints=cp2, hitl=hm2, tickets=tm2)

        with db.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS tool_overrides (
                tool_name TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

        _stack = Stack(mcp=mcp, llm=llm, rag=rag, checkpoints=cp,
                       hitl=hm, tickets=tm,
                       rescue_wf=wf, sourcing_wf=sourcing_wf,
                       warranty_wf=warranty_wf)   # ▶
    return _stack


def peek_stack() -> Stack | None:
    return _stack