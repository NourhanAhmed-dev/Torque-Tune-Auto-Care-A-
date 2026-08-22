"""Shared interfaces between state_graph's packages.

hitl/ and tickets/ depend on this Protocol, not on a concrete
implementation — CheckpointManager (checkpoint/checkpoint_manager.py)
satisfies it against the real state_checkpoints table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Checkpoint:
    checkpoint_id: str          # state_checkpoints.checkpoint_id — TEXT
    run_id: str
    node_name: str              # maps to state_checkpoints.state_name
    state: dict[str, Any]       # maps to state_checkpoints.state_data (JSON)
    reason: str                 # no dedicated column — see checkpoint_manager.py envelope
    metadata: dict[str, Any]    # same
    created_at: str = field(default_factory=_now)


class CheckpointStore(Protocol):
    def save(
        self,
        *,
        run_id: str,
        node_name: str,
        state: dict[str, Any],
        reason: str,
        metadata: dict[str, Any],
    ) -> Checkpoint: ...

    def load(self, checkpoint_id: int) -> Checkpoint: ...


class PlatformTaskGateway(Protocol):
    """Deliberately unused for now — wiring to a real admin platform is
    the next step, per the user's instruction to connect to the
    checkpoint layer first. Kept here so hitl/tickets can accept an
    optional gateway without a forward-reference import cycle."""

    def create_task(
        self, *, task_type: str, resource_id: str, title: str, payload: dict[str, Any],
    ) -> str: ...

    def close_task(self, *, platform_task_id: str) -> None: ...
