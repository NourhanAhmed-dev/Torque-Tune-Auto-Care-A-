"""
RAG Architecture Evaluation & Benchmarking Suite (Production-Grade).

Evaluates Naive RAG, Hybrid RAG, and Agentic RAG against a domain-specific dataset (Q1 - Q6).

Fixes & Improvements Applied:
- Uses HybridRetriever directly inside AgenticRAG (exposing .retrieve() / .search()).
- Complete benchmark table preservation even on query failure (Status: SUCCESS/FAILED).
- Expanded statistical metrics (Mean, Std, Min, Max).
- Auto-export to CSV ('architecture_benchmark.csv').
- Programmatic best-architecture selection.
"""

from __future__ import annotations

import time
import pandas as pd
import numpy as np
from typing import Any

# Import architectural modules and retrievers
from rag.naive_rag import NaiveRAG
from rag.hybrid_rag import HybridRAG
from rag.agentic_rag import AgenticRAG
from rag.retriever import VectorRetriever, BM25Retriever
from rag.hybrid_rag import HybridRAG, HybridRetriever


# 1. Benchmark Test Dataset (Q1 - Q6)


TEST_QUESTIONS = [
    {
        "id": "Q1",
        "category": "Policy Lookup",
        "favored_architecture": "Naive RAG",
        "query": "What is the warranty disclosure policy for emissions-affecting modifications in Egypt?",
        "expected_keywords": ["warranty", "emissions", "Egypt", "disclosure", "policy"],
    },
    {
        "id": "Q2",
        "category": "Fact Verification",
        "favored_architecture": "Naive RAG",
        "query": "Is the Front-Mount Intercooler an emissions-affecting modification?",
        "expected_keywords": ["Front-Mount Intercooler", "emissions", "modification"],
    },
    {
        "id": "Q3",
        "category": "Exact Identifier Lookup",
        "favored_architecture": "Hybrid RAG",
        "query": "What does SKU-DP-DECAT-102 refer to?",
        "expected_keywords": ["SKU-DP-DECAT-102", "downpipe", "de-cat"],
    },
    {
        "id": "Q4",
        "category": "Exact Identifier Lookup",
        "favored_architecture": "Hybrid RAG",
        "query": "What is the latest guidance in TSB-2026-002?",
        "expected_keywords": ["TSB-2026-002", "guidance"],
    },
    {
        "id": "Q5",
        "category": "Multi-hop Approval Rules",
        "favored_architecture": "Agentic RAG",
        "query": "A customer in the European Union wants to install SKU-ECU-STD-101. What approvals are required before the job can be completed?",
        "expected_keywords": ["European Union", "SKU-ECU-STD-101", "approvals", "emissions"],
    },
    {
        "id": "Q6",
        "category": "Multi-step Action Procedure",
        "favored_architecture": "Agentic RAG",
        "query": "A customer declines to sign the emissions disclosure after requesting a standalone ECU install in the European Union. What should the technician do?",
        "expected_keywords": ["emissions disclosure", "declines", "technician", "stop", "refuse"],
    },
]


# 2. Evaluation Helper Functions

def calculate_keyword_accuracy(answer: str, expected_keywords: list[str]) -> float:
    """Calculates keyword match coverage percentage (0.0 to 100.0)."""
    if not answer:
        return 0.0
    matches = sum(1 for kw in expected_keywords if kw.lower() in answer.lower())
    return round((matches / len(expected_keywords)) * 100, 1)

# 3. Benchmark Execution Loop

