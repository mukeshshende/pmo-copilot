# Part 2 — Building Your First ReACT Agent

## What We Are Building

A single PMO Risk Analyst agent that reads your CSV data, reasons through it using the ReACT loop, and produces grounded risk assessments citing specific SPI values, risk scores, and dates.

By the end of this part you will have an agent that:

- Autonomously decides which tools to call and in what order
- Reasons through project data step by step
- Produces specific, evidence-based risk assessments
- Recovers gracefully from parsing errors
- Stores analyses in memory for future use
- Sends traces to Langfuse for observability
- Runs entirely via your local Ollama instance

> **Note on memory and observability:** This file imports ChromaDB memory and Langfuse tracing from the start. Memory context will be empty until Part 3 populates it. Langfuse traces will appear once Langfuse is deployed in Part 5. Both are safe to have present now — they degrade gracefully when not yet configured.

---

## How ReACT Works in Practice

The ReACT pattern is the foundation of everything in this system. Understanding it before writing code makes everything else clear.

When you ask the agent a question, it does not answer immediately. Instead it enters a reasoning loop:

```
Question: Which project is at the highest risk right now?

Thought: I should first list all projects to know what exists.
Action: list_all_projects
Action Input: all
Observation: PRJ001 ERP Modernisation (On Track), PRJ002 Customer Portal 2.0 (Off Track)...

Thought: PRJ002 is Off Track. Let me check its recent performance.
Action: get_weekly_status
Action Input: PRJ002
Observation: Week 51 RAG=Red SPI=0.64 CPI=0.67 Open issues=1

Thought: SPI of 0.64 is critically low. Let me check its risks.
Action: get_project_risks
Action Input: PRJ002
Observation: RSK012 Budget overrun Score=0.52 Status=Escalated...

Thought: I now have enough information to answer.
Final Answer: PRJ002 Customer Portal 2.0 is at highest risk...
```

Three things to notice:

1. Nobody told the agent to check PRJ002 first — it inferred from the project list that `Off Track` status warranted investigation
2. Nobody hardcoded the tool call sequence — the agent decided `list → status → risks` based on its reasoning
3. The final answer cites specific data — SPI=0.64, RSK012, Score=0.52 — not vague generalisations

This is the difference between a scripted workflow and an agentic system.

---

## Tool Design — Why Docstrings Matter

LangChain feeds each tool's docstring directly to the LLM as the tool's description. The LLM reads the docstring to decide whether to call the tool and what to pass as input.

Vague docstring:
```python
@tool
def get_status(project_id: str) -> str:
    """Get status."""  # LLM has no idea when to use this
```

Good docstring:
```python
@tool
def get_weekly_status(project_id: str) -> str:
    """
    Returns the last 4 weeks of status data for a project including
    RAG status, SPI, CPI, percent complete, and open issues.
    Input: project_id as a string e.g. PRJ001
    """
```

The docstring is prompt engineering. Write it for the LLM, not for human readers.

---

## The Six PMO Tools — `agents/pmo_tools.py`

All tools live in `pmo_tools.py` so they can be shared between the single agent and the multi-agent crew without duplication.

