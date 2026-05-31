# Part 4 — Building a Multi-Agent Crew

## What We Are Building

A three-agent CrewAI crew where specialist agents work sequentially, each building on the previous agent's output. The Schedule Risk Analyst analyses SPI trends and milestone delays. The Delivery Risk Analyst analyses open risks and CPI performance. The Executive PMO Advisor synthesises both reports into a CXO-ready summary.

By the end of this part you will have:

- Three specialist agents with distinct roles, goals, and backstories
- Tool specialisation — each agent has only the tools it needs
- Sequential execution — agents run in order, outputs flow forward
- Agent-to-agent context passing — the summary agent reads specialist outputs
- Memory integration — crew analyses stored and retrieved semantically
- Langfuse tracing — every crew run captured as an observable trace

---

## Why Multiple Agents

The single agent in Part 2 does everything itself — list projects, check schedules, check risks, summarise. This works but has limitations:

- One agent context gets overloaded on complex portfolio analysis
- No specialisation — the same agent reasons about schedules AND risks AND executive communication
- Output quality is inconsistent — the agent switches reasoning styles mid-analysis

CrewAI solves this with a team. Each agent has:

- A **role** — its job title, shown in verbose output
- A **goal** — what it is trying to achieve, shapes its reasoning
- A **backstory** — context that influences its output style
- **Tools** — only what it needs for its specific job
- A **task** — the specific work assigned for this run

---

## The Three-Agent Design

```
Portfolio scope
      │
      ▼
Schedule Risk Analyst
  Tools: list_projects, get_status, get_milestones
  Output: RAG rating per project + delayed milestones list
      │
      ▼
Delivery Risk Analyst
  Tools: list_projects, get_status, get_risks
  Output: Top 5 risks ranked by score + CPI summary
      │
      ▼
Executive PMO Advisor
  Tools: portfolio_overview only
  Input: reads both specialist reports via context=[]
  Output: Sub-300-word CXO summary with urgency levels
```

The summary agent never touches raw CSV data. It reasons purely from what the specialist agents produced. This mirrors how a real executive team works — the advisor synthesises analyst reports, not raw data.

---

## CrewAI vs LangChain Tools — Why Both Exist

You will notice that `pmo_crew.py` redefines tools using `@crewai_tool` rather than importing from `pmo_tools.py`. This is intentional.

CrewAI uses its own tool schema for pydantic validation — different from LangChain's `@tool` decorator. Importing LangChain tools directly into CrewAI agents causes validation errors.

The tools in `pmo_crew.py` are functionally identical to those in `pmo_tools.py` but wrapped with CrewAI's decorator. Both sets read the same CSV files and return the same formatted text.

| File | Decorator | Used by |
|---|---|---|
| `agents/pmo_tools.py` | `@tool` (LangChain) | Single agent, Streamlit UI |
| `crew/pmo_crew.py` | `@crewai_tool` (CrewAI) | Multi-agent crew |

---

## The LLM Configuration — Important Note

