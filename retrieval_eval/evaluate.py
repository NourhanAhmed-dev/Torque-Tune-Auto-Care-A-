"""retrieval_eval — produces the retrieval comparison table (PDF deliverable).

Thin wrapper: reuses rag/evaluation.py UNCHANGED, freezes the domain question
set as JSON, and writes comparison_table.md for the README.
Run: python -m retrieval_eval.evaluate
"""
from __future__ import annotations

import json
from pathlib import Path

from rag.evaluation import TEST_QUESTIONS, run_rag_benchmark

HERE = Path(__file__).parent
QUESTIONS_PATH = HERE / "test_questions.json"


def freeze_or_load_questions() -> list:
    """Guardrail: the question set is FROZEN once written — drift fails loud."""
    if QUESTIONS_PATH.exists():
        frozen = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
        assert [q["id"] for q in frozen] == [q["id"] for q in TEST_QUESTIONS], (
            "Frozen question set drifted from rag/evaluation.py — "
            "do not edit either silently."
        )
        return frozen
    QUESTIONS_PATH.write_text(
        json.dumps(TEST_QUESTIONS, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return TEST_QUESTIONS


def write_markdown_table(summary_df) -> str:
    lines = [
        "| Architecture | Accuracy (mean %) | Tokens/query (mean) | Latency/query (mean s) |",
        "|---|---|---|---|",
    ]
    for _, r in summary_df.iterrows():
        lines.append(
            f"| {r['Tested Architecture']} | {r['Accuracy_Mean']} "
            f"| {r['Tokens_Mean']} | {r['Latency_Mean']} |"
        )
    md = "\n".join(lines) + "\n"
    (HERE / "comparison_table.md").write_text(md, encoding="utf-8")
    return md


def main() -> None:
    freeze_or_load_questions()
    df, summary_df = run_rag_benchmark()
    if summary_df.empty:
        print("No successful runs — check quota / ingestion. Table not written.")
        return
    md = write_markdown_table(summary_df)
    print("\nMarkdown table written to retrieval_eval/comparison_table.md:\n")
    print(md)


if __name__ == "__main__":
    main()