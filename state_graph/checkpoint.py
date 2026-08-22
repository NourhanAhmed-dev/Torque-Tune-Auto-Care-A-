"""
Checkpointing and crash/resume support for the state graph.
"""

from datetime import datetime, timezone

from db.persistence import (
    append_history,
    checkpoint_exists,
    delete_state,
    get_history,
    get_latest_state,
    upsert_state,
)
from state_graph.schema import RunState


class CheckpointManager:
    """
    Handles persistent saving and loading of graph checkpoints.

    Checkpoints are stored in the project's existing db/redline.db
    database, so they survive process restarts and crashes.
    """

    def save(self, state: RunState) -> RunState:
        """
        Save the current state as a persistent checkpoint.

        The latest state is updated, while every checkpoint is also
        preserved in the immutable history trail.
        """
        state.checkpoint_ts = datetime.now(timezone.utc)

        # Store the latest state for crash/resume.
        upsert_state(state)

        # Store an immutable record for the execution history.
        append_history(state)

        return state

    def load(self, run_id: str) -> RunState:
        """Load the latest persistent checkpoint for a run."""
        return get_latest_state(run_id)

    def history(self, run_id: str) -> list[dict]:
        """Return the checkpoint history for a run."""
        return get_history(run_id)

    def exists(self, run_id: str) -> bool:
        """Check whether a persistent checkpoint exists."""
        return checkpoint_exists(run_id)

    def delete(self, run_id: str) -> None:
        """Delete a persistent checkpoint."""
        delete_state(run_id)