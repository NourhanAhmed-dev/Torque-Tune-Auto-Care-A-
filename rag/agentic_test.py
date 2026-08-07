from rag.agentic_rag import AgenticRAG


def main():
    rag = AgenticRAG()

    query = "What is the emissions disclosure policy for vehicle remapping?"

    result = rag.answer(query)

    print("=" * 70)
    print("AGENTIC RAG TEST")
    print("=" * 70)

    print("\nQuestion:")
    print(query)

    print("\nRetrieved Documents:")

    for i, doc in enumerate(result.retrieved, start=1):
        print(f"\nDocument {i}")
        print(f"Doc ID   : {doc.doc_id}")
        print(f"Type     : {doc.metadata.get('doc_type')}")
        print(f"Distance : {doc.distance:.4f}")

    print("\nGenerated Answer:")
    print(result.answer)

    print("\nMetrics")
    print(f"Prompt Tokens       : {result.prompt_tokens}")
    print(f"Completion Tokens   : {result.completion_tokens}")
    print(f"Total Tokens        : {result.total_tokens}")
    print(f"Retrieval Latency   : {result.retrieval_latency_s:.3f}s")
    print(f"Generation Latency  : {result.generation_latency_s:.3f}s")
    print(f"Total Latency       : {result.total_latency_s:.3f}s")

    # Reasoning loop 
    if result.steps:
        print("\nReasoning Trajectory")

        for i, step in enumerate(result.steps, start=1):
            print("-" * 50)
            print(f"Step {i}")
            print(f"Thought    : {step.thought}")
            print(f"Action     : {step.action}")
            if step.query:
                print(f"Query      : {step.query}")
            if step.observation:
                print(f"Observation: {step.observation}")


if __name__ == "__main__":
    main()