```python
"""
Shared PMO tools used by all agents.
Each tool reads from CSV files and returns formatted text.
The docstring of each tool is what the LLM reads to decide when to use it.
"""

import os
import pandas as pd
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

DATA_DIR = os.getenv("DATA_DIR")


@tool
def list_all_projects(dummy: str = "") -> str:
    """
    Returns a list of all project IDs and names.
    Use this first if you need to know which projects exist.
    Input: leave empty or pass any string.
    """
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
        lines = ["Available projects:"]
        for _, r in df.iterrows():
            lines.append(f"  {r['project_id']}: {r['project_name']} ({r['status']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing projects: {str(e)}"


@tool
def get_project_summary(project_id: str) -> str:
    """
    Returns basic details for a project: name, domain, budget,
    team size, start date, planned end date, current status.
    Input: project_id e.g. PRJ001
    """
    try:
        df  = pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
        row = df[df["project_id"] == project_id.strip().upper()]
        if row.empty:
            return f"No project found with id {project_id}."
        r = row.iloc[0]
        return (
            f"Project: {r['project_name']} ({r['project_id']})\n"
            f"Domain: {r['domain']}\n"
            f"Budget: ${r['budget']:,}\n"
            f"Team size: {r['team_size']}\n"
            f"Start: {r['start_date']}\n"
            f"Planned end: {r['planned_end_date']}\n"
            f"Status: {r['status']}"
        )
    except Exception as e:
        return f"Error reading project data: {str(e)}"


@tool
def get_weekly_status(project_id: str) -> str:
    """
    Returns the last 4 weeks of status for a project:
    RAG status, SPI, CPI, percent complete, open issues.
    Input: project_id e.g. PRJ001
    """
    try:
        df   = pd.read_csv(os.path.join(DATA_DIR, "weekly_status.csv"))
        proj = df[df["project_id"] == project_id.strip().upper()]
        if proj.empty:
            return f"No weekly status found for {project_id}"
        last4 = proj.tail(4)
        lines = ["Last 4 weeks of status:"]
        for _, r in last4.iterrows():
            lines.append(
                f"  Week {int(r['week_number'])} ending {r['week_ending']}: "
                f"RAG={r['rag_status']} SPI={r['spi']} CPI={r['cpi']} "
                f"Complete={r['percent_complete']}% "
                f"Open issues={int(r['issues_open'])}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading weekly status: {str(e)}"


@tool
def get_project_risks(project_id: str) -> str:
    """
    Returns all open or escalated risks for a project:
    risk type, probability, impact, score, mitigation.
    Input: project_id e.g. PRJ001
    """
    try:
        df   = pd.read_csv(os.path.join(DATA_DIR, "risks.csv"))
        proj = df[
            (df["project_id"] == project_id.strip().upper()) &
            (df["status"].isin(["Open", "Escalated"]))
        ]
        if proj.empty:
            return f"No open risks found for {project_id}"
        lines = [f"Open/Escalated risks for {project_id}:"]
        for _, r in proj.iterrows():
            lines.append(
                f"  [{r['risk_id']}] {r['risk_type']} | "
                f"Prob={r['probability']} Impact={r['impact']} "
                f"Score={r['risk_score']} Status={r['status']}\n"
                f"    Mitigation: {r['mitigation_action']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading risks: {str(e)}"


@tool
def get_milestone_status(project_id: str) -> str:
    """
    Returns all milestones for a project with planned date,
    actual date, status and delay in weeks.
    Input: project_id e.g. PRJ001
    """
    try:
        df   = pd.read_csv(os.path.join(DATA_DIR, "milestones.csv"))
        proj = df[df["project_id"] == project_id.strip().upper()]
        if proj.empty:
            return f"No milestones found for {project_id}"
        lines = [f"Milestones for {project_id}:"]
        for _, r in proj.iterrows():
            delay_note = (
                f" — DELAYED by {int(r['delay_weeks'])} week(s)"
                if r['delay_weeks'] > 0 else ""
            )
            actual_note = (
                f"actual={r['actual_date']}"
                if r['actual_date'] else "not yet completed"
            )
            lines.append(
                f"  [{r['milestone_id']}] {r['milestone_name']}: "
                f"planned={r['planned_date']} {actual_note} "
                f"status={r['status']}{delay_note}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading milestones: {str(e)}"


@tool
def get_portfolio_overview(dummy: str = "") -> str:
    """
    Returns a high-level overview of all projects showing
    their latest RAG status, SPI, CPI and completion percentage.
    Use this to get a portfolio-wide picture quickly.
    Input: leave empty or pass any string.
    """
    try:
        projects = pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
        status   = pd.read_csv(os.path.join(DATA_DIR, "weekly_status.csv"))
        lines = ["Portfolio overview — latest week per project:"]
        for _, p in projects.iterrows():
            pid  = p["project_id"]
            proj = status[status["project_id"] == pid]
            if proj.empty:
                continue
            latest = proj.iloc[-1]
            lines.append(
                f"  {pid} {p['project_name']}: "
                f"RAG={latest['rag_status']} "
                f"SPI={latest['spi']} CPI={latest['cpi']} "
                f"Complete={latest['percent_complete']}% "
                f"Overall status={p['status']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading portfolio data: {str(e)}"
```

> **Why `dummy: str = ""`?** LangChain 0.3.x requires all `@tool` function arguments to be non-optional for correct pydantic validation. Tools that don't need input use `dummy: str = ""` as a placeholder. The LLM can pass any string or an empty string.

---

## The ReACT Prompt Template

The prompt template is what makes the LLM produce parseable `Thought/Action/Observation` output. The exact format matters — LangChain's parser looks for these specific keywords.

LangChain injects these variables automatically:

| Variable | What LangChain injects |
|---|---|
| `{tools}` | Tool names and docstrings |
| `{tool_names}` | Comma-separated list of tool names |
| `{input}` | The user's question |
| `{agent_scratchpad}` | The accumulated Thought/Action/Observation loop |

We inject one additional variable manually:

| Variable | What we inject |
|---|---|
| `{memory_context}` | Relevant past analyses from ChromaDB — empty string in Part 2, populated in Part 3 |

---

## The Single Agent — `agents/pmo_risk_analyst.py`

