"""
Script to test Similarity Search & Metadata Filtering in ChromaDB.
"""
from rag import config as cfg
from rag.embeddings import get_embedder
from rag.vector_store import VectorStore

def run_test():
    print("=" * 60)
    print(" Testing Vector Search & Metadata Filtering")
    print("=" * 60)

    print("\n[1] Connecting to ChromaDB & Loading Embedder...")
    embedder = get_embedder()
    store = VectorStore()
    
    total_docs = store.count()
    print(f"✓ Connected successfully. Total chunks stored: {total_docs}")

    # 2.(Basic Semantic Search)
   
    query_1 = "What is the emissions disclosure policy for vehicle remapping?"
    print(f"\n[2] Executing Basic Search for Query:\n    -> '{query_1}'")

    query_vector_1 = embedder.embed_one(query_1)
      
    results_1 = store.search(query_vector_1, top_k=2)

    print("\n--- Basic Search Results ---")
    for i, (doc, meta) in enumerate(zip(results_1["documents"][0], results_1["metadatas"][0])):
        print(f"\n Result #{i+1}:")
        print(f"   • Doc ID   : {meta.get('doc_id')}")
        print(f"   • Doc Type : {meta.get('doc_type')}")
        print(f"   • Snippet  : {doc[:120].strip()}...")

   
    #(Metadata Filtering Search)
    #(service_bulletin)
    filter_query = "carbon buildup on intake valves"
    filter_condition = {"doc_type": "service_bulletin"}
    
    print(f"\n[3] Executing Search with Metadata Filter:")
    print(f"    -> Query: '{filter_query}'")
    print(f"    -> Filter: {filter_condition}")

    query_vector_2 = embedder.embed_one(filter_query)
    
   
    results_2 = store.search_with_filter(
        query_vector_2, 
        metadata_filter=filter_condition, 
        top_k=2
    )

    print("\n--- Filtered Search Results ---")
    for i, (doc, meta) in enumerate(zip(results_2["documents"][0], results_2["metadatas"][0])):
        print(f"\n Filtered Result #{i+1}:")
        print(f"   • Doc ID   : {meta.get('doc_id')}")
        print(f"   • Doc Type : {meta.get('doc_type')}")
        print(f"   • Snippet  : {doc[:120].strip()}...")


if __name__ == "__main__":
    run_test()

# Test retriever 
# TEst Done
# from rag.retriever import VectorRetriever

# retriever = VectorRetriever()

# print("=" * 60)
# print("Testing Retriever")
# print("=" * 60)

# results = retriever.retrieve(
#     "What is the emissions disclosure policy?"
# )

# for i, r in enumerate(results, 1):

#     print()

#     print(f"Result #{i}")

#     print("Doc ID :", r.doc_id)

#     print("Type   :", r.metadata.get("doc_type"))

#     print("distance  :", r.distance)

#     print(r.text[:250])