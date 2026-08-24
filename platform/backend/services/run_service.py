from state_graph import db
from ..deps import get_stack


def list_runs(limit: int = 50):
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM state_graph_runs ORDER BY rowid DESC LIMIT ?", (limit,))]
    cp = get_stack().checkpoints
    for r in rows:
        ck = cp.get_latest(r["run_id"])
        s = ck.state if ck else {}
        r["selected_provider"] = s.get("selected_provider")
        r["rejected_providers"] = s.get("rejected_providers") or []
    return rows