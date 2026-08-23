from __future__ import annotations
#Graph 2 -- node implementations.
import json
import re
from typing import Any, Literal, TypedDict

from langgraph.graph import END
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.checkpoint.recovery import get_resume_info, should_skip, ResumeInfo
from state_graph.failure_node import FailureNode
from state_graph.hitl_node import HitlNode
from state_graph.tickets.ticket_manager import TicketManager
from state_graph.hitl.hitl_manager import HitlManager
from rag.agentic_rag import AgenticRAG


# --------------------------------------------------------------------------
# Node names (also used as `node_name` in checkpoints / completed_nodes)
# --------------------------------------------------------------------------

INTAKE_COMPLAINT = "intake_complaint"
LINK_TO_ORIGINAL_LOG = "link_to_original_log"
SCHEDULE_INSPECTION = "schedule_inspection"
EVALUATE_INSPECTION = "evaluate_inspection"
DETERMINE_RESPONSIBILITY = "determine_responsibility"
SENIOR_REVIEW_HITL = "senior_review_hitl"
AWAIT_CLIENT_DECISION = "await_client_decision"
TICKET = "ticket"
COMPLETE = "complete"

Status = Literal[
    "running",
    "waiting_inspection",
    "waiting_hitl",
    "waiting_client",
    "ticket_open",
    "completed",
]


class InconclusiveInspection(Exception):
    """Raised inside EVALUATE_INSPECTION's work() when the physical
    inspection could not establish a cause. FailureNode catches this and
    turns it into a ticket instead of blindly retrying the same
    inspection."""


class HitlRejected(Exception):
    """Raised when a senior reviewer rejects the candidate responsibility.

    ApprovalService.decide() only ever records {"approved", "comment",
    "admin_id"} -- there is no field for a corrected responsibility
    value, just a free-text comment. So a rejection can't be applied
    automatically the way an approval can; it needs the same
    ticket-based follow-up as an inconclusive inspection (a human has
    to actually decide what responsibility *is*, outside this node)."""


class Graph2State(TypedDict, total=False):
    run_id: str
    vehicle_id: int
    client_id: int | None

    complaint: dict[str, Any]

    # populated by LINK_TO_ORIGINAL_LOG (via AgenticRAG)
    original_log_summary: str
    original_log_sources: list[str]

    # populated externally once the car has actually been inspected
    inspection_scheduled: bool
    inspection_result: dict[str, Any] | None  # {"status": "tuning_fault"|"unrelated"|"inconclusive", "notes": str}

    # populated by DETERMINE_RESPONSIBILITY (via the constrained ReAct loop)
    responsibility: str | None          # "company" | "client" | "unrelated"
    responsibility_ambiguous: bool
    responsibility_react_trace: list[dict[str, Any]]  # thought/action/observation history
    hitl_decision: dict[str, Any] | None
    proposed_resolution: str | None

    # populated externally once the client has replied
    client_decision: str | None         # "accept" | "reject" | "escalate"

    completed_nodes: list[str]
    status: Status


# --------------------------------------------------------------------------
# Node logic
# --------------------------------------------------------------------------


