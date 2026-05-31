# Part 3 — Giving Your Agent Memory

## What We Are Building

Persistent semantic memory using ChromaDB. After every analysis the agent produces, we store it as a vector embedding. Next time a similar question is asked, the system retrieves the most relevant past analyses and injects them into the prompt as context.

By the end of this part the agent will:

- Store every analysis it produces to a local vector database
- Retrieve semantically relevant past analyses before answering
- Reason with memory context injected into the prompt
- Persist memory across process restarts and reboots
- Search by meaning — not keywords

---

## The Problem This Solves

The agent built in Part 2 is stateless. Every run starts from zero.

Run it today:
```
Question: Which project is at highest risk?
Answer: PRJ002 is at highest risk — SPI=0.64, budget overrun escalated.
```

Run it tomorrow with the same question:
```
Question: Which project is at highest risk?
[Agent calls the same tools, does the same reasoning, produces the same answer]
```

It has no memory of yesterday's analysis. No awareness that it already investigated PRJ002. No ability to notice that the situation has changed or stayed the same since last time.

Semantic memory solves this. The agent now builds institutional knowledge with every run.

---

## How Vector Embeddings Work

When you store an analysis, the text is converted into a vector — a list of 768 numbers. Each number captures a dimension of meaning. Similar texts produce similar vectors. Dissimilar texts produce vectors that are far apart in the 768-dimensional space.

```
"PRJ002 has budget overrun risk"
    ↓ nomic-embed-text
[0.12, -0.34, 0.87, 0.03, ..., 0.61]  ← 768 numbers

"financial risks to escalate to CFO"
    ↓ nomic-embed-text
[0.14, -0.31, 0.84, 0.05, ..., 0.58]  ← 768 numbers, very similar
```

When you search, your question becomes a vector and ChromaDB finds the stored vectors closest to it using cosine similarity. This is why searching for "financial risks to escalate to CFO" retrieves the "budget overrun risk" analysis — they are close in meaning even though they share no keywords.

---

## The Store and Retrieve Cycle

```
STORE path:
Agent produces analysis
       ↓
"Question: ... Analysis: ..." combined text
       ↓
nomic-embed-text (Ollama) → 768-dimension vector
       ↓
Vector + text stored in ChromaDB on disk

RETRIEVE path:
New question arrives
       ↓
nomic-embed-text → 768-dimension vector
       ↓
ChromaDB cosine similarity search
       ↓
Top-k most relevant past analyses returned
       ↓
Injected into agent prompt as memory context
       ↓
Agent reasons with accumulated knowledge
```

---

## The Memory Module — `memory/pmo_memory.py`

```python
"""
PMO Memory Module
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

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
EMBED_MODEL     = os.getenv("OLLAMA_EMBED_MODEL")
CHROMA_DIR      = os.getenv("CHROMA_DIR")

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

    # Combine question and answer so the embedding captures
    # the full semantic meaning of both
    combined_text = f"Question: {question}\n\nAnalysis: {answer}"

    metadata = {
        "question"  : question[:200],
        "timestamp" : datetime.now().isoformat(),
        "projects"  : json.dumps(project_ids or []),
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

    # k cannot exceed the number of stored documents
    actual_k = min(k, count)
    docs = vectorstore.similarity_search(question, k=actual_k)

    if not docs:
        return ""

    lines = ["=== Relevant past analyses ==="]
    for i, doc in enumerate(docs, 1):
        ts = doc.metadata.get("timestamp", "unknown")[:19]
        lines.append(f"\n[Memory {i} — recorded {ts}]")
        lines.append(doc.page_content[:600])
        lines.append("---")

    return "\n".join(lines)


# ── Memory stats ──────────────────────────────────────────────────────────────

def memory_stats() -> dict:
    vectorstore = get_vectorstore()
    count = vectorstore._collection.count()
    return {"total_stored": count, "chroma_dir": CHROMA_DIR}


# ── Clear all memory ──────────────────────────────────────────────────────────

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
```

---

## Key Design Decisions Explained

**Why combine question and answer into one document:**
```python
combined_text = f"Question: {question}\n\nAnalysis: {answer}"
```
Embedding only the answer loses context about what was being asked. Embedding only the question loses the richness of the analysis. Combining both means retrieval matches on either the topic being asked about OR the findings produced — whichever is most relevant to the new question.

**Why `actual_k = min(k, count)`:**
```python
actual_k = min(k, count)
```
ChromaDB raises an exception if you request more results than documents stored. On first run the database is empty. This guard means `retrieve_relevant_analyses` safely returns an empty string rather than crashing — which is why the agent in Part 2 handles `memory_context = ""` gracefully.

**Why truncate retrieved content to 600 characters:**
```python
lines.append(doc.page_content[:600])
```
LLM context windows are finite. Injecting full analyses from previous runs would consume tokens needed for the current reasoning loop. 600 characters captures the key findings without crowding out the agent's working memory.

**Why `persist_directory=CHROMA_DIR`:**
ChromaDB with a persist directory writes to `chroma.sqlite3` on disk after every write. Memory survives process restarts, pod restarts, and reboots. Without this, memory exists only in RAM for the duration of the process.

---

## Install the Required Package

```bash
cd ~/pmo-copilot
source venv/bin/activate
pip install langchain-chroma==0.2.4
```

---

## Test the Embedding Connection

