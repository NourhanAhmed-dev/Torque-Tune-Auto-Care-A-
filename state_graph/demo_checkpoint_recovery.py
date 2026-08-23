from __future__ import annotations

"""
to run this demo, first run the following command in a terminal:
$env:CHECKPOINT_DEMO_FIRST_RUN="1"
python -m state_graph.demo_checkpoint_recovery
then 
Remove-Item Env:CHECKPOINT_DEMO_FIRST_RUN
python -m state_graph.demo_checkpoint_recovery
"""
import json, os, sqlite3, sys
from pathlib import Path
from typing import Any
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.graphs.graph1_multi_supplier.workflow import SourcingInstallGraph
from state_graph.graphs.graph1_multi_supplier.nodes import (
    BuildConfigurationNode, PriceCheckNode, SubstituteCheckNode, SupplierOrderNode, TaskDecompositionNode
)
from state_graph.graphs.graph1_multi_supplier.state import SourcingState
from state_graph.graphs.graph1_multi_supplier.repository import SourcingRepository  # >>> persistence

# Demo Configuration
BASE_DIR = Path(__file__).resolve().parent
TRACE_FILE = BASE_DIR / "execution_trace.log"
DB_PATH = str(BASE_DIR.parent / "db" / "redline.db")  # >>> persistence: single source of truth for the db path
RUN_ID =  "checkpoint-recovery-demo-v2"
KILL_AFTER_NODE = "place_orders"

class DemoFailure:
    def run(self, *, run_id: str, node_name: str, state: SourcingState, work) -> SourcingState:
        return work()

class DemoSupplierClient:
    def place_order(self, supplier: str, part_ids: list[int]) -> dict[str, Any]:
        print(f"[SUPPLIER] place_order(supplier={supplier}, parts={part_ids})")
        return {"order_id": 1002, "quoted_price": 5000.0}

class DemoHitl:
    def run(self, *, run_id: str, state: SourcingState, action: dict[str, Any], reason: str) -> SourcingState:
        return state

def trace(node_name: str, run_id: str) -> None:
    with TRACE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"pid": os.getpid(), "run_id": run_id, "node": node_name}) + "\n")

def build_graph() -> SourcingInstallGraph:
    checkpoint_manager = CheckpointManager(graph_type="graph1_multi_supplier")
    failure, hitl, supplier_client = DemoFailure(), DemoHitl(), DemoSupplierClient()
    repo = SourcingRepository(DB_PATH)

    return SourcingInstallGraph(
        order_node=SupplierOrderNode(client=supplier_client, failure=failure, repo=repo),
        decomposition_node=TaskDecompositionNode(llm=None, rag=None, failure=failure, repo=repo),
        price_check_node=PriceCheckNode(hitl=hitl, repo=repo),
        substitute_check_node=SubstituteCheckNode(hitl=hitl, repo=repo),
        build_config_node=BuildConfigurationNode(failure=failure, db_path=DB_PATH),
        repo=repo,  # >>> persistence
        checkpoint_manager=checkpoint_manager,
    )

def read_trace() -> list[dict[str, Any]]:
    if not TRACE_FILE.exists(): return []
    return [json.loads(line) for line in TRACE_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

def print_trace_summary() -> None:
    rows = read_trace()
    print("\n" + "=" * 70 + "\nEXECUTION TRACE\n" + "=" * 70)
    if not rows:
        print("No execution trace found.")
        return
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["node"]] = counts.get(row["node"], 0) + 1
        print(f"PID={row['pid']}  node={row['node']}")
    print("\nExecution counts:")
    for node, count in counts.items():
        print(f"  {node}: {count}")

def assert_no_reexecution() -> None:
    counts = {row["node"]: read_trace().count(row) for row in read_trace()}
    # Recalculate correctly from trace rows
    counts = {}
    for row in read_trace():
        counts[row["node"]] = counts.get(row["node"], 0) + 1

    assert counts.get("build_configuration", 0) == 1, "build_configuration executed improperly."
    assert counts.get("place_orders", 0) == 1, "place_orders executed improperly."
    print("\n PROOF: build_configuration executed exactly once.")
    print(" PROOF: place_orders executed exactly once.")

