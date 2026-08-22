from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from planning_toolkit.planning_lab.algorithms.lats import (
    LATSResult,
    lats as toolkit_lats,
)
from planning_toolkit.planning_lab.algorithms.environment import Environment


def run_lats(
    task: str,
    llm: BaseChatModel,
    environment: Environment,
    iterations: int = 2,
    n_actions: int = 2,
    exploration_weight: float = 1.414,
) -> LATSResult:
    """
    Run the TA's LATS implementation using an external environment
    for grounded validation.

    The environment is intentionally passed in from the caller so
    LATS can later be connected to real MCP/database evidence.
    """

    return toolkit_lats(
        task=task,
        llm=llm,
        environment=environment,
        iterations=iterations,
        n_actions=n_actions,
        exploration_weight=exploration_weight,
    )