class Graph2Nodes:
    """Holds all node/routing/ReAct implementations for Graph 2.

    This class does not build or own the `StateGraph` -- it just needs
    the same collaborators the graph used to construct directly
    (checkpoints, ticket_manager, hitl_manager, failure_node, hitl_node,
    rag), handed to it by `Graph2Warranty.__init__`.
    """

    # ---- Constrained ReAct config for DETERMINE_RESPONSIBILITY --------
    #
    # "Constrained" here means two things, both enforced by
    # `_react_parse_action`:
    #   1. The action space is a fixed, closed set (REACT_ALLOWED_ACTIONS)
    #      -- the model cannot invent a new tool name.
    #   2. Every turn must be a single JSON object matching a fixed
    #      schema -- free text, multiple actions, or missing fields are
    #      all rejected and either repaired once or treated as a failed
    #      step (fail-safe: falls back to ambiguous -> HITL).
    #
    REACT_RETRIEVE_LOGS = "retrieve_logs"
    REACT_RETRIEVE_INSPECTION = "retrieve_inspection"
    REACT_FINALIZE = "finalize"
    REACT_ALLOWED_ACTIONS = (REACT_RETRIEVE_LOGS, REACT_RETRIEVE_INSPECTION, REACT_FINALIZE)
    REACT_VALID_RESPONSIBILITIES = ("company", "client", "unrelated")
    REACT_MAX_STEPS = 4
    REACT_CONFIDENCE_THRESHOLD = 0.6

    def __init__(
        self,
        checkpoints: CheckpointManager,
        ticket_manager: TicketManager,
        hitl_manager: HitlManager,
        failure_node: FailureNode,
        hitl_node: HitlNode,
        rag: AgenticRAG,
    ) -> None:
        self.checkpoints = checkpoints
        self.ticket_manager = ticket_manager
        self.hitl_manager = hitl_manager
        self.failure_node = failure_node
        self.hitl_node = hitl_node
        self.rag = rag

    # ---- helpers ---------------------------------------------------

    def _checkpoint(self, state: Graph2State, node_name: str, reason: str) -> Graph2State:
        """Mark `node_name` complete and persist a checkpoint."""
        completed = list(state.get("completed_nodes", []))
        if node_name not in completed:
            completed.append(node_name)
        state["completed_nodes"] = completed

        self.checkpoints.save(
            run_id=state["run_id"],
            node_name=node_name,
            state=dict(state),
            reason=reason,
            metadata={},
        )
        return state

    def _resume_info(self, state: Graph2State) -> ResumeInfo:
        return get_resume_info(state["run_id"], self.checkpoints)

    # ---- node implementations --------------------------------------

    def _n_intake_complaint(self, state: Graph2State) -> Graph2State:
        if should_skip(INTAKE_COMPLAINT, self._resume_info(state)):
            return state

        state["status"] = "running"
        # `complaint` is expected to already be populated by whatever
        # entrypoint created the run (client-facing form / call center).
        state.setdefault("complaint", {})

        return self._checkpoint(state, INTAKE_COMPLAINT, "complaint intake recorded")

    def _n_link_to_original_log(self, state: Graph2State) -> Graph2State:
        if should_skip(LINK_TO_ORIGINAL_LOG, self._resume_info(state)):
            return state

        vehicle_id = state["vehicle_id"]
        complaint_text = state.get("complaint", {}).get("description", "")

        # RAG here is just a retrieval helper over tuning_logs +
        # episodic_memories for this vehicle -- it is not the thing
        # deciding fault.
        query = (
            f"Original tuning log and episodic memory history for vehicle "
            f"{vehicle_id}. Client now reports: {complaint_text}"
        )
        result = self.rag.answer(query)

        state["original_log_summary"] = result.answer
        state["original_log_sources"] = [r.doc_id for r in result.retrieved]
        state["status"] = "running"

        return self._checkpoint(state, LINK_TO_ORIGINAL_LOG, "linked to original tuning log via RAG")

    def _n_schedule_inspection(self, state: Graph2State) -> Graph2State:
        if should_skip(SCHEDULE_INSPECTION, self._resume_info(state)):
            return state

        # Scheduling itself is a side-effecting call to an external
        # system (workshop calendar) -- assumed to happen in `work()`.
        # We do not know the inspection *result* yet; that only arrives
        # through `submit_inspection_result()`.
        state["inspection_scheduled"] = True
        state["inspection_result"] = None
        state["status"] = "waiting_inspection"

        return self._checkpoint(state, SCHEDULE_INSPECTION, "inspection scheduled, awaiting physical inspection")

    def _route_after_schedule(self, state: Graph2State) -> str:
        if state.get("inspection_result") is None:
            return END
        return EVALUATE_INSPECTION

    def _n_evaluate_inspection(self, state: Graph2State) -> Graph2State:
        if should_skip(EVALUATE_INSPECTION, self._resume_info(state)):
            return state

        def work() -> dict[str, Any]:
            result = state.get("inspection_result") or {}
            if result.get("status") == "inconclusive":
                # Don't just retry the same inspection over and over --
                # this needs a ticket / management call (e.g. goodwill
                # compensation), not another automated pass.
                raise InconclusiveInspection(
                    f"Inspection inconclusive for run {state['run_id']}: "
                    f"{result.get('notes', '')}"
                )
            state["status"] = "running"
            return state

        # FailureNode.run() returns the (mutated) state on success. On
        # failure it always ends by raising FailurePaused (via
        # TicketManager.capture_failure) -- it never returns in that
        # case. That exception propagates straight out of this node,
        # out of graph.invoke(), out of Graph2Warranty._invoke():
        # callers of start()/submit_inspection_result() must catch
        # FailurePaused and hold on to its .ticket_id / .checkpoint_id
        # to resume later via resume_after_ticket_resolution().
        updated = self.failure_node.run(
            run_id=state["run_id"],
            node_name=EVALUATE_INSPECTION,
            state=dict(state),
            work=work,
        )
        state.update(updated)

        return self._checkpoint(state, EVALUATE_INSPECTION, "inspection result evaluated")

    def _route_after_evaluate_inspection(self, state: Graph2State) -> str:
        result = state.get("inspection_result") or {}
        if result.get("status") == "resolved_via_ticket":
            return AWAIT_CLIENT_DECISION
        return DETERMINE_RESPONSIBILITY

    # ---- DETERMINE_RESPONSIBILITY: Constrained ReAct -----------------
    #
    #   think --(action)--> {retrieve_logs, retrieve_inspection} --> observe --> think ...
    #                    \-->  finalize --> (responsibility, ambiguous)
    #
    # Bounded by REACT_MAX_STEPS. Every step's model output is parsed by
    # `_react_parse_action`, which enforces the fixed schema/action set;
    # anything that doesn't validate gets one repair attempt and then
    # fails safe to "ambiguous" (routes to SENIOR_REVIEW_HITL) rather
    # than guessing or looping forever.

    def _react_parse_action(self, raw_text: str) -> dict[str, Any] | None:
        """Strictly parse a single constrained-ReAct action. Expects a
        JSON object with exactly the keys {"thought", "action",
        "action_input"} where `action` is one of REACT_ALLOWED_ACTIONS.
        Anything else (extra/unknown actions, missing fields, malformed
        JSON, free text) is treated as invalid."""
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None
        if parsed.get("action") not in self.REACT_ALLOWED_ACTIONS:
            return None
        if "thought" not in parsed or "action_input" not in parsed:
            return None
        if not isinstance(parsed.get("action_input"), dict):
            return None
        return parsed

    def _react_observe(self, action: str, action_input: dict[str, Any], state: Graph2State) -> str:
        """Execute exactly one of the two retrieval tools. This is the
        entire action space available to the loop besides `finalize` --
        it is not free-form tool use, just these two RAG queries."""
        vehicle_id = state["vehicle_id"]

        if action == self.REACT_RETRIEVE_LOGS:
            focus = action_input.get("focus", "")
            query = (
                f"Tuning log / episodic memory detail for vehicle {vehicle_id}. "
                f"Follow-up focus: {focus or 'general history'}. "
                f"Already known summary: {state.get('original_log_summary', '')}"
            )
            result = self.rag.answer(query)
            existing_sources = state.get("original_log_sources", [])
            state["original_log_sources"] = list(
                dict.fromkeys(existing_sources + [r.doc_id for r in result.retrieved])
            )
            return result.answer

        if action == self.REACT_RETRIEVE_INSPECTION:
            inspection = state.get("inspection_result") or {}
            focus = action_input.get("focus", "")
            query = (
                f"Workshop inspection finding for vehicle {vehicle_id}: "
                f"status={inspection.get('status')}, notes={inspection.get('notes', '')}. "
                f"Follow-up focus: {focus or 'root cause detail'}"
            )
            result = self.rag.answer(query)
            return result.answer

        raise ValueError(f"_react_observe called with non-actionable action: {action!r}")

    def _run_responsibility_react(self, state: Graph2State) -> tuple[str | None, bool, list[dict[str, Any]]]:
        """Runs the bounded constrained-ReAct loop and returns
        (responsibility, ambiguous, trace). `trace` is the full
        thought/action/observation history -- kept in state so a senior
        reviewer at SENIOR_REVIEW_HITL (or a ticket) can see exactly how
        the agent got there."""
        inspection = state.get("inspection_result") or {}
        trace: list[dict[str, Any]] = []
        history_text = ""

        for step_idx in range(self.REACT_MAX_STEPS):
            prompt = (
                "You are investigating warranty responsibility for a post-tune "
                "comeback. Take exactly ONE action per turn, and it must be one "
                f"of: {', '.join(self.REACT_ALLOWED_ACTIONS)}. "
                "Reply with ONLY a single JSON object, no other text: "
                '{"thought": "...", "action": "<one of the allowed actions>", '
                '"action_input": {...}}. '
                'If action is "finalize", action_input must be exactly '
                '{"responsibility": "company"|"client"|"unrelated"|"ambiguous", '
                '"confidence": <0-1>, "reasoning": "..."}. '
                f"Vehicle inspection: status={inspection.get('status')}, "
                f"notes={inspection.get('notes', '')}. "
                f"Original tuning history: {state.get('original_log_summary', '')}. "
                f"Steps taken so far:\n{history_text or '(none)'}"
            )

            result = self.rag.answer(prompt)
            parsed = self._react_parse_action(result.answer)

            if parsed is None:
                # One repair attempt, echoing back what failed to parse.
                repair_prompt = prompt + (
                    "\n\nYour previous reply could not be parsed as the "
                    f"required JSON action. Previous reply: {result.answer}\n"
                    "Reply again with ONLY the JSON object described above."
                )
                repair_result = self.rag.answer(repair_prompt)
                parsed = self._react_parse_action(repair_result.answer)

            if parsed is None:
                trace.append(
                    {
                        "step": step_idx,
                        "thought": None,
                        "action": None,
                        "action_input": None,
                        "observation": "unparseable model output; ReAct loop aborted, failing safe to ambiguous",
                    }
                )
                return None, True, trace

            action = parsed["action"]
            action_input = parsed["action_input"]
            thought = parsed.get("thought", "")

            if action == self.REACT_FINALIZE:
                responsibility = action_input.get("responsibility")
                confidence = action_input.get("confidence")
                trace.append(
                    {
                        "step": step_idx,
                        "thought": thought,
                        "action": action,
                        "action_input": action_input,
                        "observation": None,
                    }
                )

                if responsibility == "ambiguous" or responsibility not in self.REACT_VALID_RESPONSIBILITIES:
                    return (
                        responsibility if responsibility in self.REACT_VALID_RESPONSIBILITIES else None,
                        True,
                        trace,
                    )

                # Low confidence is treated the same as an explicit
                # "ambiguous" finalize -- goes to SENIOR_REVIEW_HITL.
                ambiguous = isinstance(confidence, (int, float)) and confidence < self.REACT_CONFIDENCE_THRESHOLD
                return responsibility, ambiguous, trace

            observation = self._react_observe(action, action_input, state)
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": action,
                    "action_input": action_input,
                    "observation": observation,
                }
            )
            history_text += (
                f"\n- thought: {thought}\n  action: {action}({action_input})\n  observation: {observation}\n"
            )

        # Exhausted the step budget without a finalize action -- fail
        # safe to ambiguous rather than silently guessing.
        trace.append(
            {
                "step": self.REACT_MAX_STEPS,
                "thought": None,
                "action": None,
                "action_input": None,
                "observation": f"max ReAct steps ({self.REACT_MAX_STEPS}) reached without finalize; failing safe to ambiguous",
            }
        )
        return None, True, trace

    def _n_determine_responsibility(self, state: Graph2State) -> Graph2State:
        if should_skip(DETERMINE_RESPONSIBILITY, self._resume_info(state)):
            return state

        responsibility, ambiguous, trace = self._run_responsibility_react(state)

        state["responsibility"] = responsibility
        state["responsibility_ambiguous"] = ambiguous
        state["responsibility_react_trace"] = trace
        state["status"] = "running"

        return self._checkpoint(state, DETERMINE_RESPONSIBILITY, "responsibility determined via constrained ReAct")

    def _route_after_responsibility(self, state: Graph2State) -> str:
        if state.get("responsibility_ambiguous"):
            return SENIOR_REVIEW_HITL
        return AWAIT_CLIENT_DECISION

    def _n_senior_review_hitl(self, state: Graph2State) -> Graph2State:
        resume_info = self._resume_info(state)

        if should_skip(SENIOR_REVIEW_HITL, resume_info):
            # We only get here on a resumed invoke where
            # resume_after_hitl_approval() already handled the decision
            # before re-invoking the graph: an approval merged
            # `hitl_decision` into the state and cleared the ambiguity
            # flag; a rejection never reaches here at all -- it opens a
            # ticket instead (see resume_after_hitl_approval). So by the
            # time this branch runs, `responsibility` is already final.
            decision = state.get("hitl_decision")
            if decision is not None and decision.get("approved"):
                state["responsibility_ambiguous"] = False
                state["status"] = "running"
            return state

        # Not yet reviewed. Mark the node complete *before* pausing, so
        # that after the admin decides and we resume, should_skip()
        # treats this node as done and lets the (now decision-carrying)
        # state flow straight through to AWAIT_CLIENT_DECISION.
        state["status"] = "waiting_hitl"
        completed = list(state.get("completed_nodes", []))
        completed.append(SENIOR_REVIEW_HITL)
        state["completed_nodes"] = completed

        # HitlNode.run() -> HitlManager.require_decision() ALWAYS raises
        # HitlPaused after checkpointing this exact state and creating
        # an approval request. It never returns normally. Callers of
        # start()/submit_inspection_result() must catch HitlPaused and
        # hold on to its .request_id / .checkpoint_id to resume later
        # via resume_after_hitl_approval().
        self.hitl_node.run(
            run_id=state["run_id"],
            state=dict(state),
            action={
                "type": "confirm_responsibility",
                "candidate": state.get("responsibility"),
                # Full think/act/observe trail from the constrained
                # ReAct loop, so the reviewer sees *why* the agent
                # landed here instead of just the raw candidate value.
                "react_trace": state.get("responsibility_react_trace", []),
            },
            reason="Inspection evidence is ambiguous; needs senior sign-off on responsibility.",
        )
        raise AssertionError("unreachable: HitlManager.require_decision() always raises HitlPaused")

    def _n_await_client_decision(self, state: Graph2State) -> Graph2State:
        if should_skip(AWAIT_CLIENT_DECISION, self._resume_info(state)):
            return state

        if state.get("client_decision") is None:
            state["status"] = "waiting_client"
            return self._checkpoint(state, AWAIT_CLIENT_DECISION, "waiting on client decision")

        state["status"] = "running"
        return self._checkpoint(state, AWAIT_CLIENT_DECISION, f"client decision recorded: {state['client_decision']}")

    def _route_after_client(self, state: Graph2State) -> str:
        if state.get("client_decision") is None:
            return END
        return COMPLETE

    def _n_complete(self, state: Graph2State) -> Graph2State:
        if should_skip(COMPLETE, self._resume_info(state)):
            return state

        state["status"] = "completed"
        state = self._checkpoint(state, COMPLETE, "investigation complete")
        self.checkpoints.mark_run_finished(state["run_id"], status="completed")
        return state