from __future__ import annotations

from typing import Any, Literal
from langgraph.graph import END, START, StateGraph
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.checkpoint.recovery import ResumeInfo, get_resume_info, should_skip
from state_graph.graphs.graph1_multi_supplier.nodes import (
    BuildConfigurationNode,
    PriceCheckNode,
    SubstituteCheckNode,
    SupplierOrderNode,
    TaskDecompositionNode,
)
from state_graph.graphs.graph1_multi_supplier.state import SourcingState
from .repository import SourcingRepository  # >>> persistence


class _GraphState(SourcingState, total=False):
    """SourcingState plus transient routing/input fields required by LangGraph.

    These fields are orchestration-only. They are removed before the state
    is returned through the public API.
    """
    entry: Literal["preset", "orders", "event", "hitl"]
    preset: str | None
    orders_to_place: list[dict[str, Any]] | None
    event: dict[str, Any] | None
    hitl_decision: dict[str, Any] | None
    # RECOVERY: tracks which nodes already completed for this run_id so a
    # resumed invocation can skip work that was already checkpointed.
    completed_nodes: list[str]


_TRANSIENT_KEYS = ("entry", "preset", "orders_to_place", "event", "hitl_decision")


def _strip_transient(state: _GraphState) -> SourcingState:
    return {k: v for k, v in state.items() if k not in _TRANSIENT_KEYS}  # type: ignore[return-value]


