"""CheckpointManager — the concrete CheckpointStore, backed by the real
state_checkpoints table (and, transitively, state_graph_runs — a
checkpoint can't exist without its run existing first, because the FK
is actually enforced).
 
state_checkpoints has no `reason`/`metadata` columns. Rather than alter
the adopted schema, this class wraps them into state_data as an
envelope: {"state": <the real state dict>, "reason": ..., "metadata":
...}. load()/get_latest() unwrap the same envelope on the way out, so
callers of .save()/.load() never see the wrapping — they still get a
Checkpoint with .state / .reason / .metadata as separate fields.
"""
from __future__ import annotations
 
import json
from typing import Any
 
from state_graph import runs
from state_graph.checkpoint import persistence
from state_graph.contracts import Checkpoint
 
 
def _wrap(state: dict[str, Any], reason: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {"state": state, "reason": reason, "metadata": metadata}
 
 
def _unwrap(row) -> Checkpoint:
    envelope = json.loads(row["state_data"])
    return Checkpoint(
        checkpoint_id=row["checkpoint_id"],
        run_id=row["run_id"],
        node_name=row["state_name"],
        state=envelope.get("state", {}),
        reason=envelope.get("reason", ""),
        metadata=envelope.get("metadata", {}),
        created_at=row["created_at"],
    )
 
 
class CheckpointManager:
    """Satisfies contracts.CheckpointStore. One instance per graph type
    (repair / tuning / warranty, ...) — graph_type is what gets written
    into state_graph_runs.graph_type the first time a run is seen."""
 
    def __init__(self, *, graph_type: str) -> None:
        self.graph_type = graph_type
 
    def start_run(
        self, run_id: str, *, vehicle_id: int | None = None, client_id: int | None = None
    ) -> None:
        """Optional explicit call to register vehicle_id/client_id up
        front. Not required — save() will register the run anyway (with
        NULL vehicle_id/client_id) the first time it's called for a new
        run_id — but calling this first gets the FK-linked context into
        state_graph_runs from the start."""
        runs.ensure_run(
            run_id, graph_type=self.graph_type, vehicle_id=vehicle_id, client_id=client_id
        )
 
    def save(
        self,
        *,
        run_id: str,
        node_name: str,
        state: dict[str, Any],
        reason: str,
        metadata: dict[str, Any],
    ) -> Checkpoint:
        # The FK on state_checkpoints.run_id requires this row to exist
        # first. Idempotent: no-ops if start_run() already created it.
        runs.ensure_run(run_id, graph_type=self.graph_type)
 
        checkpoint_id = persistence.insert(
            run_id=run_id,
            state_name=node_name,
            state_data=_wrap(state, reason, metadata),
        )
        runs.touch_run(run_id, status="running", current_state=node_name)
 
        row = persistence.get_by_id(checkpoint_id)
        return _unwrap(row)
 
    def load(self, checkpoint_id: int) -> Checkpoint:
        row = persistence.get_by_id(checkpoint_id)
        if row is None:
            raise KeyError(f"unknown checkpoint: {checkpoint_id}")
        return _unwrap(row)
 
    def get_latest(self, run_id: str) -> Checkpoint | None:
        row = persistence.get_latest_for_run(run_id)
        return _unwrap(row) if row else None
 
    def history(self, run_id: str) -> list[Checkpoint]:
        return [_unwrap(row) for row in persistence.list_for_run(run_id)]
 
    def mark_run_finished(self, run_id: str, *, status: str = "completed") -> None:
        runs.touch_run(run_id, status=status)
 