from __future__ import annotations

import uuid
from pprint import pprint
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.failure_node import FailureNode
from state_graph.tickets.ticket_manager import FailurePaused, TicketManager
from state_graph.tickets.ticket_service import TicketService


def main() -> None:

    # Setup
    run_id = f"demo-failure-{uuid.uuid4().hex[:8]}"
    node_name = "SupplierOrderNode"

    state = {
        "vehicle_id": 101,
        "part_id": 55,
        "supplier": "Supplier-A",
        "price": 15000,
        "currency": "USD",
        "step": "placing_supplier_order",
    }

    checkpoints = CheckpointManager(graph_type="demo_failure")
    tickets = TicketService()

    manager = TicketManager(
        checkpoints=checkpoints,
        tickets=tickets,
    )

    node = FailureNode(manager)
    # First execution fails.
    # Second execution succeeds.
    attempts = 0
    def supplier_order_work() -> dict:
        nonlocal attempts
        attempts += 1
        print(f"\nExecuting {node_name} (attempt {attempts})...")
        if attempts == 1:
            raise RuntimeError(
                "Supplier API timeout while creating the supplier order."
            )
        print("Supplier API responded successfully.")
        return {
            **state,
            "step": "supplier_order_created",
            "order_id": f"SUP-{uuid.uuid4().hex[:6]}",
            "status": "success",
        }

    print("\n" + "=" * 60)
    print("FAILURE RECOVERY E2E DEMO")
    print("=" * 60)
    print("\nInitial state:")
    pprint(state)

    # 1. First execution -> FAILURE
    try:
        node.run(
            run_id=run_id,
            node_name=node_name,
            state=state,
            work=supplier_order_work,
        )
        raise AssertionError("Expected the first attempt to fail.")
    
    except FailurePaused as exc:
        ticket_id = exc.ticket_id
        checkpoint_id = exc.checkpoint_id
        print("\n[1] FAILURE -> GRAPH PAUSED")
        print("ticket_id:", ticket_id)
        print("checkpoint_id:", checkpoint_id)

    # 2. Verify ticket
    ticket = tickets.get(ticket_id)

    assert ticket["run_id"] == run_id
    assert ticket["node_name"] == node_name
    assert ticket["status"] == "open"
    assert ticket["error_type"] == "RuntimeError"

    print("\n[2] TICKET CREATED")
    pprint(ticket)

    
    # 3. Verify checkpoint
    checkpoint = checkpoints.load(checkpoint_id)

    assert checkpoint.run_id == run_id
    assert checkpoint.node_name == node_name
    assert checkpoint.state == state
    assert checkpoint.reason == "node_failure"

    print("\n[3] CHECKPOINT SAVED")
    pprint(checkpoint)

    # 4. Human investigates and resolves
    tickets.set_status(
        ticket_id,
        "investigating",
        assigned_to="demo-admin",
    )
    resolved_ticket = tickets.resolve(
        ticket_id=ticket_id,
        resolution="Supplier API recovered. Retry is safe.",
    )

    assert resolved_ticket["status"] == "resolved"

    print("\n[4] TICKET RESOLVED")
    print("resolution:", resolved_ticket["resolution"])

    # 5. Resume from checkpoint
    resume = manager.resume_data(ticket_id)

    assert resume["ticket_id"] == ticket_id
    assert resume["checkpoint_id"] == checkpoint_id
    assert resume["state"] == state
    assert resume["resolution"] == resolved_ticket["resolution"]

    print("\n[5] RESUMED FROM CHECKPOINT")
    print("restored state:")
    pprint(resume["state"])

    # 6. Rerun failed node
    print("\n[6] RERUNNING FAILED NODE...")

    recovered_state = node.run(
        run_id=run_id,
        node_name=node_name,
        state=resume["state"],
        work=supplier_order_work,
    )

    # 7. Verify successful continuation
    assert recovered_state["status"] == "success"
    assert recovered_state["step"] == "supplier_order_created"
    assert "order_id" in recovered_state

    print("\n[7] NODE SUCCEEDED")
    pprint(recovered_state)
    print("\n" + "=" * 60)
    print("PASS")
    print("=" * 60)
    print(
        "\nFailure"
        " -> Checkpoint"
        " -> Ticket"
        " -> Investigation"
        " -> Resolution"
        " -> Resume"
        " -> Rerun"
        " -> Success"
    )


if __name__ == "__main__":
    main()