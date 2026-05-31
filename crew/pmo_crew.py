"""
Phase 4 — Multi-Agent PMO Crew
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

# ── LLM ──────────────────────────────────────────────────────────────────────
# CrewAI 0.86.x requires its own LLM class with ollama/ prefix.
# This tells LiteLLM to route to local Ollama instead of cloud providers.

llm = LLM(
    model="ollama/qwen2.5:7b",
    base_url="http://192.168.1.16:11434",
    temperature=0,
)

# ── Tools (CrewAI-compatible wrappers) ───────────────────────────────────────

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


# ── Crew assembly ─────────────────────────────────────────────────────────────

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