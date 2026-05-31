"""
Phase 3 — PMO Memory Module
Demonstrates: Embeddings, Vector Database, Semantic Search, Context Injection
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.schema import Document

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL")
EMBED_MODEL      = os.getenv("OLLAMA_EMBED_MODEL")
CHROMA_DIR       = os.getenv("CHROMA_DIR")

os.makedirs(CHROMA_DIR, exist_ok=True)


# ── Embedding function ────────────────────────────────────────────────────────

def get_embeddings():
    return OllamaEmbeddings(
        base_url=OLLAMA_BASE_URL,
        model=EMBED_MODEL,
    )


# ── ChromaDB collection ───────────────────────────────────────────────────────

def get_vectorstore():
    return Chroma(
        collection_name="pmo_analyses",
        embedding_function=get_embeddings(),
        persist_directory=CHROMA_DIR,
    )


# ── Store an analysis ─────────────────────────────────────────────────────────

def store_analysis(question: str, answer: str, project_ids: list = None):
    """
    Embeds and stores a question+answer pair in ChromaDB.
    project_ids is optional metadata for filtering later.
    """
    vectorstore = get_vectorstore()

    # The document text combines question and answer so the embedding
    # captures the full semantic meaning of both
    combined_text = f"Question: {question}\n\nAnalysis: {answer}"

    metadata = {
        "question"   : question[:200],
        "timestamp"  : datetime.now().isoformat(),
        "projects"   : json.dumps(project_ids or []),
    }

    doc = Document(page_content=combined_text, metadata=metadata)
    vectorstore.add_documents([doc])

    print(f"  [Memory] Stored analysis ({len(combined_text)} chars)")
    return True


# ── Retrieve relevant past analyses ──────────────────────────────────────────

def retrieve_relevant_analyses(question: str, k: int = 3) -> str:
    """
    Embeds the question and retrieves the k most semantically similar
    past analyses from ChromaDB.
    Returns a formatted string ready to inject into a prompt.
    """
    vectorstore = get_vectorstore()

    # Check how many documents exist before searching
    count = vectorstore._collection.count()
    if count == 0:
        return ""

    # Retrieve top-k similar documents
    # k cannot exceed the number of stored documents
    actual_k = min(k, count)
    docs = vectorstore.similarity_search(question, k=actual_k)

    if not docs:
        return ""

    lines = ["=== Relevant past analyses ==="]
    for i, doc in enumerate(docs, 1):
        ts  = doc.metadata.get("timestamp", "unknown")[:19]
        lines.append(f"\n[Memory {i} — recorded {ts}]")
        lines.append(doc.page_content[:600])
        lines.append("---")

    return "\n".join(lines)


# ── Show memory stats ─────────────────────────────────────────────────────────

def memory_stats() -> dict:
    vectorstore = get_vectorstore()
    count = vectorstore._collection.count()
    return {"total_stored": count, "chroma_dir": CHROMA_DIR}


# ── Clear all memory (useful for testing) ────────────────────────────────────

def clear_memory():
    vectorstore = get_vectorstore()
    vectorstore._collection.delete(
        where={"timestamp": {"$gte": "2000-01-01"}}
    )
    print("  [Memory] All analyses cleared")


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── Memory module self-test ──────────────────────────────")

    print("\n1. Storing three sample analyses...")
    store_analysis(
        question="Which project is at highest risk?",
        answer="PRJ002 Customer Portal 2.0 is at highest risk. SPI=0.64 in week 51. "
               "Budget overrun risk RSK012 is escalated with score 0.52.",
        project_ids=["PRJ002"],
    )
    store_analysis(
        question="How is ERP Modernisation performing on schedule?",
        answer="PRJ001 ERP Modernisation shows mixed schedule performance. "
               "SPI ranged from 0.85 to 1.08 over last 4 weeks. "
               "Regulatory compliance risk RSK003 is escalated.",
        project_ids=["PRJ001"],
    )
    store_analysis(
        question="What are the budget risks across all projects?",
        answer="PRJ001 has budget overrun risk RSK001 with score 0.76 — highest in portfolio. "
               "PRJ002 has RSK012 score 0.52 also escalated. "
               "Recommend immediate financial review for both.",
        project_ids=["PRJ001", "PRJ002"],
    )

    print("\n2. Checking memory stats...")
    stats = memory_stats()
    print(f"   Total stored: {stats['total_stored']}")
    print(f"   Location    : {stats['chroma_dir']}")

    print("\n3. Semantic retrieval test...")
    query = "are there any schedule delays or SPI problems?"
    print(f"   Query: '{query}'")
    result = retrieve_relevant_analyses(query, k=2)
    print(result)

    print("\n── Self-test complete ───────────────────────────────────")