class SourcingInstallGraph:
    """LangGraph orchestration for the existing sourcing/install flow.

    The business flow is unchanged:

        start_from_preset()
            -> build_configuration
            -> place_orders
            -> END

        start()
            -> place_orders
            -> END

        on_supplier_event()
            -> apply_event_effects
            -> price_check / substitute_check / task_decomposition
            -> task_decomposition
            -> END

        on_hitl_decision()
            -> apply_hitl_decision
            -> task_decomposition
            -> END

    LangGraph is used only for graph orchestration/routing.

    Checkpoint persistence is handled by the project's own
    CheckpointManager. It is intentionally NOT passed to
    StateGraph.compile(), because CheckpointManager is a project-level
    CheckpointStore and is not LangGraph's BaseCheckpointSaver.

    A checkpoint is saved after every successfully completed graph node.

    Business-data persistence (supplier_orders, supplier_order_parts,
    installation_steps, supplier_events) is handled inside the nodes
    themselves via SourcingRepository — this graph only holds a reference
    to the same repository instance for the couple of writes that happen
    at the orchestration layer (order confirm/cancel after a HITL decision).

    RECOVERY: each public entry point checks get_resume_info(run_id, ...)
    before invoking the graph. If a prior checkpoint exists for that run_id,
    its state (including completed_nodes) is used as the starting point, and
    each node skips its own work if it's already in completed_nodes.
    """

    def __init__(
        self,
        order_node: SupplierOrderNode,
        decomposition_node: TaskDecompositionNode,
        price_check_node: PriceCheckNode,
        substitute_check_node: SubstituteCheckNode,
        build_config_node: BuildConfigurationNode,
        repo: SourcingRepository,  # >>> persistence: same instance injected into the nodes
        checkpoint_manager: CheckpointManager | None = None,
    ):
        self.order_node = order_node
        self.decomposition_node = decomposition_node
        self.price_check_node = price_check_node
        self.substitute_check_node = substitute_check_node
        self.build_config_node = build_config_node
        self.repo = repo  # >>> persistence
        self.checkpoint_manager = (
            checkpoint_manager or CheckpointManager(graph_type="graph1_multi_supplier")
        )
        self._graph = self._build_graph().compile()

    # ------------------------------------------------------------------
    # Graph construction -- unchanged
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(_GraphState)

        graph.add_node("build_configuration", self._build_configuration)
        graph.add_node("place_orders", self._place_orders)
        graph.add_node("apply_event_effects", self._apply_event_effects)
        graph.add_node("price_check", self._price_check)
        graph.add_node("substitute_check", self._substitute_check)
        graph.add_node("apply_hitl_decision", self._apply_hitl_decision)
        graph.add_node("task_decomposition", self._task_decomposition)

        graph.add_conditional_edges(
            START, self._route_entry,
            {
                "build_configuration": "build_configuration",
                "place_orders": "place_orders",
                "apply_event_effects": "apply_event_effects",
                "apply_hitl_decision": "apply_hitl_decision",
            },
        )

        graph.add_edge("build_configuration", "place_orders")
        graph.add_edge("place_orders", END)

        graph.add_conditional_edges(
            "apply_event_effects", self._route_event_type,
            {
                "price_check": "price_check",
                "substitute_check": "substitute_check",
                "task_decomposition": "task_decomposition",
            },
        )
        graph.add_edge("price_check", "task_decomposition")
        graph.add_edge("substitute_check", "task_decomposition")

        graph.add_edge("apply_hitl_decision", "task_decomposition")
        graph.add_edge("task_decomposition", END)

        return graph

    # ------------------------------------------------------------------
    # Checkpoint helper -- unchanged
    # ------------------------------------------------------------------

    def _checkpoint(
        self, *, state: dict[str, Any], node_name: str, reason: str, metadata: dict[str, Any] | None = None
    ) -> None:
        self.checkpoint_manager.save(
            run_id=state["run_id"],
            node_name=node_name,
            state=_strip_transient(state),  # type: ignore[arg-type]
            reason=reason,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # RECOVERY helpers -- unchanged
    # ------------------------------------------------------------------

    def _prepare_initial_state(
        self, *, run_id: str, state: SourcingState, entry_fields: dict[str, Any]
        ) -> _GraphState:
        resume_info = get_resume_info(run_id, self.checkpoint_manager)
        if resume_info.can_resume:
            base = {**state, **resume_info.state}
            base["completed_nodes"] = resume_info.completed_nodes
        else:
            base = {**state, "completed_nodes": []}
    
        entry = entry_fields.get("entry")
        if entry in ("event", "hitl"):
            nodes_to_reset = {
            "apply_event_effects", 
            "price_check", 
            "substitute_check", 
            "apply_hitl_decision", 
            "task_decomposition"
        }
            base["completed_nodes"] = [
            n for n in base["completed_nodes"] if n not in nodes_to_reset
        ]
    
        return {**base, "run_id": run_id, **entry_fields}
    @staticmethod
    def _should_skip_node(node_name: str, state: _GraphState) -> bool:
        resume_info = ResumeInfo(
            can_resume=True,
            last_checkpoint=None,
            completed_nodes=list(state.get("completed_nodes", [])),
            state=state,  # type: ignore[arg-type]
        )
        return should_skip(node_name, resume_info)

    @staticmethod
    def _mark_completed(state: dict[str, Any], node_name: str) -> dict[str, Any]:
        completed = list(state.get("completed_nodes", []))
        if node_name not in completed:
            completed.append(node_name)
        return {**state, "completed_nodes": completed}

    # ------------------------------------------------------------------
    # Routers -- unchanged
    # ------------------------------------------------------------------

    @staticmethod
    def _route_entry(state: _GraphState) -> str:
        entry = state["entry"]
        if entry == "preset":
            return "build_configuration"
        if entry == "orders":
            return "place_orders"
        if entry == "event":
            return "apply_event_effects"
        if entry == "hitl":
            return "apply_hitl_decision"
        raise ValueError(f"unknown graph entry: {entry!r}")

    @staticmethod
    def _route_event_type(state: _GraphState) -> str:
        event = state["event"]
        event_type = event["event_type"]
        if event_type == "price_changed":
            return "price_check"
        if event_type == "substitute_offered":
            return "substitute_check"
        if event_type in ("delivery_confirmed", "backorder", "cancelled"):
            return "task_decomposition"
        raise ValueError(f"unknown supplier event type: {event_type}")

    # ------------------------------------------------------------------
    # Node bodies
    # ------------------------------------------------------------------

    def _build_configuration(self, state: _GraphState) -> dict[str, Any]:
        if self._should_skip_node("build_configuration", state):
            return dict(state)
        run_id = state["run_id"]
        new_state = self.build_config_node.run(run_id=run_id, state=state, preset=state["preset"])
        orders_to_place = self._group_parts_by_supplier(new_state["parts_required"])
        result = {**new_state, "orders_to_place": orders_to_place}
        result = self._mark_completed(result, "build_configuration")
        self._checkpoint(state=result, node_name="build_configuration", reason="node_completed")
        return result

    def _place_orders(self, state: _GraphState) -> dict[str, Any]:
        # >>> persistence note: SupplierOrderNode.run() now writes
        # supplier_orders / supplier_order_parts / a supplier_events row
        # itself (via its injected repo) before returning — nothing to
        # change here, the loop just stays the same.
        if self._should_skip_node("place_orders", state):
            return dict(state)
        run_id = state["run_id"]
        current: dict[str, Any] = dict(state)
        for order in state.get("orders_to_place") or []:
            current = self.order_node.run(
                run_id=run_id, supplier=order["supplier"], part_ids=order["part_ids"], state=current
            )
        current = self._mark_completed(current, "place_orders")
        self._checkpoint(state=current, node_name="place_orders", reason="node_completed")
        return current

    def _apply_event_effects(self, state: _GraphState) -> dict[str, Any]:
        if self._should_skip_node("apply_event_effects", state):
            return dict(state)
        event = state["event"]
        event_type = event["event_type"]

        if event_type == "delivery_confirmed":
            result = self._mark_delivered(state, event["part_id"])
        elif event_type == "backorder":
            result = dict(state)
        elif event_type == "cancelled":
            result = self._mark_cancelled(state, event["part_id"])
        elif event_type == "price_changed":
            result = self._apply_final_price(state, event["order_id"], event["final_price"])
        elif event_type == "substitute_offered":
            result = dict(state)
        else:
            raise ValueError(f"unknown supplier event type: {event_type}")

        result = self._mark_completed(result, "apply_event_effects")
        self._checkpoint(
            state=result, node_name="apply_event_effects", reason="node_completed", metadata={"event_type": event_type}
        )
        return result

    def _price_check(self, state: _GraphState) -> dict[str, Any]:
        # >>> persistence note: PriceCheckNode.run() now writes final_price
        # (and, when it deviates, a supplier_events row) via its injected
        # repo before it ever reaches the HITL branch — nothing to change here.
        if self._should_skip_node("price_check", state):
            return dict(state)
        run_id = state["run_id"]
        event = state["event"]
        result = self.price_check_node.run(run_id=run_id, order_id=event["order_id"], state=state)
        result = self._mark_completed(result, "price_check")
        self._checkpoint(
            state=result, node_name="price_check", reason="node_completed", metadata={"order_id": event["order_id"]}
        )
        return result

    def _substitute_check(self, state: _GraphState) -> dict[str, Any]:
        # >>> persistence note: SubstituteCheckNode.run() now writes the
        # substitute straight to supplier_order_parts when it's auto-applied,
        # or logs a supplier_events row before escalating to HITL — nothing
        # to change here.
        if self._should_skip_node("substitute_check", state):
            return dict(state)
        run_id = state["run_id"]
        event = state["event"]
        result = self.substitute_check_node.run(
            run_id=run_id, order_id=event["order_id"], part_id=event["part_id"],
            substitute=event["substitute"], state=state
        )
        result = self._mark_completed(result, "substitute_check")
        self._checkpoint(
            state=result, node_name="substitute_check", reason="node_completed",
            metadata={"order_id": event["order_id"], "part_id": event["part_id"]}
        )
        return result

    def _apply_hitl_decision(self, state: _GraphState) -> dict[str, Any]:
        if self._should_skip_node("apply_hitl_decision", state):
            return dict(state)
        decision = state["hitl_decision"]
        action_type = decision["action"]["type"]

        if action_type == "price_deviation":
            order_id = decision["action"]["order_id"]
            if decision["approved"]:
                result = self._confirm_order(state, order_id)
            else:
                result = self._cancel_order(state, order_id)
        elif action_type == "substitute_offered":
            if decision["approved"]:
                # >>> persistence FIX: the previous version only forwarded
                # substitute_part, silently dropping warranty_impact — so an
                # approved substitute with a real warranty impact ended up
                # persisted with warranty_impact = NULL. _apply_substitute()
                # now reads warranty_impact from this dict, so it must be
                # carried through from the original HITL action payload.
                result = self.substitute_check_node._apply_substitute(
                    state,
                    decision["action"]["order_id"],
                    decision["action"]["part_id"],
                    {
                        "substitute_part": decision["action"]["substitute_part"],
                        "warranty_impact": decision["action"].get("warranty_impact"),
                    },
                )
            else:
                result = self._mark_cancelled(state, decision["action"]["part_id"])
        else:
            raise ValueError(f"unknown hitl action type: {action_type}")

        result = self._mark_completed(result, "apply_hitl_decision")
        self._checkpoint(
            state=result, node_name="apply_hitl_decision", reason="node_completed",
            metadata={"action_type": action_type, "approved": decision["approved"]}
        )
        return result

    def _task_decomposition(self, state: _GraphState) -> dict[str, Any]:
        # >>> persistence note: TaskDecompositionNode.run() now replaces
        # installation_steps for this run_id via its injected repo right
        # before returning — nothing to change here.
        if self._should_skip_node("task_decomposition", state):
            return dict(state)
        run_id = state["run_id"]
        result = self.decomposition_node.run(run_id=run_id, state=state)
        result = self._mark_completed(result, "task_decomposition")
        self._checkpoint(state=result, node_name="task_decomposition", reason="node_completed")
        return result

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _group_parts_by_supplier(parts_required: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[int]] = {}
        for part in parts_required:
            supplier = part["preferred_suppliers"][0]
            grouped.setdefault(supplier, []).append(part["part_id"])
        return [{"supplier": supplier, "part_ids": part_ids} for supplier, part_ids in grouped.items()]

    @staticmethod
    def _mark_delivered(state: _GraphState, part_id: int) -> dict[str, Any]:
        new_state = dict(state)
        delivered = list(new_state.get("delivered_part_ids", []))
        if part_id not in delivered:
            delivered.append(part_id)
        new_state["delivered_part_ids"] = delivered
        return new_state

    @staticmethod
    def _mark_cancelled(state: _GraphState, part_id: int) -> dict[str, Any]:
        new_state = dict(state)
        cancelled = list(new_state.get("cancelled_part_ids", []))
        if part_id not in cancelled:
            cancelled.append(part_id)
        new_state["cancelled_part_ids"] = cancelled
        return new_state

    @staticmethod
    def _apply_final_price(state: _GraphState, order_id: int, final_price: float) -> dict[str, Any]:
        new_state = dict(state)
        orders = dict(new_state.get("orders", {}))
        order = dict(orders[order_id])
        order["final_price"] = final_price
        orders[order_id] = order
        new_state["orders"] = orders
        return new_state

    def _confirm_order(self, state: _GraphState, order_id: int) -> dict[str, Any]:
        new_state = dict(state)
        orders = dict(new_state.get("orders", {}))
        order = dict(orders[order_id])
        order["status"] = "confirmed"
        if "final_price" not in order or order["final_price"] is None:
            order["final_price"] = order.get("quoted_price")
        orders[order_id] = order
        new_state["orders"] = orders
        self.repo.update_order_status(order_id, "confirmed")
        if order.get("final_price"):
            self.repo.update_final_price(order_id, order["final_price"])
        return new_state

    def _cancel_order(self, state: _GraphState, order_id: int) -> dict[str, Any]:
        new_state = dict(state)
        orders = dict(new_state.get("orders", {}))
        order = dict(orders[order_id])
        order["status"] = "cancelled"
        orders[order_id] = order
        new_state["orders"] = orders
        # >>> persistence: same as above, for the rejected-order path.
        self.repo.update_order_status(order_id, "cancelled")
        return new_state

    # ------------------------------------------------------------------
    # Public API -- same signatures and same flow, unchanged
    # ------------------------------------------------------------------

    def start_from_preset(self, *, run_id: str, state: SourcingState, preset: str) -> SourcingState:
        self.checkpoint_manager.start_run(run_id)
        init_state = self._prepare_initial_state(
            run_id=run_id, state=state, entry_fields={"entry": "preset", "preset": preset}
        )
        result = self._graph.invoke(init_state)
        self.checkpoint_manager.mark_run_finished(run_id, status="completed")
        return _strip_transient(result)

    def start(self, *, run_id: str, state: SourcingState, orders_to_place: list[dict[str, Any]]) -> SourcingState:
        """orders_to_place: [{"supplier": str, "part_ids": [int, ...]}, ...]"""
        self.checkpoint_manager.start_run(run_id)
        init_state = self._prepare_initial_state(
            run_id=run_id, state=state,
            entry_fields={"entry": "orders", "orders_to_place": orders_to_place},
        )
        result = self._graph.invoke(init_state)
        self.checkpoint_manager.mark_run_finished(run_id, status="completed")
        return _strip_transient(result)

    def on_supplier_event(self, *, run_id: str, event: dict[str, Any], state: SourcingState) -> SourcingState:
        self.checkpoint_manager.start_run(run_id)
        init_state = self._prepare_initial_state(
            run_id=run_id, state=state, entry_fields={"entry": "event", "event": event}
        )
        result = self._graph.invoke(init_state)
        self.checkpoint_manager.mark_run_finished(run_id, status="completed")
        return _strip_transient(result)

    def on_hitl_decision(self, *, run_id: str, decision: dict[str, Any], state: SourcingState) -> SourcingState:
        self.checkpoint_manager.start_run(run_id)
        init_state = self._prepare_initial_state(
            run_id=run_id, state=state, entry_fields={"entry": "hitl", "hitl_decision": decision}
        )
        result = self._graph.invoke(init_state)
        self.checkpoint_manager.mark_run_finished(run_id, status="completed")
        return _strip_transient(result)