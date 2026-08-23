from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from state_graph import db
from state_graph.failure_node import FailureNode
from state_graph.hitl_node import HitlNode


class ExternalWaitPaused(Exception):
    """waiting for provider"""

    def __init__(self, *, wait_for: str, node_name: str, detail: str = ""):
        self.wait_for = wait_for
        self.node_name = node_name
        super().__init__(f"waiting for {wait_for} at {node_name}: {detail}")


class FleetAuthorizationNode(HitlNode):
    """HITL node type for graph"""


class FleetRescueState(TypedDict, total=False):
    run_id: str
    customer_id: int
    fleet_id: int | None
    vehicle_id: int
    rescue_request: str
    service_type: str
    estimated_cost: float
    authorization_threshold: float
    authorization_required: bool
    authorization_status: str  # approved | rejected 
    admin_decision: dict[str, Any]
    hitl_purpose: str
    provider_candidates: list[dict[str, Any]]
    selected_provider: str | None
    dispatch_id: int | None
    provider_response: str | None  # accepted | rejected 
    rejected_providers: list[str]
    retry_count: int
    rescue_status: str  # completed | cancelled
    cancel_reason: str
    current_state: str
    awaiting: str | None
    error: str | None
    ticket_id: int | None
    completed_nodes: list[str]


ALLOWED_TOOLS = [
    "search_providers",
    "get_provider_location",
    "dispatch_tow_truck",
    "notify_fleet_manager",
]
FORBIDDEN_TOOLS = ["approve_authorization", "change_contract"]
MAX_PROVIDER_RETRIES = 3


