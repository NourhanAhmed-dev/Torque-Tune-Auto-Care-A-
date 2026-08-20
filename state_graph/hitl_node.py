from __future__ import annotations

from typing import Any
from state_graph.hitl.hitl_manager import HitlManager


class HitlNode:
    def __init__(self, manager: HitlManager):
        self.manager = manager

    def run(
        self,
        *,
        run_id: str,
        state: dict[str, Any],
        action: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        self.manager.require_decision(
            run_id=run_id,
            node_name=type(self).__name__,
            state=state,
            action=action,
            reason=reason,
        )

        return state