def run_rag_benchmark():
    print("=" * 85)
    print("STARTING RAG ARCHITECTURE BENCHMARK EVALUATION (Q1 - Q6)")
    print("=" * 85 + "\n")

    # Instantiate Retrievers & Pipelines correctly
    # Note: Pass HybridRetriever instance to AgenticRAG, NOT the HybridRAG pipeline!
    vector_retriever = VectorRetriever()
    bm25_retriever = BM25Retriever()

    hybrid_retriever = HybridRetriever(
    vector_retriever=vector_retriever,
    bm25_retriever=bm25_retriever,
    )

    naive_rag = NaiveRAG(
    retriever=vector_retriever,
    top_k=3,
)

    hybrid_rag = HybridRAG(
    vector_retriever=vector_retriever,
    bm25_retriever=bm25_retriever,
    top_k=3,
)

    agentic_rag = AgenticRAG(
    retriever=hybrid_retriever,
    top_k=3,
    max_iterations=3,
)
    architectures = {
        "Naive RAG": naive_rag,
        "Hybrid RAG": hybrid_rag,
        "Agentic RAG": agentic_rag,
    }

    benchmark_results = []

    for q_item in TEST_QUESTIONS:
        q_id = q_item["id"]
        q_cat = q_item["category"]
        query_str = q_item["query"]
        favored = q_item["favored_architecture"]
        expected_kws = q_item["expected_keywords"]

        print(f" [{q_id}] ({q_cat}) -> Favors: {favored}")
        print(f"   Query: '{query_str}'\n")

        for arch_name, arch_instance in architectures.items():
            print(f"   ► Running {arch_name}...", end=" ", flush=True)

            try:
                # Execute answer generation
                res = arch_instance.answer(query_str)

                # Extract attributes safely using getattr
                answer_text = getattr(res, "answer", "")
                total_tokens = getattr(res, "total_tokens", 0)
                prompt_tokens = getattr(res, "prompt_tokens", 0)
                completion_tokens = getattr(res, "completion_tokens", 0)
                
                ret_latency = getattr(res, "retrieval_latency_s", 0.0)
                gen_latency = getattr(res, "generation_latency_s", 0.0)
                plan_latency = getattr(res, "planning_latency_s", 0.0)
                tot_latency = getattr(res, "total_latency_s", 0.0)

                # Calculate Accuracy
                accuracy = calculate_keyword_accuracy(answer_text, expected_kws)

                benchmark_results.append({
                    "Question ID": q_id,
                    "Category": q_cat,
                    "Target Architecture": favored,
                    "Tested Architecture": arch_name,
                    "Status": "SUCCESS",
                    "Accuracy (%)": accuracy,
                    "Prompt Tokens": prompt_tokens,
                    "Completion Tokens": completion_tokens,
                    "Total Tokens": total_tokens,
                    "Retrieval Latency (s)": round(ret_latency, 3),
                    "Gen/Plan Latency (s)": round(gen_latency + plan_latency, 3),
                    "Total Latency (s)": round(tot_latency, 3),
                    "Error Message": "",
                })
                print(f"SUCCESS | Acc: {accuracy}% | Tokens: {total_tokens} | Latency: {round(tot_latency, 2)}s")

            except Exception as e:
                print(f"FAILED | Error: {e}")
                # Keep table structural integrity on failure
                benchmark_results.append({
                    "Question ID": q_id,
                    "Category": q_cat,
                    "Target Architecture": favored,
                    "Tested Architecture": arch_name,
                    "Status": "FAILED",
                    "Accuracy (%)": 0.0,
                    "Prompt Tokens": None,
                    "Completion Tokens": None,
                    "Total Tokens": None,
                    "Retrieval Latency (s)": None,
                    "Gen/Plan Latency (s)": None,
                    "Total Latency (s)": None,
                    "Error Message": str(e),
                })

        print("-" * 85)

    # Convert to DataFrame
    df = pd.DataFrame(benchmark_results)

    # -----------------------------------------------------------------
    # Save Detailed Table to CSV
    # -----------------------------------------------------------------
    csv_filename = "architecture_benchmark.csv"
    df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    print(f"\n Full detailed benchmark saved to: '{csv_filename}'")

    # Display Detailed Comparison Table
    print("\n" + "=" * 90)
    print(" BENCHMARK COMPARISON TABLE (All Executions)")
    print("=" * 90)
    display_cols = [
        "Question ID", "Target Architecture", "Tested Architecture",
        "Status", "Accuracy (%)", "Total Tokens", "Total Latency (s)"
    ]
    print(df[display_cols].to_string(index=False))

    # -----------------------------------------------------------------
    # Aggregated Summary Statistics
    # -----------------------------------------------------------------
    print("\n" + "=" * 90)
    print("AGGREGATE SUMMARY STATISTICS (SUCCESSFUL RUNS)")
    print("=" * 90)

    success_df = df[df["Status"] == "SUCCESS"]

    summary_df = success_df.groupby("Tested Architecture").agg(
        Accuracy_Mean=("Accuracy (%)", "mean"),
        Accuracy_Std=("Accuracy (%)", "std"),
        Tokens_Mean=("Total Tokens", "mean"),
        Latency_Mean=("Total Latency (s)", "mean"),
        Latency_Min=("Total Latency (s)", "min"),
        Latency_Max=("Total Latency (s)", "max"),
    ).reset_index()

    # Format numbers for clean terminal display
    summary_df["Accuracy_Mean"] = summary_df["Accuracy_Mean"].round(2)
    summary_df["Accuracy_Std"] = summary_df["Accuracy_Std"].fillna(0.0).round(2)
    summary_df["Tokens_Mean"] = summary_df["Tokens_Mean"].round(1)
    summary_df["Latency_Mean"] = summary_df["Latency_Mean"].round(3)
    summary_df["Latency_Min"] = summary_df["Latency_Min"].round(3)
    summary_df["Latency_Max"] = summary_df["Latency_Max"].round(3)

    print(summary_df.to_string(index=False))
    print("=" * 90)

    # -----------------------------------------------------------------
    # Programmatic Best Architecture Selection
    # -----------------------------------------------------------------
    print("\n" + "=" * 90)
    print(" AUTOMATED ARCHITECTURE SELECTION FOR PRODUCTION")
    print("=" * 90)

    best_arch = summary_df.sort_values(
        by=["Accuracy_Mean", "Latency_Mean"],
        ascending=[False, True]
    ).iloc[0]

    print(f"Recommended Shipping Architecture : {best_arch['Tested Architecture']}")
    print(f"► Mean Accuracy                    : {best_arch['Accuracy_Mean']}%")
    print(f"► Mean Total Latency               : {best_arch['Latency_Mean']}s")
    print(f"► Mean Token Usage                 : {best_arch['Tokens_Mean']} tokens")
    print("=" * 90)

    return df, summary_df


if __name__ == "__main__":
    run_rag_benchmark()