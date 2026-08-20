from __future__ import annotations

from collections.abc import Callable
from typing import Any
from state_graph.tickets.ticket_manager import TicketManager


class FailureNode:
    def __init__(self, manager: TicketManager):
        self.manager = manager

    def run(
        self,
        *,
        run_id: str,
        node_name: str,
        state: dict[str, Any],
        work: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return work()

        except Exception as error:
            self.manager.capture_failure(
                run_id=run_id,
                node_name=node_name,
                state=state,
                error=error,
            )

            # capture_failure() always raises FailurePaused,
            # so this line is only for type checkers.
            raise