class FleetRescueNodes:
    def __init__(
        self,
        *,
        failure_node: FailureNode,
        fleet_auth_node: FleetAuthorizationNode,
        llm_client: Any,
        mcp_client: Any,
        rag_retriever: Any,
    ):
        self.failure_node = failure_node
        self.hitl_node = fleet_auth_node
        self.llm = llm_client
        self.mcp = mcp_client
        self.rag_retriever = rag_retriever

    # ---------- helpers ----------
    def _mcp(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.mcp.call_tool(name, arguments)
        if isinstance(result, dict):
            data = result
        else:
            raw = "".join(
                getattr(i, "text", "") or "" for i in getattr(result, "content", [])
            ).strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
        if not isinstance(data, dict):
            raise ValueError(f"MCP {name} returned non-object: {data!r}")
        if data.get("error"):
            raise RuntimeError(f"MCP {name} failed: {data['error']}")
        return data

    def _llm_json(self, prompt: str) -> Any:
        import time

        for attempt in range(3):
            try:
                text = self.llm.complete(prompt).strip()
                text = re.sub(r"^```(json)?", "", text)
                text = re.sub(r"```$", "", text).strip()
                return json.loads(text)
            except Exception as e:
                if "503" in str(e) or "UNAVAILABLE" in str(e) and attempt < 2:
                    print(f"[LLM] 503 error, retrying in {2**attempt}s...")
                    time.sleep(2**attempt)
                    continue
                raise

    def _pause_hitl(
        self, state, *, purpose: str, reason: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        paused = {**state, "hitl_purpose": purpose}
        self.hitl_node.run(
            run_id=state["run_id"], state=paused, action=action, reason=reason
        )
        return {}  # unreachable: require_decision بيرمي HitlPaused

    # ---------- nodes ----------
    def validating(self, state: FleetRescueState) -> dict[str, Any]:
        if not state.get("rescue_request") or not state.get("vehicle_id"):
            return {
                "rescue_status": "cancelled",
                "cancel_reason": "incomplete request",
                "current_state": "CANCELLED",
            }
        with db.connect() as conn:
            row = conn.execute(
                "SELECT client_id FROM vehicles WHERE vehicle_id = ?",
                (state["vehicle_id"],),
            ).fetchone()
        if row is None or row["client_id"] != state["customer_id"]:
            return {
                "rescue_status": "cancelled",
                "cancel_reason": f"vehicle {state['vehicle_id']} not in customer "
                f"{state['customer_id']} fleet",
                "current_state": "CANCELLED",
            }
        return {"current_state": "VALIDATING"}

    def service_assessment(self, state: FleetRescueState) -> dict[str, Any]:
        def _work():
            d = self._llm_json(f"""You are a fleet-rescue cost estimator.
Estimate the realistic market cost (parts + labor + tow) in USD for EXACTLY
what the user describes — do NOT assume extra work beyond the message.
Guidelines:
- tow / roadside fix (flat tire, battery, lockout): $80-$250
- engine failure or mechanical breakdown (diagnostics + repair only): $300-$900
- explicit full engine / major component replacement: $3,000-$6,000
Reply STRICT JSON only: {{"service_type": str, "estimated_cost": number}}
Request: {state.get('rescue_request', '')}""")
            cost = float(d.get("estimated_cost", 0))
            if cost <= 0:
                raise ValueError(f"assessment returned non-positive cost: {d!r}")
            return {
                "service_type": str(d.get("service_type", "tow")),
                "estimated_cost": cost,
                "current_state": "SERVICE_ASSESSMENT",
            }

        return self.failure_node.run(
            run_id=state["run_id"],
            node_name="service_assessment",
            state=state,
            work=_work,
        )

    def authorization_check(self, state: FleetRescueState) -> dict[str, Any]:
        """RAG addition: from the documents"""

        def _work():
            chunks = (
                self.rag_retriever.search(
                    query=f"fleet rescue contract authorization threshold for customer "
                    f"{state['customer_id']}",
                    filter={"doc_type": "contract", "client_id": state["customer_id"]},
                )
                or []
            )
            chunks = [
                c
                for c in chunks
                if str(c.get("metadata", {}).get("client_id", state["customer_id"]))
                == str(state["customer_id"])
            ]
            if not chunks:
                raise ValueError(
                    f"No contract indexed for customer "
                    f"{state['customer_id']} — cannot decide authorization"
                )
            text = " ".join(c.get("content", "") for c in chunks)
            m = re.search(r"up to\s+\$([\d,]+)", text, re.I)
            if not m:
                raise ValueError(
                    "contract retrieved but no authorization threshold parsed"
                )
            threshold = float(m.group(1).replace(",", ""))
            return {
                "authorization_threshold": threshold,
                "authorization_required": state.get("estimated_cost", 0.0) > threshold,
                "current_state": "AUTHORIZATION_CHECK",
            }

        return self.failure_node.run(
            run_id=state["run_id"],
            node_name="authorization_check",
            state=state,
            work=_work,
        )

    def waiting_for_approval(self, state: FleetRescueState) -> dict[str, Any]:
        """HITL node: arrive here and waiting for approval"""
        if state.get("authorization_status") in ("approved", "rejected"):
            return {"current_state": "WAITING_FOR_APPROVAL"}
        return self._pause_hitl(
            state,
            purpose="cost_approval",
            reason=f"estimated cost ${state.get('estimated_cost')} exceeds contract "
            f"threshold ${state.get('authorization_threshold')}",
            action={
                "estimated_cost": state.get("estimated_cost"),
                "threshold": state.get("authorization_threshold"),
                "customer_id": state["customer_id"],
                "vehicle_id": state["vehicle_id"],
            },
        )

    def provider_search(self, state: FleetRescueState) -> dict[str, Any]:
        """Constrained ReAct"""
        rejected = state.get("rejected_providers", [])

        def _dispatch_args(pid: str) -> dict[str, Any]:
            return {
                "run_id": state["run_id"],
                "provider_id": pid,
                "vehicle_id": state["vehicle_id"],
                "distance_km": 10.0,
                "cost": state.get("estimated_cost", 0.0),
                "location": state.get("rescue_request", "")[:80],
            }

        def _react_prompt(transcript: list[str]) -> str:
            return f"""You are the provider-search agent of a fleet-rescue graph.
The live provider list is already in the transcript below.
You may call ONLY these MCP tools: {ALLOWED_TOOLS}
Tool argument schemas:
- search_providers: {{}}  (NO arguments)
- get_provider_location: {{"provider_id": str}}
- dispatch_tow_truck: {{"provider_id": str, "distance_km": number}}
You must NEVER call: {FORBIDDEN_TOOLS} (approval is a human decision).
Providers that already rejected this run — never pick them: AVOID: {rejected}
Strategy, one tool call per reply:
1) Call get_provider_location for a provider you have not checked yet (skip AVOID).
2) As soon as any checked provider shows status "available": call dispatch_tow_truck with that provider_id and distance_km 10.
NEVER reply {{"done": true}} before a dispatch_tow_truck call succeeded.
Respond STRICT JSON only: {{"tool": "<name>", "arguments": {{...}}}}
Transcript so far:
{chr(10).join(transcript)}"""

        def _work():
            # Perception step — deterministic, whitelisted tool:
            candidates = self._mcp("search_providers", {}).get("providers", [])
            transcript = [
                f"OBSERVATION: {json.dumps({'providers': candidates}, default=str)}"
            ]
            checked: dict[str, dict[str, Any]] = {}
            for _ in range(4):
                decision = self._llm_json(_react_prompt(transcript))
                if decision.get("done"):
                    break
                tool = decision.get("tool")
                if tool in FORBIDDEN_TOOLS or tool not in ALLOWED_TOOLS:
                    raise ValueError(
                        f"Constrained ReAct attempted disallowed tool: {tool}"
                    )
                raw_args = decision.get("arguments", {}) or {}
                if tool == "search_providers":
                    result = self._mcp("search_providers", {})
                    candidates = result.get("providers", [])
                elif tool == "get_provider_location":
                    pid = raw_args.get("provider_id")
                    result = self._mcp("get_provider_location", {"provider_id": pid})
                    checked[pid] = result
                else:  # dispatch_tow_truck
                    args = _dispatch_args(raw_args.get("provider_id"))
                    result = self._mcp(tool, args)
                    return {
                        "provider_candidates": candidates,
                        "selected_provider": args["provider_id"],
                        "dispatch_id": result.get("dispatch_id"),
                        "current_state": "PROVIDER_SEARCH",
                    }
                transcript.append(f"ACTION: {json.dumps(decision)}")
                transcript.append(f"OBSERVATION: {json.dumps(result, default=str)}")
            
            for cand in candidates:
                pid = cand.get("provider_id")
                if pid in rejected:
                    continue
                if (checked.get(pid) or cand).get("status") == "available":
                    args = _dispatch_args(pid)
                    result = self._mcp("dispatch_tow_truck", args)
                    return {
                        "provider_candidates": candidates,
                        "selected_provider": pid,
                        "dispatch_id": result.get("dispatch_id"),
                        "current_state": "PROVIDER_SEARCH",
                    }
            raise ValueError(
                "provider search finished without creating a rescue request"
            )

        return self.failure_node.run(
            run_id=state["run_id"], node_name="provider_search", state=state, work=_work
        )

    def waiting_for_provider(self, state: FleetRescueState) -> dict[str, Any]:
        resp = state.get("provider_response")
        if resp == "accepted":

            def _work():
                self._mcp(
                    "update_vehicle_status",
                    {"dispatch_id": state["dispatch_id"], "status": "en_route"},
                )
                return {"awaiting": None, "current_state": "WAITING_FOR_PROVIDER"}

            return self.failure_node.run(
                run_id=state["run_id"],
                node_name="waiting_for_provider",
                state=state,
                work=_work,
            )
        if resp == "rejected":

            def _close():
                self._mcp(
                    "update_vehicle_status",
                    {"dispatch_id": state["dispatch_id"], "status": "failed"},
                )
                return {}

            self.failure_node.run(
                run_id=state["run_id"],
                node_name="waiting_for_provider",
                state=state,
                work=_close,
            )
            keep = [
                n
                for n in state.get("completed_nodes", [])
                if n not in {"provider_search", "waiting_for_provider"}
            ]
            return {
                "completed_nodes": keep,
                "retry_count": int(state.get("retry_count", 0)) + 1,
                "rejected_providers": state.get("rejected_providers", [])
                + [state.get("selected_provider")],
                "selected_provider": None,
                "dispatch_id": None,
                "provider_response": None,
                "awaiting": None,
            }
        raise ExternalWaitPaused(
            wait_for="provider_response",
            node_name="waiting_for_provider",
            detail=f"dispatch_id={state.get('dispatch_id')}",
        )

    def escalate_provider_failure(self, state: FleetRescueState) -> dict[str, Any]:
        """Stop condition: after 3 iterations open a ticket"""

        def _work():
            raise RuntimeError(
                f"no provider accepted after "
                f"{state.get('retry_count')} attempts; "
                f"rejected={state.get('rejected_providers')}"
            )

        return self.failure_node.run(
            run_id=state["run_id"],
            node_name="escalate_provider_failure",
            state=state,
            work=_work,
        )

    def rescue_in_progress(self, state: FleetRescueState) -> dict[str, Any]:
        def _work():
            self._mcp(
                "update_vehicle_status",
                {"dispatch_id": state["dispatch_id"], "status": "completed"},
            )
            self._mcp(
                "notify_fleet_manager",
                {
                    "run_id": state["run_id"],
                    "message": f"rescue completed for vehicle {state['vehicle_id']} "
                    f"by {state['selected_provider']}",
                },
            )
            return {"rescue_status": "completed", "current_state": "RESCUE_IN_PROGRESS"}

        return self.failure_node.run(
            run_id=state["run_id"],
            node_name="rescue_in_progress",
            state=state,
            work=_work,
        )

    def cancelled(self, state: FleetRescueState) -> dict[str, Any]:
        def _work():
            if state.get("dispatch_id"):
                self._mcp(
                    "update_vehicle_status",
                    {"dispatch_id": state["dispatch_id"], "status": "failed"},
                )
            self._mcp(
                "notify_fleet_manager",
                {
                    "run_id": state["run_id"],
                    "message": f"rescue cancelled: {state.get('cancel_reason') or 'authorization rejected'}",
                },
            )
            return {"rescue_status": "cancelled", "current_state": "CANCELLED"}

        return self.failure_node.run(
            run_id=state["run_id"], node_name="cancelled", state=state, work=_work
        )
