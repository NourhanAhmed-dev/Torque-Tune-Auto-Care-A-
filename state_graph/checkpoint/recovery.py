from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.contracts import Checkpoint


@dataclass
class ResumeInfo:
    can_resume: bool
    last_checkpoint: Checkpoint | None
    completed_nodes: list[str]
    state: dict[str, Any]


def get_resume_info(run_id: str, checkpoint_manager: CheckpointManager) -> ResumeInfo:
    latest = checkpoint_manager.get_latest(run_id)
    if latest is None:
        return ResumeInfo(can_resume=False, last_checkpoint=None, completed_nodes=[], state={})

    completed = list(latest.state.get("completed_nodes", []))
    return ResumeInfo(can_resume=True, last_checkpoint=latest, completed_nodes=completed, state=latest.state)


def should_skip(node_name: str, resume_info: ResumeInfo) -> bool:
    return node_name in resume_info.completed_nodes
