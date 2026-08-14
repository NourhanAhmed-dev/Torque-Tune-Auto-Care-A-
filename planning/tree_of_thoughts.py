from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from planning.models import PlanningRequest
from planning_toolkit.planning_lab.algorithms.tree_of_thoughts import (
    tree_of_thoughts as toolkit_tree_of_thoughts,
)
from planning_toolkit.planning_lab.models import Thought


def build_tot_question(planning_request: PlanningRequest) -> str:
    return f"""
You are evaluating a high-risk vehicle tuning job for Torque-Tune-Auto-Care.

Customer request:
{planning_request.request}

Client ID: {planning_request.client_id}
Vehicle ID: {planning_request.vehicle_id}
Technician ID: {planning_request.tech_id}
Appointment ID: {planning_request.appointment_id}

Your task is to compare possible decisions for this planning request.

Possible decisions:

1. RELEASE
   Sufficient verified evidence exists to safely proceed.

2. HOLD
   Required evidence is missing, so the job cannot currently be released.

3. ESCALATE
   Shift-lead review or customer confirmation is required.

Use Tree-of-Thoughts reasoning to consider multiple possible
decision paths before selecting the most appropriate candidate.

For every candidate reasoning path, consider:

- Client and vehicle identity.
- Previous tuning history.
- Appointment validity.
- Technician identity, authentication, and authorization.
- Compliance and warranty requirements.
- Required customer disclosure and sign-off.
- Whether the requested modification is emissions-affecting.
- Whether any consequential database write is permitted.

The candidate decision must be grounded in available evidence.

Do not invent evidence.
Do not assume that an MCP or database check succeeded.
Do not perform any consequential action.

Prefer a candidate that correctly identifies whether the available
evidence supports RELEASE, HOLD, or ESCALATE.
"""


def evaluate_decisions(
    planning_request: PlanningRequest,
    llm: BaseChatModel,
    depth: int = 2,
    beam_width: int = 2,
) -> list[Thought]:
    question = build_tot_question(planning_request)

    return toolkit_tree_of_thoughts(
        question,
        llm,
        depth=depth,
        beam_width=beam_width,
    )