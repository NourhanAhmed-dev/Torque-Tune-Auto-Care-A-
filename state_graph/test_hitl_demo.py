from __future__ import annotations

import uuid
from pprint import pprint
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.hitl.approval_service import ApprovalService
from state_graph.hitl.hitl_manager import HitlManager, HitlPaused
from state_graph.hitl_node import HitlNode


def banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def build_components() -> tuple[HitlNode, HitlManager, ApprovalService]:
    checkpoints = CheckpointManager(graph_type="demo_hitl")

    approvals = ApprovalService()

    manager = HitlManager(
        checkpoints=checkpoints,
        approvals=approvals,
    )

    return HitlNode(manager), manager, approvals


def run_scenario() -> None:
    hitl_node, manager, approvals = build_components()

    run_id = f"demo-hitl-{uuid.uuid4().hex[:8]}"

    state = {
        "vehicle_id": 101,
        "part_id": 55,
        "supplier": "Supplier-A",
        "price": 15000,
        "currency": "USD",
        "step": "waiting_for_approval",
    }

    action = {
        "type": "place_supplier_order",
        "part_id": 55,
        "supplier": "Supplier-A",
        "amount": 15000,
        "currency": "USD",
    }

    reason = "Order amount exceeds the approval threshold."

    # 1. GRAPH STARTS
    banner("1. GRAPH STARTED")

    print("run_id:", run_id)
    print("state:")
    pprint(state)

    # The HITL node should NOT return normally.
    #
    # It should:
    #   1. Save a checkpoint
    #   2. Create a HITL request
    #   3. Pause the graph by raising HitlPaused
    try:
        hitl_node.run(
            run_id=run_id,
            state=state,
            action=action,
            reason=reason,
        )

        # If execution reaches here, HITL failed.
        raise AssertionError("HITL did not pause the graph.")

    except HitlPaused as exc:

        # 2. GRAPH PAUSED
        banner("2. GRAPH PAUSED")

        print("exception:", str(exc))
        print("request_id:", exc.request_id)
        print("checkpoint_id:", exc.checkpoint_id)

        # Verify that the HITL request was persisted.
        request = approvals.get_request(exc.request_id)

        print("\nHITL request persisted in DB:")
        pprint(request)

        assert request["status"] == "pending"
        assert request["run_id"] == run_id
        assert request["checkpoint_id"] == exc.checkpoint_id

        # 3. HUMAN / ADMIN DECISION
        banner("3. ADMIN DECISION REQUIRED")

        print("The graph is currently paused.")
        print("A human administrator must decide whether the action")
        print("is allowed to continue.\n")

        print("Approval request:")
        print(f"  Request ID : {exc.request_id}")
        print(f"  Run ID     : {run_id}")
        print(f"  Part ID    : {action['part_id']}")
        print(f"  Supplier   : {action['supplier']}")
        print(f"  Amount     : {action['amount']} {action['currency']}")
        print(f"  Action     : {action['type']}")
        print(f"  Reason     : {reason}")

        print()

        # Ask the real human running the demo for their admin ID.
        admin_id = input("Enter your admin ID: ").strip()

        while not admin_id:
            print("Admin ID cannot be empty.")
            admin_id = input("Enter your admin ID: ").strip()

        # Ask the human for the actual decision.
        while True:
            decision = input(
                "Approve this request? [y/n]: "
            ).strip().lower()

            if decision in {"y", "n"}:
                break

            print("Invalid choice. Please enter 'y' or 'n'.")

        approved = decision == "y"

        # Optional human comment.
        comment = input("Enter your comment: ").strip()

        if not comment:
            comment = (
                "Approved by admin."
                if approved
                else "Rejected by admin."
            )

        # Persist the human's decision.
        result = approvals.decide(
            request_id=exc.request_id,
            admin_id=admin_id,
            approved=approved,
            comment=comment,
        )

        print("\nAdmin decision persisted:")
        pprint(result)

        expected_status = (
            "approved"
            if approved
            else "rejected"
        )

        # Verify the DB state.
        assert result["status"] == expected_status
        assert result["decision"]["approved"] is approved
        assert result["decision"]["admin_id"] == admin_id
        # 4. RESUME FROM CHECKPOINT
        banner("4. RESUME FROM CHECKPOINT")
        resume = manager.resume_data(exc.request_id)
        print("Resume data:")
        pprint(resume)

        # Critical HITL guarantees.
        # We resume from the exact checkpoint that caused the pause.
        assert resume["checkpoint_id"] == exc.checkpoint_id
        # The original state must be preserved.
        assert resume["state"] == state
        # The human decision must be available to the graph.
        assert resume["approved"] is approved
        assert resume["status"] == expected_status
        assert resume["admin_decision"]["admin_id"] == admin_id
        assert (
            resume["admin_decision"]["approved"]
            is approved
        )
        # RESULT
        if approved:
            print(
                "\nRESULT: APPROVED -> "
                "graph may continue to supplier-order execution."
            )
        else:
            print(
                "\nRESULT: REJECTED -> "
                "graph should follow the rejection branch."
            )

        print(
            "\nPASS: checkpoint + request + "
            "human decision + resume all verified."
        )

def main() -> None:
    banner("HITL END-TO-END INTERACTIVE DEMO")
    print(
        "\nThis demo pauses the graph and waits for YOU "
        "to act as the administrator."
    )
    print(
        "\nYou will be asked to:"
        "\n  1. Enter your admin ID"
        "\n  2. Approve or reject the request"
        "\n  3. Enter an optional comment"
    )
    run_scenario()
    banner("HITL DEMO PASSED")
    print(
        "\nHuman-in-the-loop flow completed successfully."
    )

if __name__ == "__main__":
    main()