Before running the memory module, confirm `nomic-embed-text` is reachable:

```bash
python3 - << 'EOF'
from langchain_ollama import OllamaEmbeddings
from dotenv import load_dotenv
import os

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

embeddings = OllamaEmbeddings(
    base_url=os.getenv("OLLAMA_BASE_URL"),
    model=os.getenv("OLLAMA_EMBED_MODEL"),
)

vector = embeddings.embed_query("Project Alpha is at high risk due to budget overrun")
print(f"Embedding dimensions : {len(vector)}")
print(f"First 5 values       : {[round(v, 4) for v in vector[:5]]}")
print("PASS: nomic-embed-text is working")
EOF
```

Expected:
```
Embedding dimensions : 768
First 5 values       : [0.xxxx, 0.xxxx, 0.xxxx, 0.xxxx, 0.xxxx]
PASS: nomic-embed-text is working
```

---

## Run the Memory Self-Test

```bash
python3 memory/pmo_memory.py
```

Expected output:
```
── Memory module self-test ──────────────────────────────

1. Storing three sample analyses...
  [Memory] Stored analysis (xxx chars)
  [Memory] Stored analysis (xxx chars)
  [Memory] Stored analysis (xxx chars)

2. Checking memory stats...
   Total stored: 3
   Location    : /home/<user>/pmo-copilot/memory/chroma_db

3. Semantic retrieval test...
   Query: 'are there any schedule delays or SPI problems?'
=== Relevant past analyses ===

[Memory 1 — recorded 2026-xx-xx xx:xx:xx]
Question: How is ERP Modernisation performing on schedule?
Analysis: PRJ001 ERP Modernisation shows mixed schedule performance...
---
[Memory 2 — recorded 2026-xx-xx xx:xx:xx]
Question: Which project is at highest risk?
Analysis: PRJ002 Customer Portal 2.0 is at highest risk. SPI=0.64...
---

── Self-test complete ───────────────────────────────────
```

**The critical thing to observe:** The query was `"are there any schedule delays or SPI problems?"` — it retrieved the ERP schedule analysis AND the highest risk analysis (which mentioned SPI). It did NOT retrieve the budget risks analysis. That is semantic search working — matching by meaning, not keywords.

---

## Run the Agent with Memory Active

Now run the agent three times to see memory building up:

**Run 1 — cold start, no memory:**
```bash
python3 agents/pmo_risk_analyst.py "Which project has the worst budget performance?"
```

Watch for: `[Memory] No relevant past analyses — starting fresh`

**Run 2 — same question, memory now has Run 1's analysis:**
```bash
python3 agents/pmo_risk_analyst.py "Which project has the worst budget performance?"
```

Watch for: `[Memory] Injecting relevant past analyses`

The agent skips re-listing all projects and goes straight to the relevant ones. Memory made it more efficient.

**Run 3 — different vocabulary, same topic:**
```bash
python3 agents/pmo_risk_analyst.py "Are there any financial risks I should escalate to the CFO?"
```

Watch for: Memory injecting the budget analysis even though this question uses completely different words — "financial risks", "CFO", "escalate" — compared to what was stored — "worst budget performance".

This is the semantic search proof. Different vocabulary, same meaning, correct retrieval.

---

## Verify Persistence on Disk

```bash
ls -lh ~/pmo-copilot/memory/chroma_db/
```

Expected:
```
-rw-r--r-- 1 <user> <group>  xxxK  chroma.sqlite3
drwxrwxr-x 2 <user> <group>  4.0K  <uuid>/
```

The `chroma.sqlite3` file is the vector store. It survives restarts. Restart the terminal, run the agent again — memory is still there.

---

## Common Failures and Fixes

**`ModuleNotFoundError: langchain_chroma`:**
```bash
pip install langchain-chroma==0.2.4
```

**Embedding hangs or times out:**
```bash
# Confirm nomic-embed-text is available on Ollama
curl http://<windows-laptop-ip>:11434/api/tags | python3 -m json.tool | grep nomic
```
If not listed — pull it: `ollama pull nomic-embed-text` on the Windows laptop.

**`ValueError: k must be <= number of documents`:**
This means the `actual_k = min(k, count)` guard is missing. Confirm your `pmo_memory.py` matches the code above exactly.

**Run 2 still shows "starting fresh":**
The analysis from Run 1 was not stored. Check that `store_analysis` is called at the end of `pmo_risk_analyst.py` and that no exception occurred before it.

---

## Validation Checkpoint

Before proceeding to Part 4, confirm:

```bash
# Self-test passes
python3 memory/pmo_memory.py

# Run 2 shows memory injection
python3 agents/pmo_risk_analyst.py "Which project has the worst budget performance?"
python3 agents/pmo_risk_analyst.py "Which project has the worst budget performance?"

# Semantic retrieval works with different vocabulary
python3 agents/pmo_risk_analyst.py "Are there any financial risks I should escalate to the CFO?"

# ChromaDB persisted to disk
ls -lh memory/chroma_db/chroma.sqlite3
```

All checks passing means memory is working correctly.

---

## What's Next

The agent now remembers past analyses and retrieves them semantically. The next step is building a team of specialist agents — each focused on a specific aspect of PMO analysis — and coordinating them with CrewAI.

→ [Part 4 — Building a Multi-Agent Crew](./04-crew.md)