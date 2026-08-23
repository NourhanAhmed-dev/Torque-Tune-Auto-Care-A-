from __future__ import annotations
 
import json
import re
import sqlite3
from unittest.mock import MagicMock, call
 
import pytest
 
from state_graph.failure_node import FailureNode
from state_graph.hitl_node import HitlNode
from state_graph.graphs.graph1_multi_supplier import nodes as nodes_module
from state_graph.graphs.graph1_multi_supplier.workflow import SourcingInstallGraph
from state_graph.graphs.graph1_multi_supplier.nodes import (
    BuildConfigurationNode,
    CompatibilityRagNode,
    PriceCheckNode,
    SubstituteCheckNode,
    SupplierOrderNode,
    TaskDecompositionNode,
)
 
 
# ---------------------------------------------------------------------------
# Stand-in for the real "run paused, ticket created" control-flow exception.
# TicketManager.capture_failure() is documented as "always raises"; we don't
# have its real exception class, so we fake one with the same role.
# ---------------------------------------------------------------------------
class FakeFailurePaused(Exception):
    def __init__(self, *, run_id: str, node_name: str, error: Exception):
        super().__init__(f"run {run_id} paused at {node_name}: {error}")
        self.run_id = run_id
        self.node_name = node_name
        self.error = error
 
 
# ---------------------------------------------------------------------------
# Fakes for external I/O
# ---------------------------------------------------------------------------
class FakeSupplierClient:
    """In-memory stand-in for the real supplier HTTP client.
 
    `responses` maps supplier -> either:
      - a dict response (always returned), or
      - a callable(part_ids) -> dict, or
      - an exception instance/class to always raise (simulates a supplier
        whose API never responds usefully, for the ticket-escalation test).
    """
 
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[tuple[str, list[int]]] = []
 
    def place_order(self, supplier: str, part_ids: list[int]) -> dict:
        self.calls.append((supplier, list(part_ids)))
        behavior = self.responses[supplier]
        if isinstance(behavior, Exception):
            raise behavior
        if isinstance(behavior, type) and issubclass(behavior, Exception):
            raise behavior(f"{supplier} timed out")
        if callable(behavior):
            return behavior(part_ids)
        return behavior
 
 
class FakeRagAnswer:
    def __init__(self, answer: str):
        self.answer = answer
 
 
class FakeAgenticRAG:
    """Returns canned compatibility/torque specs per part_id, matching the
    JSON contract CompatibilityRagNode._parse_answer expects."""
 
    def __init__(self, specs_by_part_id: dict[int, dict]):
        self.specs_by_part_id = specs_by_part_id
        self.queries: list[str] = []
 
    def answer(self, query: str) -> FakeRagAnswer:
        self.queries.append(query)
        match = re.search(r"part_id=(\d+)", query)
        part_id = int(match.group(1))
        return FakeRagAnswer(json.dumps(self.specs_by_part_id[part_id]))
 
 
async def _fake_dynamic_decomposition(*, goal, llm, max_steps, executor):
    """Deterministic stand-in for the real LLM-driven planner.
 
    Offers every part_id mentioned in the goal text, in ascending order,
    for up to two passes (enough for a single level of install_after
    dependency to resolve). The REAL validation logic lives in
    TaskDecompositionNode._install_step_executor (delivered/cancelled/
    dependency checks) -- this fake just proposes candidates, it doesn't
    decide what gets scheduled.
    """
    part_ids = sorted(int(m) for m in re.findall(r"part_id=(\d+)", goal))
    for _ in range(2):
        for part_id in part_ids:
            executor(f"install part {part_id}")
 
 
