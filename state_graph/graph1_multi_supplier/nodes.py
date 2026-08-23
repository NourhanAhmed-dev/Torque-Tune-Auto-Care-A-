
from __future__ import annotations

"""
sourcing_nodes_with_persistence.py

Same nodes as the original file, with `self.repo: SourcingRepository` wired
in and called at the points where each node produces data that belongs in
the database. Only the bodies that changed are annotated with
"# >>> persistence" comments — everything else is unchanged logic.

Wiring (constructors now take `repo`):
    BuildConfigurationNode   -> unchanged, reads only, no repo needed
    CompatibilityRagNode     -> unchanged, reads only, no repo needed
    TaskDecompositionNode(llm, rag, failure, repo, max_steps=8)
    SupplierOrderNode(client, failure, repo)
    PriceCheckNode(hitl, repo, threshold_pct=0.10)
    SubstituteCheckNode(hitl, repo)
    
Parts Required
      │
      ▼
Supplier Ordering
      │
      ▼
Wait for supplier response
      │
      ▼
Price Check ──────► HITL لو السعر زاد
      │
      ▼
Substitute Check ─► HITL لو البديل يأثر على الضمان
      │
      ▼
Installation Planning
      │
      ▼
Installation Sequence
"""

"""
sourcing_nodes_with_persistence.py

Same nodes as the original file, with `self.repo: SourcingRepository` wired
in and called at the points where each node produces data that belongs in
the database. Only the bodies that changed are annotated with
"# >>> persistence" comments — everything else is unchanged logic.

Wiring (constructors now take `repo`):
    BuildConfigurationNode   -> unchanged, reads only, no repo needed
    CompatibilityRagNode     -> unchanged, reads only, no repo needed
    TaskDecompositionNode(llm, rag, failure, repo, max_steps=8)
    SupplierOrderNode(client, failure, repo)
    PriceCheckNode(hitl, repo, threshold_pct=0.10)
    SubstituteCheckNode(hitl, repo)
"""
import asyncio
import re
import sqlite3
from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel

from rag.agentic_rag import AgenticRAG
from state_graph.graph1_multi_supplier.state import InstallationStep, SourcingState
from state_graph.failure_node import FailureNode
from state_graph.hitl_node import HitlNode
from planning_toolkit.planning_lab.algorithms.dynamic_decomposition import dynamic_decomposition
from .repository import SourcingRepository

_PART_ID_RE = re.compile(r"part\s+(\d+)", re.IGNORECASE)