```python
"""
PMO Risk Analyst Agent
Demonstrates: ReACT loop, Tool Calling, LangChain + Ollama,
              Memory (ChromaDB), Observability (Langfuse)
"""

import os
import sys
import pandas as pd
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool
from langchain.prompts import PromptTemplate

sys.path.insert(0, os.path.expanduser("~/pmo-copilot"))

from memory.pmo_memory import store_analysis, retrieve_relevant_analyses
from observability.pmo_tracing import get_langfuse_callback, trace_agent_run

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

DATA_DIR        = os.getenv("DATA_DIR")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL")

# ── LLM ───────────────────────────────────────────────────────────────────────

llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model=OLLAMA_MODEL,
    temperature=0,
    num_predict=1024,
)

# ── Tools ─────────────────────────────────────────────────────────────────────
# Tools are imported from pmo_tools.py so they can be shared with the crew.
# The four tools below are what the single agent uses.
# get_milestone_status and get_portfolio_overview are available in pmo_tools.py
# and used by the crew agents in Part 4.

from agents.pmo_tools import (
    list_all_projects,
    get_project_summary,
    get_weekly_status,
    get_project_risks,
)

tools = [
    list_all_projects,
    get_project_summary,
    get_weekly_status,
    get_project_risks,
]

# ── ReACT Prompt ──────────────────────────────────────────────────────────────

REACT_PROMPT = PromptTemplate.from_template("""You are a senior PMO Risk Analyst with 15 years of experience.
Your job is to analyse project data and provide clear, actionable risk assessments.

{memory_context}

You have access to the following tools:
{tools}

Use this EXACT format for every response step:

Thought: <your reasoning about what to do next>
Action: <tool name — must be one of [{tool_names}]>
Action Input: <the input to pass to the tool>
Observation: <the tool result will appear here automatically>

When you have enough information to answer, use:

Thought: I now have enough information to answer.
Final Answer: <your complete analysis>

Rules:
- Always start by listing projects if you do not know the project IDs.
- Always check weekly status AND risks before making a risk assessment.
- If past analyses are shown above, reference them where relevant.
- Be specific: cite SPI values, risk scores, and dates.
- End with a clear recommendation.

Begin!

Question: {input}
{agent_scratchpad}""")

# ── Agent ─────────────────────────────────────────────────────────────────────

agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=REACT_PROMPT,
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=10,
    handle_parsing_errors=True,
)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Which project is at the highest risk right now and why?"
    )

    print("\n" + "="*60)
    print("PMO RISK ANALYST AGENT  (with memory + observability)")
    print("="*60)
    print(f"Question: {question}")
    print("="*60 + "\n")

    # Retrieve relevant memory — empty at this stage, populated in Part 3
    memory_context = retrieve_relevant_analyses(question, k=3)
    if memory_context:
        print("[Memory] Injecting relevant past analyses")
    else:
        print("[Memory] No relevant past analyses — starting fresh\n")

    # Langfuse callback — captures every LLM + tool call automatically
    # Traces visible in Langfuse UI after Part 5 deployment
    langfuse_cb = get_langfuse_callback(session_id="single-agent-run")

    result = agent_executor.invoke(
        {
            "input"         : question,
            "memory_context": memory_context,
        },
        config={"callbacks": [langfuse_cb]},
    )

    # Store analysis in memory — used in Part 3
    store_analysis(
        question   = question,
        answer     = result["output"],
        project_ids= [],
    )

    # Manual trace record for Langfuse
    trace_agent_run(
        question   = question,
        answer     = result["output"],
        agent_name = "pmo-risk-analyst",
    )

    print("\n" + "="*60)
    print("FINAL ANSWER")
    print("="*60)
    print(result["output"])
```

---

## Test the Ollama Connection First

Before running the agent, confirm LangChain can reach Ollama:

```bash
cd ~/pmo-copilot
source venv/bin/activate

python3 - << 'EOF'
from langchain_ollama import ChatOllama
from dotenv import load_dotenv
import os

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

llm = ChatOllama(
    base_url=os.getenv("OLLAMA_BASE_URL"),
    model=os.getenv("OLLAMA_MODEL"),
    temperature=0,
)

response = llm.invoke("Reply with exactly three words: Ollama is working")
print("Response:", response.content)
print("PASS: LangChain → Ollama connection confirmed")
EOF
```

Expected:
```
Response: Ollama is working
PASS: LangChain → Ollama connection confirmed
```

Only proceed after this passes.

---

## Run the Agent

```bash
cd ~/pmo-copilot
source venv/bin/activate
python3 agents/pmo_risk_analyst.py
```

This runs the default question: `Which project is at the highest risk right now and why?`

The agent takes 60–120 seconds on `qwen2.5:7b`. Watch the terminal — you will see the ReACT loop executing in real time.

Expected output structure:

