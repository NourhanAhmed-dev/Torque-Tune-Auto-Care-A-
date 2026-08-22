"""Run every planning method over the frozen suite and emit the comparison table."""
from __future__ import annotations

import argparse, asyncio, json, logging, os, sys, time
from pathlib import Path

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "planning_toolkit")):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from planning_toolkit.planning_lab.models import EnvironmentFeedback, PlanningRequest
from planning_toolkit.planning_lab.algorithms import (
    Environment, decompose_goal, dynamic_decomposition, execute_plan, final_output,
    reflect_and_refine, reflexion)
# Domain-adapted entry points — these build the RELEASE/HOLD/ESCALATE-aware
# prompt (client/vehicle/tech/appointment framing, "do not invent evidence")
# before calling into the toolkit's generic search loop. Importing straight
# from the submodules so this doesn't depend on the algorithms package's
# __init__.py re-exporting them.
from planning_toolkit.planning_lab.algorithms.plan_and_solve import plan_job
from planning_toolkit.planning_lab.algorithms.tree_of_thoughts import evaluate_decisions
from planning_toolkit.planning_lab.algorithms.lats import run_lats
from planning.torque_tune_environment import PlanningContext, TorqueTuneEnvironment
from planning_eval.test_cases import CASES

IN_PRICE, OUT_PRICE = 0.10 / 1e6, 0.40 / 1e6  # flash-tier $/token
TRACE_DIR = PROJECT_ROOT / "planning_eval" / "artifacts"