# BuildConfigurationNode — read-only (build_part_requirements), no repo
class BuildConfigurationNode:
    def __init__(self, failure: FailureNode, db_path: str):
        self.failure = failure
        self.db_path = db_path

    def run(self, *, run_id: str, state: SourcingState, preset: str) -> SourcingState:
        def work() -> SourcingState:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT part_id, part_name, supplier, price, quantity
                    FROM build_part_requirements
                    WHERE preset_key = ?
                    ORDER BY part_id
                    """,
                    (preset,),
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                raise ValueError(f"unknown build preset (or no parts configured): {preset!r}")

            parts_required = [
                {
                    "part_id": row["part_id"],
                    "part_name": row["part_name"],
                    "quantity": row["quantity"],
                    "price": row["price"],
                    "preferred_suppliers": [row["supplier"]],
                }
                for row in rows
            ]

            new_state = dict(state)
            new_state["run_id"] = run_id
            new_state["parts_required"] = parts_required
            return new_state

        return self.failure.run(
            run_id=run_id, node_name=type(self).__name__, state=state, work=work
        )


# ----------------------------------------------------------------------
# CompatibilityRagNode — no table of its own, unchanged
# ----------------------------------------------------------------------
class CompatibilityRagNode:
    def __init__(self, agentic_rag: AgenticRAG, parts_catalog: dict[int, dict[str, Any]]):
        self.agentic_rag = agentic_rag
        self.parts_catalog = parts_catalog

    def lookup(self, part_id: int) -> dict[str, Any]:
        part = self.parts_catalog.get(part_id, {})
        part_name = part.get("name", f"part_{part_id}")
        query = (
            f"What are the compatibility rules, required torque spec, and any "
            f"parts that must be installed before the {part_name} "
            f"(part_id={part_id})?\n"
            "Answer with ONLY valid JSON, no markdown fences, in this shape:\n"
            '{"compatibility_notes": "...", "torque_spec": "...", '
            '"install_after": [part_id, ...], "special_instructions": "..."}'
        )
        result = self.agentic_rag.answer(query)
        return self._parse_answer(result.answer)

    @staticmethod
    def _parse_answer(raw: str) -> dict[str, Any]:
        text = (
            (raw or "")
            .strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        import json as _json

        try:
            data = _json.loads(text)
        except _json.JSONDecodeError:
            return {
                "compatibility_notes": raw.strip() if raw else "",
                "torque_spec": "",
                "install_after": [],
                "special_instructions": "",
            }
        return {
            "compatibility_notes": data.get("compatibility_notes", ""),
            "torque_spec": data.get("torque_spec", ""),
            "install_after": data.get("install_after", []) or [],
            "special_instructions": data.get("special_instructions", ""),
        }


# ----------------------------------------------------------------------
# TaskDecompositionNode -> installation_steps
# ----------------------------------------------------------------------
class TaskDecompositionNode:
    def __init__(
        self,
        llm: BaseChatModel,
        rag: CompatibilityRagNode,
        failure: FailureNode,
        repo: SourcingRepository,   # >>> persistence
        max_steps: int = 8,
    ):
        self.llm = llm
        self.rag = rag
        self.failure = failure
        self.repo = repo            # >>> persistence
        self.max_steps = max_steps

    def run(self, *, run_id: str, state: SourcingState) -> SourcingState:
        def work() -> SourcingState:
            delivered = set(state.get("delivered_part_ids", []))
            cancelled = set(state.get("cancelled_part_ids", []))
            required = state.get("parts_required", [])

            specs = self._fetch_all_specs(required)
            goal = self._build_goal(required, delivered, cancelled, specs)

            scheduled: list[InstallationStep] = []

            def executor(task: str) -> str:
                return self._install_step_executor(task, delivered, cancelled, scheduled, specs)

            asyncio.run(
                dynamic_decomposition(
                    goal=goal, llm=self.llm, max_steps=self.max_steps, executor=executor
                )
            )

            for i, step in enumerate(scheduled, start=1):
                step["step_order"] = i

            # >>> persistence: write the finished plan to installation_steps
            self.repo.save_installation_steps(run_id, scheduled)

            new_state = dict(state)
            new_state["installation_sequence"] = scheduled
            return new_state

        return self.failure.run(
            run_id=run_id, node_name=type(self).__name__, state=state, work=work
        )

    def _fetch_all_specs(self, required: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        specs: dict[int, dict[str, Any]] = {}
        for req in required:
            specs[req["part_id"]] = self.rag.lookup(req["part_id"])
        return specs

    @staticmethod
    def _build_goal(
        required: list[dict[str, Any]],
        delivered: set[int],
        cancelled: set[int],
        specs: dict[int, dict[str, Any]],
    ) -> str:
        lines = []
        for req in required:
            pid = req["part_id"]
            if pid in cancelled:
                status = "cancelled — do not schedule"
            elif pid in delivered:
                status = "delivered, ready to install"
            else:
                status = "not yet delivered — do not schedule"
            install_after = specs.get(pid, {}).get("install_after") or []
            dep_note = f"; must be installed AFTER part(s) {install_after}" if install_after else ""
            lines.append(f"- part_id={pid}, status={status}{dep_note}")
        return (
            "Build the physical installation sequence for this vehicle "
            "performance build (e.g. turbo kit, intercooler, ECU tune).\n"
            "Decide ONE installation step at a time, in the order it should "
            "physically happen.\n"
            "Phrase every next_task EXACTLY as: install part <part_id> "
            "(e.g. 'install part 42').\n"
            "Only propose a part whose status is 'delivered, ready to "
            "install'. Never propose a cancelled or not-yet-delivered part.\n"
            "Respect every 'must be installed AFTER' constraint below — "
            "never propose a part before the part(s) it depends on have "
            "already been scheduled.\n"
            "Set done to true once every deliverable part has a step.\n\n"
            "Parts:\n" + "\n".join(lines)
        )

    def _install_step_executor(
        self,
        task: str,
        delivered: set[int],
        cancelled: set[int],
        scheduled: list[InstallationStep],
        specs: dict[int, dict[str, Any]],
    ) -> str:
        part_id = self._parse_part_id(task)
        if part_id is None:
            return f"Rejected: could not parse a part_id out of task '{task}'."
        if part_id in cancelled:
            return f"Rejected: part {part_id} was cancelled, cannot be scheduled."
        if part_id not in delivered:
            return f"Rejected: part {part_id} has not been delivered yet."
        if any(s["part_id"] == part_id for s in scheduled):
            return f"Rejected: part {part_id} is already scheduled."

        spec = specs.get(part_id, {})
        install_after = spec.get("install_after") or []
        scheduled_ids = {s["part_id"] for s in scheduled}
        missing_deps = [dep for dep in install_after if dep not in scheduled_ids]
        if missing_deps:
            return (
                f"Rejected: part {part_id} must be installed after "
                f"part(s) {missing_deps}, which are not scheduled yet. "
                "Propose one of those parts first."
            )

        scheduled.append(
            {
                "part_id": part_id,
                "step_order": 0,
                "description": self._describe_step(part_id, spec),
                "status": "pending",
                "dependencies": install_after,
                "compatibility_notes": spec.get("compatibility_notes", ""),
                "torque_spec": spec.get("torque_spec", ""),
            }
        )
        return f"Scheduled part {part_id} as step {len(scheduled)}. Torque spec: {spec.get('torque_spec') or 'n/a'}."

    @staticmethod
    def _parse_part_id(task: str) -> int | None:
        match = _PART_ID_RE.search(task)
        return int(match.group(1)) if match else None

    @staticmethod
    def _describe_step(part_id: int, spec: dict) -> str:
        base = f"Install part {part_id}"
        if spec.get("special_instructions"):
            base += f" — {spec['special_instructions']}"
        return base


# ----------------------------------------------------------------------
# SupplierOrderNode -> supplier_orders + supplier_order_parts
# ----------------------------------------------------------------------
class SupplierClient(Protocol):
    def place_order(self, supplier: str, part_ids: list[int]) -> dict[str, Any]: ...


class SupplierOrderNode:
    MAX_ATTEMPTS = 3

    def __init__(self, client: SupplierClient, failure: FailureNode, repo: SourcingRepository):
        self.client = client
        self.failure = failure
        self.repo = repo   # >>> persistence

    def run(
        self, *, run_id: str, supplier: str, part_ids: list[int], state: SourcingState
    ) -> SourcingState:
        def work() -> SourcingState:
            last_error: Exception | None = None
            for _ in range(self.MAX_ATTEMPTS):
                try:
                    response = self.client.place_order(supplier, part_ids)
                    self._validate_response(response)

                    order_id = response["order_id"]
                    quoted_price = response["quoted_price"]

                    # >>> persistence: order + line items in one transaction
                    self.repo.save_supplier_order(
                        run_id=run_id,
                        order_id=order_id,
                        supplier=supplier,
                        status="ordered",
                        quoted_price=quoted_price,
                        part_ids=part_ids,
                    )
                    self.repo.log_event(
                        run_id=run_id,
                        order_id=order_id,
                        event_type="order_placed",
                        payload={"supplier": supplier, "part_ids": part_ids, "quoted_price": quoted_price},
                        status="processed",
                    )

                    new_state = dict(state)
                    orders = dict(new_state.get("orders", {}))
                    orders[order_id] = {
                        "order_id": order_id,
                        "supplier": supplier,
                        "status": "ordered",
                        "quoted_price": quoted_price,
                        "final_price": None,
                        "part_ids": part_ids,
                    }
                    new_state["orders"] = orders
                    return new_state

                except (TimeoutError, ValueError) as exc:
                    last_error = exc
                    # >>> persistence: only meaningful once we have an order_id;
                    # a failure before place_order() returns has no order row yet,
                    # so there is nothing to record here for the *first* failed
                    # attempt — record_order_failure is for post-creation retries
                    # (e.g. webhook confirmation retries), not this loop.
                    continue

            assert last_error is not None
            raise last_error

        return self.failure.run(
            run_id=run_id, node_name=type(self).__name__, state=state, work=work
        )

    @staticmethod
    def _validate_response(response: dict[str, Any]) -> None:
        required = {"order_id", "quoted_price"}
        missing = required - response.keys()
        if missing:
            raise ValueError(f"malformed supplier response, missing keys: {missing}")


# ----------------------------------------------------------------------
# PriceCheckNode -> supplier_orders.final_price / supplier_events
# ----------------------------------------------------------------------
class PriceCheckNode:
    def __init__(self, hitl: HitlNode, repo: SourcingRepository, threshold_pct: float = 0.10):
        self.hitl = hitl
        self.repo = repo   # >>> persistence
        self.threshold_pct = threshold_pct

    def run(self, *, run_id: str, order_id: int, state: SourcingState) -> SourcingState:
        order = state["orders"][order_id]
        quoted = order["quoted_price"]
        final = order.get("final_price")

        if final is None or quoted == 0:
            return state

        # >>> persistence: record the confirmed final price regardless of
        # whether it triggers HITL, so supplier_orders stays accurate
        self.repo.update_final_price(order_id, final)

        deviation = abs(final - quoted) / quoted
        if deviation <= self.threshold_pct:
            return state

        # >>> persistence: audit trail for the deviation itself
        self.repo.log_event(
            run_id=run_id,
            order_id=order_id,
            event_type="price_changed",
            payload={
                "quoted_price": quoted,
                "final_price": final,
                "deviation_pct": round(deviation * 100, 1),
            },
        )

        return self.hitl.run(
            run_id=run_id,
            state=state,
            action={
                "type": "price_deviation",
                "order_id": order_id,
                "quoted_price": quoted,
                "final_price": final,
                "deviation_pct": round(deviation * 100, 1),
            },
            reason=(
                f"Order {order_id}: final price {final} deviates "
                f"{deviation:.1%} from quote {quoted} "
                f"(threshold {self.threshold_pct:.0%})"
            ),
        )


# ----------------------------------------------------------------------
# SubstituteCheckNode -> supplier_order_parts + supplier_events
# ----------------------------------------------------------------------
class SubstituteCheckNode:
    def __init__(self, hitl: HitlNode, repo: SourcingRepository):
        self.hitl = hitl
        self.repo = repo   # >>> persistence

    def run(
        self,
        *,
        run_id: str,
        order_id: int,
        part_id: int,
        substitute: dict[str, Any],
        state: SourcingState,
    ) -> SourcingState:
        warranty_impact = substitute.get("warranty_impact")

        if not warranty_impact:
            return self._apply_substitute(run_id, state, order_id, part_id, substitute)

        # >>> persistence: log the offer before handing off to a human
        self.repo.log_event(
            run_id=run_id,
            order_id=order_id,
            event_type="substitute_offered",
            payload={
                "part_id": part_id,
                "substitute_part": substitute.get("substitute_part"),
                "warranty_impact": warranty_impact,
            },
        )

        return self.hitl.run(
            run_id=run_id,
            state=state,
            action={
                "type": "substitute_offered",
                "order_id": order_id,
                "part_id": part_id,
                "substitute_part": substitute.get("substitute_part"),
                "warranty_impact": warranty_impact,
            },
            reason=(
                f"Substitute for part {part_id} on order {order_id} "
                f"affects warranty: {warranty_impact}"
            ),
        )

    def _apply_substitute(
        self,
        run_id: str,
        state: SourcingState,
        order_id: int,
        part_id: int,
        substitute: dict[str, Any],
    ) -> SourcingState:
        substitute_part = substitute.get("substitute_part")

        # >>> persistence: this is now the actual write to supplier_order_parts
        self.repo.apply_substitute(
            order_id=order_id,
            part_id=part_id,
            substitute_part=substitute_part,
            warranty_impact=None,
        )

        new_state = dict(state)
        applied = dict(new_state.get("applied_substitutes", {}))
        applied[part_id] = substitute_part
        new_state["applied_substitutes"] = applied
        return new_state