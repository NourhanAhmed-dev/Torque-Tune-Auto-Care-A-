from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """All possible statuses for a graph run."""

    RUNNING = "running"

    # Expected pauses
    WAITING_HITL = "waiting_hitl"
    WAITING_EXTERNAL = "waiting_external"

    # Unexpected failure
    FAILED = "failed"
    TICKET_OPEN = "ticket_open"

    # Final states
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class HITLData(BaseModel):
    """Information needed for a pending human-in-the-loop task."""

    reason: str
    assigned_admin: str | None = None
    status: str = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketData(BaseModel):
    """Information about an unexpected failure."""

    error: str
    node_failed: str
    status: str = "open"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunState(BaseModel):
    """
    Shared state contract for all state graphs.

    Graph-specific data should be stored inside payload.
    """

    run_id: str
    graph_name: str
    current_node: str = "START"

    status: RunStatus = RunStatus.RUNNING
    payload: dict[str, Any] = Field(default_factory=dict)

    checkpoint_ts: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    hitl: HITLData | None = None
    ticket: TicketData | None = None