class CountingLLM:
    """Counts calls/tokens and paces requests under the free-tier limit."""

    _last_call = 0.0
    _min_delay = 4.0  # 15 req/min per model on the free tier

    def __init__(self, inner):
        self.inner, self.calls, self.tokens = inner, 0, 0

    def _rate_limit(self):
        elapsed = time.time() - CountingLLM._last_call
        if elapsed < CountingLLM._min_delay:
            time.sleep(CountingLLM._min_delay - elapsed)
        CountingLLM._last_call = time.time()

    @staticmethod
    def _extract_text(out) -> str:
        content = getattr(out, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
        return str(content) if content is not None else ""

    @staticmethod
    def _usage(out, prompt_text: str, response_text: str) -> int:
        meta = getattr(out, "usage_metadata", None)
        used = 0
        if isinstance(meta, dict):
            used = (meta.get("input_tokens") or 0) + (meta.get("output_tokens") or 0)
        elif meta is not None:
            used = getattr(meta, "input_tokens", 0) + getattr(meta, "output_tokens", 0)
        return used or max(1, len(prompt_text) // 4) + max(1, len(response_text) // 4)

    def _retry(self, fn):
        for attempt in range(5):
            try:
                self._rate_limit()
                return fn()
            except Exception as exc:
                wait = 30 if ("429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)) else min(80, 5 * (2 ** attempt))
                print(f"API issue ({str(exc)[:100]}); retry {attempt + 1}/5 in {wait}s", flush=True)
                time.sleep(wait)
        raise RuntimeError("All retries failed")

    def invoke(self, messages, **kw):
        self.calls += 1
        prompt_text = "\n".join(str(m[1]) for m in messages if isinstance(m, tuple))

        def call():
            out = self.inner.invoke(messages, **kw)
            text = self._extract_text(out)
            if not text.strip():
                raise RuntimeError("empty response")
            if not isinstance(out.content, str):
                out.content = text
            self.tokens += self._usage(out, prompt_text, text)
            return out

        return self._retry(call)

    def with_structured_output(self, schema, *, method):
        runnable = self.inner.with_structured_output(schema, method=method)
        outer = self

        class _Counted:
            def invoke(self, m, **kw):
                outer.calls += 1
                prompt_text = "\n".join(str(x[1]) for x in m if isinstance(x, tuple))

                def call():
                    res = runnable.invoke(m, **kw)
                    blob = str(res.model_dump()) if hasattr(res, "model_dump") else str(res)
                    outer.tokens += max(1, len(prompt_text) // 4) + max(1, len(blob) // 4)
                    return res

                return outer._retry(call)

        return _Counted()


UNGROUND = Environment(lambda c: EnvironmentFeedback(success=True, score=0.9, details=["ungrounded: always approves"]))


def _request(case: dict) -> PlanningRequest:
    """Build the same domain-specific request object plan_job/evaluate_decisions/run_lats expect."""
    ctx = case["context"]
    return PlanningRequest(
        request=case["goal"],
        client_id=ctx["client_id"],
        vehicle_id=ctx["vehicle_id"],
        tech_id=ctx["tech_id"],
        appointment_id=ctx.get("appointment_id"),
    )


def run_method(method: str, case: dict, llm, env):
    goal = case["goal"]
    if method.startswith("decomposition"):
        plan = decompose_goal(goal, llm)
        outs = asyncio.run(execute_plan(plan, llm))
        return reflect_and_refine(goal, final_output(plan, outs), llm, env).revised
    if method.startswith("dynamic"):
        history = asyncio.run(dynamic_decomposition(goal, llm))
        return history[-1][1] if history else ""
    if method.startswith("plan_and_solve"):
        return plan_job(_request(case), llm)
    if method.startswith("tree_of_thoughts"):
        thoughts = evaluate_decisions(_request(case), llm, depth=2, beam_width=2)
        return thoughts[0].state if thoughts else ""
    if method.startswith("lats"):
        return run_lats(_request(case), llm, env, iterations=1, n_actions=2).output
    return reflexion(goal, llm, env, max_trials=2, memory_size=2).output


def emit_table(records) -> None:
    by: dict[str, list[dict]] = {}
    for r in records:
        by.setdefault(r["method"], []).append(r)
    lines = ["| Method | Grounded success | Env self-success | Avg calls | Avg tokens | Avg latency s | Est cost/run |",
             "|---|---|---|---|---|---|---|"]
    for m, rs in by.items():
        n = len(rs)
        lines.append(f"| {m} | {sum(r['grounded_success'] for r in rs)}/{n} | {sum(r['env_success'] for r in rs)}/{n} "
                     f"| {sum(r['calls'] for r in rs)/n:.1f} | {int(sum(r['tokens'] for r in rs)/n)} "
                     f"| {sum(r['latency'] for r in rs)/n:.1f} | ${sum(r['cost'] for r in rs)/n:.4f} |")
    table = "\n".join(lines)
    print(table)
    (PROJECT_ROOT / "planning_eval" / "comparison_table.md").write_text(table + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", default=[
        "decomposition_first", "dynamic", "plan_and_solve", "tree_of_thoughts",
        "lats", "reflexion", "lats_ungrounded", "reflexion_ungrounded"])
    ap.add_argument("--resume", action="store_true", help="reuse artifacts from earlier partial runs")
    ap.add_argument("--table-only", action="store_true", help="rebuild the table from artifacts, zero API calls")
    args = ap.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    if args.table_only:
        records = []
        for p in sorted(TRACE_DIR.glob("*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            if rec["method"] in args.methods:
                records.append(rec)
        emit_table(records)
        return

    base = ChatGoogleGenerativeAI(
        google_api_key=os.environ["GEMINI_API_KEY"],
        model=os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        temperature=0.2, max_output_tokens=1024, max_retries=1, timeout=60,
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        },
    )

    records = []
    total = len(CASES) * len(args.methods)
    current = 0
    for case in CASES:
        for method in args.methods:
            current += 1
            path = TRACE_DIR / f"{case['id']}-{method}.json"
            if args.resume and path.exists():
                records.append(json.loads(path.read_text(encoding="utf-8")))
                print(f"[{current}/{total}] {case['id']} x {method} (cached)", flush=True)
                continue
            print(f"[{current}/{total}] {case['id']} x {method} ...", flush=True)
            env = UNGROUND if "ungrounded" in method else Environment(
                TorqueTuneEnvironment(PlanningContext(request_text=case["goal"], **case["context"])).evaluate)
            llm = CountingLLM(base)
            t0 = time.perf_counter()
            final = run_method(method, case, llm, env)
            latency = time.perf_counter() - t0
            scorer = TorqueTuneEnvironment(PlanningContext(request_text=case["goal"], **case["context"]))
            fb = scorer.evaluate(final)
            decision = scorer._decision(final)
            plan_blocking = [d for d in fb.details if not d.startswith("SQLite:")]
            rec = dict(case=case["id"], method=method, decision=decision,
                       grounded_success=decision in case["expected"] and not plan_blocking,
                       env_success=env.evaluate(final).success,
                       calls=llm.calls, tokens=llm.tokens, latency=round(latency, 2),
                       cost=round(llm.tokens * (IN_PRICE + OUT_PRICE), 5))
            records.append(rec)
            path.write_text(json.dumps({**rec, "final_plan": final}, indent=2, ensure_ascii=False), encoding="utf-8")

    emit_table(records)


if __name__ == "__main__":
    main()