def main() -> None:
    first_process = os.getenv("CHECKPOINT_DEMO_FIRST_RUN") == "1"
    print(f"\n{'='*70}\nCHECKPOINT RECOVERY DEMO\n{'='*70}\n")
    print(f"DB         : db/redline.db")
    print(f"TRACE      : {TRACE_FILE}")

    if first_process:
        print("MODE: FIRST RUN\n")
        if TRACE_FILE.exists(): TRACE_FILE.unlink()

        graph = build_graph()
        orig_build, orig_order = graph.build_config_node.run, graph.order_node.run

        def traced_build(*args, **kwargs):
            trace("build_configuration", RUN_ID)
            print("[TRACE] build_configuration EXECUTING")
            return orig_build(*args, **kwargs)

        def traced_order(*args, **kwargs):
            trace("place_orders", RUN_ID)
            print("[TRACE] place_orders EXECUTING")
            return orig_order(*args, **kwargs)

        graph.build_config_node.run, graph.order_node.run = traced_build, traced_order

        orig_save = graph.checkpoint_manager.save
        def save_and_kill(*args, **kwargs):
            result = orig_save(*args, **kwargs)
            node_name = kwargs.get("node_name") or (args[1] if len(args) >= 2 else None)
            print(f"[CHECKPOINT] saved node={node_name}")

            if node_name == KILL_AFTER_NODE:
                print(f"\n{'='*70}\n INTENTIONAL PROCESS KILL\n{'='*70}")
                print(f"Checkpoint for {node_name} was saved first.\nNow killing the worker with os._exit(137)...")
                sys.stdout.flush(); sys.stderr.flush()
                os._exit(137)
            return result

        graph.checkpoint_manager.save = save_and_kill
        state: SourcingState = {"run_id": RUN_ID, "parts_required": [], "orders": {}, "delivered_part_ids": [], "cancelled_part_ids": []}
        
        graph.start_from_preset(run_id=RUN_ID, state=state, preset='stage1_ecu_only')
        raise AssertionError("The process was expected to be killed after place_orders.")

    # RECOVERY / RESTART
    print("MODE: RECOVERY / RESTART\n")
    
    graph = build_graph()
    orig_build, orig_order = graph.build_config_node.run, graph.order_node.run

    def traced_build(*args, **kwargs):
        trace("build_configuration", RUN_ID)
        print("[TRACE] build_configuration EXECUTING")
        return orig_build(*args, **kwargs)

    def traced_order(*args, **kwargs):
        trace("place_orders", RUN_ID)
        print("[TRACE] place_orders EXECUTING")
        return orig_order(*args, **kwargs)

    graph.build_config_node.run, graph.order_node.run = traced_build, traced_order
    state: SourcingState = {"run_id": RUN_ID, "parts_required": [], "orders": {}, "delivered_part_ids": [], "cancelled_part_ids": []}

    print("Restarting with SAME run_id...\n")
    result = graph.start_from_preset(run_id=RUN_ID, state=state, preset='stage1_ecu_only')

    print(f"\n{'='*70}\nRECOVERY RESULT\n{'='*70}\n")
    print("Recovered final state:\n" + json.dumps(result, indent=2, default=str))

    assert_no_reexecution()
    assert result.get("parts_required"), "parts_required was lost during recovery."
    assert result.get("orders"), "orders was lost during recovery."

    print("\n PROOF: parts_required survived the process kill.")
    print(" PROOF: orders survived the process kill.")
    print(f"\n{'='*70}\n🎉 CHECKPOINT RECOVERY TEST PASSED\n{'='*70}\n")
    print_trace_summary()

if __name__ == "__main__":
    main()