CrewAI 0.86.x requires its own `LLM` class with the `ollama/` prefix. This tells LiteLLM (CrewAI's internal routing layer) to use the local Ollama endpoint instead of attempting cloud provider lookup.

```python
from crewai import LLM

llm = LLM(
    model="ollama/qwen2.5:7b",
    base_url="http://192.168.1.16:11434",
    temperature=0,
)
```

**The `base_url` is hardcoded** — update `192.168.1.16` to your Windows laptop's actual LAN IP before running.

Using `ChatOllama` from LangChain instead of `crewai.LLM` causes CrewAI to serialise the model name incorrectly, stripping the `ollama/` prefix and causing LiteLLM to fail with `LLM Provider NOT provided`.

---

## The Complete Crew File — `crew/pmo_crew.py`

```python
"""
Multi-Agent PMO Crew
Demonstrates: CrewAI, Agent roles, Task delegation, Sequential execution,
              Agent-to-agent context passing, Memory integration
"""

import os
import sys
sys.path.insert(0, os.path.expanduser("~/pmo-copilot"))

from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool as crewai_tool
import pandas as pd

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

from memory.pmo_memory import store_analysis, retrieve_relevant_analyses
from observability.pmo_tracing import trace_crew_run

DATA_DIR        = os.getenv("DATA_DIR")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL")

# ── LLM ───────────────────────────────────────────────────────────────────────
# CrewAI 0.86.x requires its own LLM class with ollama/ prefix.
# Update base_url to your Windows laptop's LAN IP.

llm = LLM(
    model="ollama/qwen2.5:7b",
    base_url="http://192.168.1.16:11434",
    temperature=0,
)

# ── Tools ─────────────────────────────────────────────────────────────────────
# CrewAI requires its own @crewai_tool decorator — cannot use LangChain @tool.
# These tools are functionally identical to pmo_tools.py but wrapped for CrewAI.

@crewai_tool("List all projects")
def list_projects(query: str) -> str:
    """List all projects in the PMO portfolio with their current status. Input: pass any string like 'all'."""
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
        lines = ["Portfolio projects:"]
        for _, r in df.iterrows():
            lines.append(
                f"  {r['project_id']}: {r['project_name']} "
                f"| Domain={r['domain']} | Status={r['status']} "
                f"| Budget=${r['budget']:,} | Team={r['team_size']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


@crewai_tool("Get weekly status")
def get_status(project_id: str) -> str:
    """
    Get the last 4 weeks of RAG status, SPI, CPI and open issues
    for a specific project. Input: project_id like PRJ001.
    """
    try:
        df   = pd.read_csv(os.path.join(DATA_DIR, "weekly_status.csv"))
        proj = df[df["project_id"] == project_id.strip().upper()].tail(4)
        if proj.empty:
            return f"No data for {project_id}"
        lines = [f"Weekly status for {project_id}:"]
        for _, r in proj.iterrows():
            lines.append(
                f"  Wk{int(r['week_number'])} {r['week_ending']}: "
                f"RAG={r['rag_status']} SPI={r['spi']} CPI={r['cpi']} "
                f"Done={r['percent_complete']}% Issues={int(r['issues_open'])}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


@crewai_tool("Get project risks")
def get_risks(project_id: str) -> str:
    """
    Get all open and escalated risks for a project.
    Input: project_id like PRJ001.
    """
    try:
        df   = pd.read_csv(os.path.join(DATA_DIR, "risks.csv"))
        proj = df[
            (df["project_id"] == project_id.strip().upper()) &
            (df["status"].isin(["Open", "Escalated"]))
        ]
        if proj.empty:
            return f"No open risks for {project_id}"
        lines = [f"Risks for {project_id}:"]
        for _, r in proj.iterrows():
            lines.append(
                f"  [{r['risk_id']}] {r['risk_type']} "
                f"Score={r['risk_score']} Status={r['status']}"
                f" → {r['mitigation_action']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


@crewai_tool("Get milestone status")
def get_milestones(project_id: str) -> str:
    """
    Get all milestones for a project showing delays.
    Input: project_id like PRJ001.
    """
    try:
        df   = pd.read_csv(os.path.join(DATA_DIR, "milestones.csv"))
        proj = df[df["project_id"] == project_id.strip().upper()]
        if proj.empty:
            return f"No milestones for {project_id}"
        lines = [f"Milestones for {project_id}:"]
        for _, r in proj.iterrows():
            delay = (
                f" DELAYED {int(r['delay_weeks'])}wk"
                if r["delay_weeks"] > 0 else ""
            )
            lines.append(
                f"  {r['milestone_name']}: {r['status']}"
                f" planned={r['planned_date']}{delay}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


@crewai_tool("Get portfolio overview")
def portfolio_overview(query: str) -> str:
    """Get a one-line summary of every project showing latest RAG, SPI, CPI and completion. Input: pass any string like 'all'."""
    try:
        projects = pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
        status   = pd.read_csv(os.path.join(DATA_DIR, "weekly_status.csv"))
        lines    = ["Portfolio snapshot:"]
        for _, p in projects.iterrows():
            pid    = p["project_id"]
            latest = status[status["project_id"] == pid].iloc[-1]
            lines.append(
                f"  {pid} {p['project_name']}: "
                f"RAG={latest['rag_status']} SPI={latest['spi']} "
                f"CPI={latest['cpi']} Done={latest['percent_complete']}% "
                f"Status={p['status']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


# ── Agent definitions ─────────────────────────────────────────────────────────

schedule_agent = Agent(
    role="Schedule Risk Analyst",
    goal=(
        "Identify schedule risks across all projects by analysing SPI trends, "
        "milestone delays, and RAG status patterns. Produce a concise schedule "
        "risk report with RED/AMBER/GREEN rating per project."
    ),
    backstory=(
        "You are a certified PMP with 12 years of experience tracking project "
        "schedules. You are known for catching schedule slippage early by "
        "spotting SPI trends before they become critical. You are direct, "
        "precise, and always cite specific metrics."
    ),
    tools=[list_projects, get_status, get_milestones],
    llm=llm,
    verbose=True,
    max_iter=5,
    allow_delegation=False,
)

delivery_agent = Agent(
    role="Delivery Risk Analyst",
    goal=(
        "Identify delivery risks across all projects by analysing open and "
        "escalated risks, CPI trends, and issue counts. Produce a concise "
        "delivery risk report with top risks ranked by score."
    ),
    backstory=(
        "You are a risk management specialist with a background in enterprise "
        "delivery. You have an eye for compounding risks — situations where "
        "two medium risks combine into a critical one. You always recommend "
        "specific, actionable mitigations."
    ),
    tools=[list_projects, get_status, get_risks],
    llm=llm,
    verbose=True,
    max_iter=5,
    allow_delegation=False,
)

summary_agent = Agent(
    role="Executive PMO Advisor",
    goal=(
        "Synthesise the schedule and delivery risk reports into a concise "
        "executive summary suitable for a CXO audience. Highlight the top 3 "
        "concerns and provide clear recommended actions."
    ),
    backstory=(
        "You are a former CTO turned PMO advisor. You have presented portfolio "
        "reviews to boards for 20 years. You translate technical risk data into "
        "business impact language. You never use jargon without explaining it. "
        "Your summaries are always under one page."
    ),
    tools=[portfolio_overview],
    llm=llm,
    verbose=True,
    max_iter=4,
    allow_delegation=False,
)


# ── Task definitions ──────────────────────────────────────────────────────────

def build_tasks(focus_project: str = None):
    """
    Builds the three crew tasks.
    If focus_project is set, agents focus on that project.
    Otherwise they analyse the full portfolio.
    """
    scope = (
        f"Focus specifically on project {focus_project}."
        if focus_project
        else "Analyse all projects in the portfolio."
    )

    task_schedule = Task(
        description=(
            f"Analyse schedule performance across the PMO portfolio. {scope}\n"
            "Steps:\n"
            "1. Get portfolio overview or list projects\n"
            "2. For each relevant project check weekly status (SPI trend)\n"
            "3. Check milestone status for delays\n"
            "4. Rate each project RED/AMBER/GREEN for schedule risk\n"
            "5. Write a schedule risk report with specific SPI values and dates"
        ),
        expected_output=(
            "A schedule risk report with: "
            "(a) one-line RAG rating per project with SPI evidence, "
            "(b) list of delayed milestones with delay in weeks, "
            "(c) overall portfolio schedule health statement."
        ),
        agent=schedule_agent,
    )

    task_delivery = Task(
        description=(
            f"Analyse delivery risks across the PMO portfolio. {scope}\n"
            "Steps:\n"
            "1. Get portfolio overview or list projects\n"
            "2. For each relevant project check open and escalated risks\n"
            "3. Check CPI and open issue trends\n"
            "4. Rank the top 5 risks by risk score across the portfolio\n"
            "5. Write a delivery risk report with specific risk IDs and scores"
        ),
        expected_output=(
            "A delivery risk report with: "
            "(a) top 5 risks ranked by score with project and risk ID, "
            "(b) CPI summary per project, "
            "(c) recommended immediate actions for each top risk."
        ),
        agent=delivery_agent,
    )

    task_summary = Task(
        description=(
            "You have received two specialist reports:\n"
            "- Schedule Risk Report from the Schedule Risk Analyst\n"
            "- Delivery Risk Report from the Delivery Risk Analyst\n\n"
            "Using ONLY those reports plus the portfolio overview tool:\n"
            "1. Identify the top 3 concerns for executive attention\n"
            "2. Write an executive summary in plain business language\n"
            "3. List recommended actions with owner and urgency\n"
            "Keep the summary under 300 words."
        ),
        expected_output=(
            "An executive summary with: "
            "(a) portfolio health statement in one sentence, "
            "(b) top 3 concerns with business impact, "
            "(c) recommended actions with urgency level (Immediate/This Week/This Month)."
        ),
        agent=summary_agent,
        context=[task_schedule, task_delivery],
    )

    return [task_schedule, task_delivery, task_summary]


# ── Crew assembly and run ─────────────────────────────────────────────────────

def run_crew(focus_project: str = None):
    tasks = build_tasks(focus_project)

    crew = Crew(
        agents=[schedule_agent, delivery_agent, summary_agent],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    print("\n" + "="*60)
    print("PMO CREW  —  MULTI-AGENT ANALYSIS")
    print("="*60)
    scope = focus_project or "Full Portfolio"
    print(f"Scope: {scope}")
    print("="*60 + "\n")

    # Retrieve relevant memory before crew runs
    query  = f"PMO portfolio analysis {focus_project or 'all projects'}"
    memory = retrieve_relevant_analyses(query, k=2)
    if memory:
        print("[Memory] Injecting relevant past analyses\n")

    result = crew.kickoff()

    # Trace the completed crew run in Langfuse
    trace_crew_run(
        crew_name = "pmo-crew",
        scope     = scope,
        result    = str(result),
    )

    # Store the executive summary in memory
    store_analysis(
        question   = f"Portfolio crew analysis: {scope}",
        answer     = str(result),
        project_ids= [focus_project] if focus_project else [],
    )

    print("\n" + "="*60)
    print("EXECUTIVE SUMMARY")
    print("="*60)
    print(result)
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    focus = sys.argv[1] if len(sys.argv) > 1 else None
    run_crew(focus)
```

---

## Before Running — Update the Ollama IP

The `base_url` in the LLM definition is hardcoded. Update it to your Windows laptop's LAN IP:

```python
llm = LLM(
    model="ollama/qwen2.5:7b",
    base_url="http://<your-windows-laptop-ip>:11434",
    temperature=0,
)
```

Verify your Windows laptop IP from the Linux machine:

```bash
curl http://<windows-laptop-ip>:11434/api/tags | python3 -m json.tool | head -5
```

---

## Run the Crew

**Full portfolio analysis:**

```bash
cd ~/pmo-copilot
source venv/bin/activate
python3 crew/pmo_crew.py
```

Expected runtime: **4–8 minutes** for three agents sequentially on `qwen2.5:7b`.

**Single project focus:**

```bash
python3 crew/pmo_crew.py PRJ002
```

Expected runtime: 2–4 minutes.

---

## What to Watch in the Output

The output clearly shows each agent handing off to the next:

```
# Agent: Schedule Risk Analyst
## Task: Analyse schedule performance...
## Using tool: List all projects
## Using tool: Get weekly status
## Using tool: Get milestone status
## Final Answer: [Schedule risk report with RAG ratings]

# Agent: Delivery Risk Analyst
## Task: Analyse delivery risks...
## Using tool: List all projects
## Using tool: Get project risks
## Final Answer: [Delivery risk report with ranked risks]

# Agent: Executive PMO Advisor
## Task: Synthesise the reports...
## Using tool: Get portfolio overview
## Final Answer: [Executive summary under 300 words]

EXECUTIVE SUMMARY
[Final output]
```

---

## Key Observations in the Output

**Tool specialisation working:**

| Agent | Tools called | Tools NOT called |
|---|---|---|
| Schedule analyst | `list_projects`, `get_status`, `get_milestones` | `get_risks` — not its job |
| Delivery analyst | `list_projects`, `get_status`, `get_risks` | `get_milestones` — not its job |
| Summary advisor | `portfolio_overview` only | Never touches raw data |

**Autonomous prioritisation:**
The schedule agent checks PRJ002 before PRJ001 even though PRJ001 has a larger budget. It inferred from the project list that `Off Track` status is more urgent than `On Track`. Nobody told it to do this.

**Agent-to-agent context passing:**
The summary agent's output references findings from both specialist reports — specific SPI values, risk IDs, and milestone delays — even though it only has access to `portfolio_overview`. It got that detail from `context=[task_schedule, task_delivery]`.

**Backstory shaping output style:**
The schedule analyst writes in bullet points with specific metrics. The summary advisor writes in flowing business prose. Same LLM, different backstory, different output style.

---

## Key Implementation Details

**Why `Process.sequential` not `Process.hierarchical`:**
Sequential means agents run in strict order — Schedule → Delivery → Summary. Each waits for the previous to complete. Hierarchical would allow a manager agent to delegate dynamically, adding complexity without benefit for this use case.

**Why `allow_delegation=False`:**
Prevents agents from handing tasks to each other mid-execution. Each agent completes its assigned task fully. Delegation is handled at the Crew level through task context, not at the agent level.

**Why `max_iter=5` for analyst agents and `max_iter=4` for summary agent:**
The summary agent has less work to do — it synthesises reports rather than calling multiple tools. Lower `max_iter` prevents it from over-elaborating.

**Why memory is retrieved before `crew.kickoff()` but not injected:**
Unlike the single agent where memory context is injected into the prompt, the crew uses memory for awareness only — printing whether relevant past analyses exist. Full memory injection into CrewAI agents requires custom prompt templates per agent, adding complexity beyond the scope of this series.

**Why `trace_crew_run` is a manual trace:**
CrewAI does not natively support LangChain callbacks, so automatic per-call tracing is not available. `trace_crew_run` creates a single summary trace after the crew completes — capturing the scope and executive summary output.

---

## Common Failures and Fixes

**Crew hangs on `🧠 Thinking...` for more than 5 minutes:**
```bash
# Kill the process with Ctrl+C then verify Ollama
curl http://<windows-laptop-ip>:11434/api/tags
```

**`LLM Provider NOT provided` error:**
The `base_url` in the LLM definition is wrong or the `ollama/` prefix is missing:
```python
# Wrong
llm = LLM(model="qwen2.5:7b", ...)

# Correct
llm = LLM(model="ollama/qwen2.5:7b", base_url="http://<ip>:11434", ...)
```

**`pkg_resources` import error:**
```bash
pip install setuptools==69.5.1
```

**Agent hits `max_iter` without completing:**
The LLM is struggling with the CrewAI format. This is more common on first run when there is no warm cache. Run again — second run is usually faster and more reliable.

**`ModuleNotFoundError: No module named 'memory'`:**
```bash
cd ~/pmo-copilot
python3 crew/pmo_crew.py
```
Must run from the project root directory.

---

## Validation Checkpoint

Before proceeding to Part 5, confirm:

```bash
# Full portfolio run completes
python3 crew/pmo_crew.py

# Single project run completes
python3 crew/pmo_crew.py PRJ002
```

Both runs must:
- Show all three agents completing with `## Final Answer:`
- Print `EXECUTIVE SUMMARY` at the end
- Show `[Memory] Stored analysis` confirming persistence
- Complete without Python exceptions

---

## What's Next

The crew produces excellent analyses but the only way to see what happened is to scroll through terminal output. In Part 5 we add Langfuse observability — a self-hosted web UI that captures every LLM call, tool call, and agent step as a structured trace — and wrap everything in a Streamlit UI.

→ [Part 5 — Observability and UI](./05-observability-ui.md)