# ---------------------------------------------------------------------------
# DB fixture for BuildConfigurationNode
# ---------------------------------------------------------------------------
@pytest.fixture
def build_db_path(tmp_path) -> str:
    db_path = str(tmp_path / "sourcing.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE build_part_requirements (
                part_id INTEGER PRIMARY KEY,
                part_name TEXT,
                supplier TEXT,
                price REAL,
                quantity INTEGER,
                preset_key TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO build_part_requirements VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "Turbomax Turbo Kit", "TurboWorks", 2500.0, 1, "turbo_kit_stage2"),
                (2, "ColdFlow Intercooler", "TurboWorks", 800.0, 1, "turbo_kit_stage2"),
                (3, "ECU Tune Module", "ChipTuners", 600.0, 1, "turbo_kit_stage2"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path
 
 
# ---------------------------------------------------------------------------
# RAG specs used by the scenario:
#   - intercooler (2) and ECU tune (3) must be installed AFTER the turbo
#     kit (1) -- this is what makes the dependency-ordering behavior of
#     TaskDecompositionNode observable in the test.
# ---------------------------------------------------------------------------
RAG_SPECS = {
    1: {
        "compatibility_notes": "Requires new turbo-to-manifold gasket kit.",
        "torque_spec": "35 Nm",
        "install_after": [],
        "special_instructions": "",
    },
    2: {
        "compatibility_notes": "Fits behind the front bumper support.",
        "torque_spec": "18 Nm",
        "install_after": [1],
        "special_instructions": "",
    },
    3: {
        "compatibility_notes": "Flash only after turbo hardware is installed.",
        "torque_spec": "n/a",
        "install_after": [1],
        "special_instructions": "Flash via OBD-II port.",
    },
}
 
PARTS_CATALOG = {
    1: {"name": "Turbomax Turbo Kit"},
    2: {"name": "ColdFlow Intercooler"},
    3: {"name": "ECU Tune Module"},
}
 
 
@pytest.fixture
def graph_and_doubles(build_db_path, monkeypatch):
    """Builds SourcingInstallGraph wired to REAL node classes, with fakes
    only at the true external-I/O boundaries."""
    monkeypatch.setattr(nodes_module, "dynamic_decomposition", _fake_dynamic_decomposition)
 
    ticket_manager = MagicMock(name="TicketManager")
    ticket_manager.capture_failure.side_effect = (
        lambda *, run_id, node_name, state, error: (_ for _ in ()).throw(
            FakeFailurePaused(run_id=run_id, node_name=node_name, error=error)
        )
    )
    failure = FailureNode(manager=ticket_manager)
 
    hitl_manager = MagicMock(name="HitlManager")
    hitl_manager.require_decision.return_value = None
    hitl = HitlNode(manager=hitl_manager)
 
    supplier_client = FakeSupplierClient(
        responses={
            "TurboWorks": lambda part_ids: {
                "order_id": 101,
                "quoted_price": 2500.0 if part_ids == [1] else 3300.0,
            },
            "ChipTuners": lambda part_ids: {"order_id": 102, "quoted_price": 600.0},
        }
    )
 
    agentic_rag = FakeAgenticRAG(RAG_SPECS)
    compat_rag = CompatibilityRagNode(agentic_rag=agentic_rag, parts_catalog=PARTS_CATALOG)
 
    build_config_node = BuildConfigurationNode(failure=failure, db_path=build_db_path)
    order_node = SupplierOrderNode(client=supplier_client, failure=failure)
    price_check_node = PriceCheckNode(hitl=hitl, threshold_pct=0.10)
    substitute_check_node = SubstituteCheckNode(hitl=hitl)
    decomposition_node = TaskDecompositionNode(
        llm=MagicMock(name="unused_llm"), rag=compat_rag, failure=failure, max_steps=8
    )
 
    checkpoint_manager = MagicMock(name="CheckpointManager")
 
    graph = SourcingInstallGraph(
        order_node=order_node,
        decomposition_node=decomposition_node,
        price_check_node=price_check_node,
        substitute_check_node=substitute_check_node,
        build_config_node=build_config_node,
        checkpoint_manager=checkpoint_manager,
    )
 
    return {
        "graph": graph,
        "supplier_client": supplier_client,
        "ticket_manager": ticket_manager,
        "hitl_manager": hitl_manager,
        "checkpoint_manager": checkpoint_manager,
        "failure": failure,
    }
 
 
def _sequence_part_ids(state) -> list[int]:
    return [step["part_id"] for step in state["installation_sequence"]]
 
 
# ---------------------------------------------------------------------------
# Full scenario
# ---------------------------------------------------------------------------
def test_full_multi_supplier_build_scenario(graph_and_doubles):
    graph = graph_and_doubles["graph"]
    hitl_manager = graph_and_doubles["hitl_manager"]
    run_id = "run-turbo-001"
 
    # 1) Customer places the preset build. Real DB read groups parts by
    # supplier; real supplier client "places" two orders.
    state = graph.start_from_preset(
        run_id=run_id, state={}, preset="turbo_kit_stage2"
    )
 
    assert {p["part_id"] for p in state["parts_required"]} == {1, 2, 3}
    assert set(state["orders"].keys()) == {101, 102}
    assert state["orders"][101]["supplier"] == "TurboWorks"
    assert state["orders"][101]["quoted_price"] == 3300.0
    assert state["orders"][102]["supplier"] == "ChipTuners"
    assert state["orders"][102]["quoted_price"] == 600.0
    # no orchestration-only keys leak into the public state
    assert not {"entry", "preset", "orders_to_place", "event", "hitl_decision"} & state.keys()
 
    # 2) Turbo kit (part 1) delivered -> re-plan. It has no dependencies,
    # so it's the only thing schedulable.
    state = graph.on_supplier_event(
        run_id=run_id,
        event={"event_type": "delivery_confirmed", "part_id": 1},
        state=state,
    )
    assert state["delivered_part_ids"] == [1]
    assert _sequence_part_ids(state) == [1]
 
    # 3) Intercooler (part 2) delivered -> re-plan. It depends on part 1
    # (RAG-sourced install_after), which is already scheduled, so it's
    # appended after it.
    state = graph.on_supplier_event(
        run_id=run_id,
        event={"event_type": "delivery_confirmed", "part_id": 2},
        state=state,
    )
    assert state["delivered_part_ids"] == [1, 2]
    assert _sequence_part_ids(state) == [1, 2]
 
    # 4) ChipTuners invoices the ECU order at a price 15% above quote --
    # over the 10% threshold -> HITL required. Graph does NOT halt: part 3
    # simply stays undelivered/unscheduled until a human decides.
    state = graph.on_supplier_event(
        run_id=run_id,
        event={"event_type": "price_changed", "order_id": 102, "final_price": 690.0},
        state=state,
    )
    assert state["orders"][102]["final_price"] == 690.0
    assert _sequence_part_ids(state) == [1, 2]  # unchanged, part 3 still unresolved
    hitl_manager.require_decision.assert_called_once()
    _, first_hitl_kwargs = hitl_manager.require_decision.call_args
    assert first_hitl_kwargs["action"]["type"] == "price_deviation"
    assert first_hitl_kwargs["action"]["order_id"] == 102
    assert first_hitl_kwargs["action"]["deviation_pct"] == 15.0
 
    # 5) Human approves the price deviation -> order confirmed.
    state = graph.on_hitl_decision(
        run_id=run_id,
        decision={
            "action": {"type": "price_deviation", "order_id": 102},
            "approved": True,
        },
        state=state,
    )
    assert state["orders"][102]["status"] == "confirmed"
 
    # 6) ChipTuners can't source the exact ECU module and offers a
    # substitute that voids the powertrain warranty -> HITL required again.
    state = graph.on_supplier_event(
        run_id=run_id,
        event={
            "event_type": "substitute_offered",
            "order_id": 102,
            "part_id": 3,
            "substitute": {
                "substitute_part": "ECU-Tune-Lite",
                "warranty_impact": "voids powertrain warranty",
            },
        },
        state=state,
    )
    assert "applied_substitutes" not in state or 3 not in state.get("applied_substitutes", {})
    assert hitl_manager.require_decision.call_count == 2
    _, second_hitl_kwargs = hitl_manager.require_decision.call_args
    assert second_hitl_kwargs["action"]["type"] == "substitute_offered"
    assert second_hitl_kwargs["action"]["warranty_impact"] == "voids powertrain warranty"
 
    # 7) Human rejects the substitute (warranty matters more than
    # finishing the build) -> part 3 permanently cancelled, never
    # scheduled, even though it was never explicitly "delivered".
    state = graph.on_hitl_decision(
        run_id=run_id,
        decision={
            "action": {
                "type": "substitute_offered",
                "order_id": 102,
                "part_id": 3,
                "substitute_part": "ECU-Tune-Lite",
            },
            "approved": False,
        },
        state=state,
    )
    assert state["cancelled_part_ids"] == [3]
    assert _sequence_part_ids(state) == [1, 2]  # final sequence: turbo kit, then intercooler
 

# ---------------------------------------------------------------------------
# Ticket escalation: supplier API times out on every attempt
# ---------------------------------------------------------------------------
def test_supplier_timeout_escalates_to_ticket_after_retries(graph_and_doubles):
    graph = graph_and_doubles["graph"]
    supplier_client = graph_and_doubles["supplier_client"]
    ticket_manager = graph_and_doubles["ticket_manager"]
    checkpoint_manager = graph_and_doubles["checkpoint_manager"]
 
    # GhostParts always times out -- no successful response is ever possible.
    supplier_client.responses["GhostParts"] = TimeoutError
 
    run_id = "run-ghost-001"
    with pytest.raises(FakeFailurePaused) as exc_info:
        graph.start(
            run_id=run_id,
            state={},
            orders_to_place=[{"supplier": "GhostParts", "part_ids": [9]}],
        )
 
    assert exc_info.value.node_name == "SupplierOrderNode"
    assert isinstance(exc_info.value.error, TimeoutError)
 
    # SupplierOrderNode retries MAX_ATTEMPTS (3) times before giving up.
    ghostparts_calls = [c for c in supplier_client.calls if c[0] == "GhostParts"]
    assert len(ghostparts_calls) == SupplierOrderNode.MAX_ATTEMPTS
 
    # Escalated to a ticket exactly once, not retried indefinitely.
    ticket_manager.capture_failure.assert_called_once()
    _, capture_kwargs = ticket_manager.capture_failure.call_args
    assert capture_kwargs["run_id"] == run_id
    assert capture_kwargs["node_name"] == "SupplierOrderNode"
 
    # The run never reaches "completed" -- it's paused pending the ticket.
    checkpoint_manager.mark_run_finished.assert_not_called()
 