```
============================================================
PMO RISK ANALYST AGENT  (with memory + observability)
============================================================
Question: Which project is at the highest risk right now and why?
============================================================

[Memory] No relevant past analyses — starting fresh

> Entering new AgentExecutor chain...

Thought: I should first list all projects to know what exists.
Action: list_all_projects
Action Input: all
Observation: Available projects:
  PRJ001: ERP Modernisation (On Track)
  PRJ002: Customer Portal 2.0 (Off Track)
  ...

Thought: PRJ002 is Off Track. Let me check its weekly status.
Action: get_weekly_status
Action Input: PRJ002
Observation: Last 4 weeks of status:
  Week 51 ending 2025-12-29: RAG=Red SPI=0.64 CPI=0.67...

Thought: SPI of 0.64 is critically low. Let me check risks.
Action: get_project_risks
Action Input: PRJ002
Observation: Open/Escalated risks for PRJ002:
  [RSK012] Budget overrun Score=0.52 Status=Escalated...

Thought: I now have enough information to answer.
Final Answer: PRJ002 Customer Portal 2.0 is at highest risk...

> Finished chain.

============================================================
FINAL ANSWER
============================================================
PRJ002 Customer Portal 2.0 is at highest risk...
```

---

## Run a Second Question

```bash
python3 agents/pmo_risk_analyst.py "Summarise the schedule performance of PRJ001 ERP Modernisation"
```

---

## Understanding the Output

**What to observe in the ReACT loop:**

| What you see | What it means |
|---|---|
| Agent calls `list_all_projects` first | Autonomous decision — agent didn't know project IDs |
| Agent focuses on PRJ002 immediately | Inferred from `Off Track` status without being told |
| Agent calls `get_weekly_status` then `get_project_risks` | Logical sequence — performance first, then root cause |
| `[Memory] No relevant past analyses` | ChromaDB is empty — memory populated in Part 3 |
| `OUTPUT_PARSING_FAILURE` warning | LLM briefly broke format — recovered automatically |
| Final Answer cites specific SPI and risk IDs | Grounded in tool observations, not hallucinated |

---

## Key Implementation Details

**Why `temperature=0`:**
Makes the LLM deterministic — same question produces the same reasoning path. Essential for debugging and reproducibility.

**Why `max_iterations=10`:**
Without this cap a confused agent can loop indefinitely. Ten iterations is sufficient for any PMO analysis question.

**Why `handle_parsing_errors=True`:**
Local 7B models occasionally break the `Thought/Action` format. This flag catches parser exceptions and feeds the error back to the LLM as an observation, allowing it to self-correct.

**Why tools are in `pmo_tools.py` not `pmo_risk_analyst.py`:**
The multi-agent crew in Part 4 needs the same tools. Keeping them in a shared file avoids duplication and ensures both the single agent and the crew use identical tool implementations.

**Why the single agent only uses 4 of the 6 tools:**
`get_milestone_status` and `get_portfolio_overview` are in `pmo_tools.py` but not in the single agent's tool list. The single agent focuses on risk analysis — milestones and portfolio overviews are better suited to the specialist agents in the crew.

**Why memory and Langfuse are imported now:**
Both are present from the start so the codebase evolves incrementally. In Part 2 they have no visible effect — memory is empty, Langfuse isn't deployed yet. In Parts 3 and 5 they activate without requiring changes to this file.

---

## Common Failures and Fixes

**Agent hangs with no output:**
```bash
curl http://<windows-laptop-ip>:11434/api/tags
```
If no response — restart Ollama on the Windows laptop.

**`ModuleNotFoundError: No module named 'memory'`:**
```bash
# Confirm you are running from the project root
cd ~/pmo-copilot
python3 agents/pmo_risk_analyst.py
```

**`FileNotFoundError: projects.csv`:**
```bash
grep DATA_DIR .env
ls data/*.csv
```
Confirm `DATA_DIR` in `.env` points to the correct absolute path.

**Agent hits `max_iterations` without Final Answer:**
The LLM is struggling with the format. Try:
```bash
# In .env change to smaller, faster model for testing
OLLAMA_MODEL=llama3.2:latest
```

**`Langfuse` connection errors on startup:**
These are warnings not errors. The agent runs correctly even if Langfuse is not yet deployed. Traces will appear after Part 5.

---

## Validation Checkpoint

Before proceeding to Part 3, confirm both runs complete successfully:

```bash
# Default question
python3 agents/pmo_risk_analyst.py

# Targeted question
python3 agents/pmo_risk_analyst.py "What are the open risks for PRJ003?"
```

Both runs must:
- Complete without Python exceptions
- Show at least 2 tool calls in the ReACT loop
- Produce a `Final Answer` that cites specific project data — SPI values, risk IDs, scores

---

## What's Next

The agent works and produces grounded analyses. But it has no memory across sessions — ask the same question tomorrow and it starts from scratch. In Part 3 we add ChromaDB semantic memory so the agent accumulates knowledge and retrieves relevant past analyses automatically.

→ [Part 3 — Giving Your Agent Memory](./03-memory.md)