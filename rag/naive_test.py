from rag import naive_rag
from rag.naive_rag import NaiveRAG
from rag.hybrid_rag import HybridRAG


def main():
    rag = naive_rag.NaiveRAG()

    query = "What is the emissions disclosure policy for vehicle remapping?"

    result = rag.answer(query)

    print("=" * 70)
    print("NAIVE RAG TEST")
    print("=" * 70)

    print("\nQuestion:")
    print(result.query)

    print("\nRetrieved Documents:")

    for i, doc in enumerate(result.retrieved, start=1):
        print(f"\nDocument {i}")
        print(f"Doc ID : {doc.doc_id}")
        print(f"Type   : {doc.metadata.get('doc_type')}")
        print(f"Distance : {doc.distance:.4f}")

    print("\nGenerated Answer:")
    print(result.answer)

    print("\nMetrics")
    print(f"Prompt Tokens      : {result.prompt_tokens}")
    print(f"Completion Tokens  : {result.completion_tokens}")
    print(f"Total Tokens       : {result.total_tokens}")
    print(f"Retrieval Latency  : {result.retrieval_latency_s:.3f}s")
    print(f"Generation Latency : {result.generation_latency_s:.3f}s")
    print(f"Total Latency      : {result.total_latency_s:.3f}s")


if __name__ == "__main__":
     main()