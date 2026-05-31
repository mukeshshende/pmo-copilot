"""
Phase 2 — PMO Risk Analyst Agent
Demonstrates: ReACT loop, Tool Calling, LangChain + Ollama
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

DATA_DIR = os.getenv("DATA_DIR")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

# ── LLM setup ────────────────────────────────────────────────────────────────

llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model=OLLAMA_MODEL,
    temperature=0,
    num_predict=1024,
)

# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_project_summary(project_id: str) -> str:
    """
    Returns basic details for a project including name, domain, budget,
    team size, start date, planned end date, and current status.
    Input: project_id as a string e.g. PRJ001
    """
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
        row = df[df["project_id"] == project_id.strip().upper()]
        if row.empty:
            return f"No project found with id {project_id}. Available ids: {df['project_id'].tolist()}"
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
    Returns the last 4 weeks of status data for a project including
    RAG status, SPI, CPI, percent complete, and open issues.
    Input: project_id as a string e.g. PRJ001
    """
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, "weekly_status.csv"))
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
    Returns all open or escalated risks for a project including
    risk type, probability, impact, risk score, and recommended mitigation.
    Input: project_id as a string e.g. PRJ001
    """
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, "risks.csv"))
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


tools = [
    list_all_projects,
    get_project_summary,
    get_weekly_status,
    get_project_risks,
]

# ── ReACT Prompt ──────────────────────────────────────────────────────────────
# This is the exact prompt format LangChain's ReACT agent expects.
# {tools} and {tool_names} are injected automatically by LangChain.
# {input} is the user question. {agent_scratchpad} accumulates the
# Thought/Action/Observation loop turns.

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

# ── Agent setup ───────────────────────────────────────────────────────────────

agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=REACT_PROMPT,
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,          # Shows the full Thought/Action/Observation loop
    max_iterations=10,     # Safety cap — prevents infinite loops
    handle_parsing_errors=True,
)

# ── Run ───────────────────────────────────────────────────────────────────────

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

    # Retrieve relevant memory
    memory_context = retrieve_relevant_analyses(question, k=3)
    if memory_context:
        print("[Memory] Injecting relevant past analyses")
    else:
        print("[Memory] No relevant past analyses — starting fresh\n")

    # Get Langfuse callback — captures every LLM + tool call automatically
    langfuse_cb = get_langfuse_callback(session_id="single-agent-run")

    result = agent_executor.invoke(
        {
            "input"         : question,
            "memory_context": memory_context,
        },
        config={"callbacks": [langfuse_cb]},
    )

    # Store in memory
    store_analysis(
        question   = question,
        answer     = result["output"],
        project_ids= [],
    )

    # Record trace manually as well for crew compatibility
    trace_agent_run(
        question   = question,
        answer     = result["output"],
        agent_name = "pmo-risk-analyst",
    )

    print("\n" + "="*60)
    print("FINAL ANSWER")
    print("="*60)
    print(result["output"])