"""CheckpointManager — the concrete CheckpointStore.

Backed by the real state_checkpoints table and state_graph_runs.

The database stores the Graph 1 state together with checkpoint metadata.
This class provides the CheckpointStore interface used by the state graph.
"""

from __future__ import annotations

import json
from typing import Any

from state_graph import runs
from state_graph.checkpoint import persistence
from state_graph.contracts import Checkpoint


def _unwrap(row) -> Checkpoint:
    """Convert a persistence row into a Checkpoint object."""

    return Checkpoint(
        checkpoint_id=row["checkpoint_id"],
        run_id=row["run_id"],
        node_name=row["node_name"],
        state=json.loads(row["state_json"]),
        reason=row["reason"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
    )


class CheckpointManager:
    """Concrete checkpoint manager for a single graph type."""

    def __init__(self, *, graph_type: str) -> None:
        self.graph_type = graph_type

    def start_run(
        self,
        run_id: str,
        *,
        vehicle_id: int | None = None,
        client_id: int | None = None,
    ) -> None:
        """Register a graph run before checkpoints are created."""

        runs.ensure_run(
            run_id,
            graph_type=self.graph_type,
            vehicle_id=vehicle_id,
            client_id=client_id,
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
        """Save one checkpoint and return the created Checkpoint."""

        runs.ensure_run(
            run_id,
            graph_type=self.graph_type,
        )

        checkpoint_id = persistence.insert(
            run_id=run_id,
            graph_name=self.graph_type,
            node_name=node_name,
            state=state,
            reason=reason,
            metadata=metadata,
        )

        runs.touch_run(
            run_id,
            status="running",
            current_state=node_name,
        )

        row = persistence.get_by_id(checkpoint_id)

        if row is None:
            raise RuntimeError(
                f"Checkpoint was inserted but could not be loaded: "
                f"{checkpoint_id}"
            )

        return _unwrap(row)

    def load(self, checkpoint_id: str) -> Checkpoint:
        """Load one checkpoint by ID."""

        row = persistence.get_by_id(checkpoint_id)

        if row is None:
            raise KeyError(
                f"unknown checkpoint: {checkpoint_id}"
            )

        return _unwrap(row)

    def get_latest(self, run_id: str) -> Checkpoint | None:
        """Return the latest checkpoint for a run."""

        row = persistence.get_latest_for_run(run_id)

        if row is None:
            return None

        return _unwrap(row)

    def history(self, run_id: str) -> list[dict[str, Any]]:
        """Return checkpoint history as state dictionaries.

        Graph 1 tests and callers expect history records to be
        dictionary-like, so each checkpoint is converted to its
        persisted state dictionary.

        The checkpoint metadata is also included without changing
        the actual state fields.
        """

        checkpoints = persistence.list_for_run(run_id)

        history: list[dict[str, Any]] = []

        for row in checkpoints:
            checkpoint = _unwrap(row)

            record = dict(checkpoint.state)

            # Keep checkpoint information available to callers.
            record["_checkpoint_id"] = checkpoint.checkpoint_id
            record["_run_id"] = checkpoint.run_id
            record["_node_name"] = checkpoint.node_name
            record["_reason"] = checkpoint.reason
            record["_metadata"] = checkpoint.metadata
            record["_created_at"] = checkpoint.created_at

            history.append(record)

        return history

    def mark_run_finished(
        self,
        run_id: str,
        *,
        status: str = "completed",
    ) -> None:
        """Mark a graph run as finished."""

        runs.touch_run(
            run_id,
            status=status,
        )

    def exists(self, run_id: str) -> bool:
        """Return True when a run has at least one checkpoint."""

        return self.get_latest(run_id) is not None

    def delete(self, run_id: str) -> None:
        """Delete all checkpoints belonging to a run."""

        persistence.delete_for_run(run_id)
