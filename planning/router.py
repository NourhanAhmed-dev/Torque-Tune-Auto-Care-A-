from __future__ import annotations

from enum import Enum


class PlanningMethod(str, Enum):
    PLAN_AND_SOLVE = "plan_and_solve"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    LATS = "lats"


def route_subtask(subtask: str) -> PlanningMethod:
    """
    Choose the appropriate planning algorithm for a subtask.

    Plan-and-Solve:
        Sequential verification and straightforward planning.

    Tree-of-Thoughts:
        Comparing multiple possible decisions or strategies.

    LATS:
        Final decision requiring external MCP/DB/environment validation.
    """

    text = subtask.lower().strip()

    # ---------------------------------------------------------
    # 1. TREE-OF-THOUGHTS
    # Use when the task explicitly compares alternatives.
    # This check MUST come before decision keywords because
    # comparison tasks may contain words like release/hold/escalate.
    # ---------------------------------------------------------
    comparison_keywords = (
        "compare",
        "comparison",
        "alternative",
        "alternatives",
        "which decision",
        "release or hold",
        "release or escalate",
        "hold or escalate",
        "release vs hold",
        "release vs escalate",
        "hold vs escalate",
        "release versus hold",
        "release versus escalate",
        "hold versus escalate",
    )

    if any(keyword in text for keyword in comparison_keywords):
        return PlanningMethod.TREE_OF_THOUGHTS

    # ---------------------------------------------------------
    # 2. LATS
    # Final decision requiring external MCP/DB/environment
    # validation.
    # ---------------------------------------------------------
    lats_keywords = (
        "final decision",
        "final release decision",
        "make the final",
        "mcp evidence",
        "database evidence",
        "external validation",
        "environment validation",
    )

    if any(keyword in text for keyword in lats_keywords):
        return PlanningMethod.LATS

    # ---------------------------------------------------------
    # 3. PLAN-AND-SOLVE
    # Straightforward sequential verification/planning.
    # ---------------------------------------------------------
    return PlanningMethod.PLAN_AND_SOLVE


def select_algorithm(subtask: str, algorithms: dict):
    """
    Return the algorithm implementation selected by the router.
    """

    method = route_subtask(subtask)
    return algorithms[method]