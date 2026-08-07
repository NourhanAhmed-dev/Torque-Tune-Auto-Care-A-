"""
Produces the context-management comparison table (lab deliverable).

Accuracy  = the model, given ONLY the pruned context, answers the final query correctly,
            judged by a fixed one-word LLM judge (NOT a grep on the pruned transcript —
            that would unfairly penalize summarization for rephrasing).
Tokens    = input:  tokens of the pruned context the run consumes.
            output: final-answer tokens + tokens generated into SUMMARY messages.
Latency   = prune + answer wall time (judge excluded: eval overhead, not system cost).

"""
import os
import sys
import time
from dotenv import load_dotenv
from dataclasses import dataclass
from google import genai
from google.genai.errors import ClientError

from . import observation_masking, recursive_summary, sliding_window, zone_pruning
from .recursive_summary import gemini_summarizer
from .schema import TurnType
from .test_cases import BURIAL_CASES, CRITICAL_FACT, QUERY
from .utils import count_tokens, timed, transcript_tokens


load_dotenv()   

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

ANSWER_PROMPT = ("Answer using ONLY the context below. If it lacks the needed detail, "
                 "say you don't know.\n\nContext:\n{context}\n\nQuestion: {query}")
JUDGE_PROMPT = ("Grade the answer against the expected fact. Reply with exactly one word: "
                "CORRECT or WRONG.\nExpected fact: {fact}\nQuestion: {query}\nAnswer: {answer}")

STRATEGIES = {
    "Sliding window (last 10 turns)": lambda t, s: sliding_window.prune(t, window_size=10),
    "Observation masking (keep last 3)": lambda t, s: observation_masking.prune(t, keep_last_n_tool_outputs=3),
    "Recursive summarization (every 15 turns)": lambda t, s: recursive_summary.prune(t, chunk_size=15, summarizer=s),
    "Zone-based pruning (4 zones)": lambda t, s: zone_pruning.prune(t, summarizer=s),
}


@dataclass
class Row:
    name: str
    correct: int = 0
    in_tok: float = 0.0
    out_tok: float = 0.0
    secs: float = 0.0
    n: int = 0


def _answer(client, pruned, query):
    context = "\n".join(f"[{m.role.value}] {m.content}" for m in pruned)
    return client.models.generate_content(
        model=MODEL, contents=ANSWER_PROMPT.format(context=context, query=query)).text.strip()


def _judge(client, answer):
    v = client.models.generate_content(model=MODEL, contents=JUDGE_PROMPT.format(
        fact=CRITICAL_FACT, query=QUERY, answer=answer)).text.strip()
    return v.upper().startswith("CORRECT")


def evaluate_strategy(name, prune_fn, client, summarizer, cases):
    row = Row(name)
    for case_idx, case in enumerate(cases):
        pruned, t_prune = timed(prune_fn, case, summarizer)
        
        # Retry logic for answer call
        answer = None
        for attempt in range(3):
            try:
                answer, t_ans = timed(_answer, client, pruned, QUERY)
                break
            except ClientError as e:
                if "429" in str(e) and attempt < 2:
                    wait_time = 60  
                    print(f"  Rate limit hit on case {case_idx+1}/{len(cases)}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
        
        # Retry logic for judge call
        judge_result = False
        for attempt in range(3):
            try:
                judge_result = _judge(client, answer)
                break
            except ClientError as e:
                if "429" in str(e) and attempt < 2:
                    wait_time = 60
                    print(f"  Rate limit hit during judge, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
        
        row.correct += judge_result
        row.in_tok += transcript_tokens(pruned)
        row.out_tok += count_tokens(answer) + sum(
            count_tokens(m.content) for m in pruned if m.role == TurnType.SUMMARY)
        row.secs += t_prune + t_ans
        row.n += 1
        
        # Delay to avoid hitting rate limits 
        print(f"  {name}: case {case_idx+1}/{len(cases)} done")
        time.sleep(5)  # 5 sec
    return row


def markdown(rows):
    lines = ["| Strategy | Detail recalled | Avg input tokens/run | Avg output tokens/run | Avg latency |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.name} | {r.correct}/{r.n} | {r.in_tok / r.n:,.0f} "
                     f"| {r.out_tok / r.n:,.0f} | {r.secs / r.n:.1f}s |")
    return "\n".join(lines)


def main():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY not found")
    client = genai.Client(api_key=key)
    summarizer = gemini_summarizer(client)
    cases = BURIAL_CASES[:1] if "--smoke" in sys.argv else BURIAL_CASES
    rows = [evaluate_strategy(n, fn, client, summarizer, cases) for n, fn in STRATEGIES.items()]
    table = markdown(rows)
    print(table)
    with open("context_eval/comparison_table.md", "w") as f:
        f.write(table + "\n")


if __name__ == "__main__":
    main()