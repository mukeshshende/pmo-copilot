"""
Phase 6 — PMO Copilot Streamlit UI
Demonstrates: Streamlit, agent integration, crew integration,
              memory browsing, real-time streaming output
"""

import os
import sys
import time
import queue
import threading
import pandas as pd
import streamlit as st

# Support both local dev (/home/m4hs4e/pmo-copilot) and container (/app)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

DATA_DIR = os.getenv("DATA_DIR")

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PMO Copilot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("📊 PMO Copilot")
st.sidebar.caption("AI-powered portfolio analysis")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Portfolio Overview",
        "🤖 Single Agent",
        "👥 Crew Analysis",
        "🧠 Memory Browser",
        "ℹ️ System Info",
    ],
)

st.sidebar.divider()
st.sidebar.caption(f"Ollama: {os.getenv('OLLAMA_BASE_URL')}")
st.sidebar.caption(f"Model: {os.getenv('OLLAMA_MODEL')}")
st.sidebar.caption(f"Langfuse: {os.getenv('LANGFUSE_HOST')}")


# ── Cached data loaders ───────────────────────────────────────────────────────

@st.cache_data
def load_projects():
    return pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))

@st.cache_data
def load_weekly_status():
    return pd.read_csv(os.path.join(DATA_DIR, "weekly_status.csv"))

@st.cache_data
def load_risks():
    return pd.read_csv(os.path.join(DATA_DIR, "risks.csv"))

@st.cache_data
def load_milestones():
    return pd.read_csv(os.path.join(DATA_DIR, "milestones.csv"))


# ── RAG colour helper ─────────────────────────────────────────────────────────

def rag_colour(val):
    colours = {
        "Green":    "background-color: #d4edda",
        "Amber":    "background-color: #fff3cd",
        "Red":      "background-color: #f8d7da",
        "On Track": "background-color: #d4edda",
        "At Risk":  "background-color: #fff3cd",
        "Off Track":"background-color: #f8d7da",
    }
    return colours.get(val, "")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Portfolio Overview
# ══════════════════════════════════════════════════════════════════════════════

if page == "🏠 Portfolio Overview":
    st.title("Portfolio Overview")
    st.caption("Live view of all project data from CSV files")

    projects   = load_projects()
    status     = load_weekly_status()
    risks      = load_risks()
    milestones = load_milestones()

    # ── KPI row ───────────────────────────────────────────────────────────────
    total      = len(projects)
    on_track   = len(projects[projects["status"] == "On Track"])
    off_track  = len(projects[projects["status"] == "Off Track"])
    at_risk    = len(projects[projects["status"] == "At Risk"])
    open_risks = len(risks[risks["status"].isin(["Open", "Escalated"])])
    delayed_ms = len(milestones[milestones["delay_weeks"] > 0])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Projects",      total)
    c2.metric("On Track",            on_track)
    c3.metric("At Risk",             at_risk)
    c4.metric("Off Track",           off_track,
              delta=f"-{off_track}" if off_track else None)
    c5.metric("Open Risks",          open_risks)
    c6.metric("Delayed Milestones",  delayed_ms)

    st.divider()

    # ── Projects table ────────────────────────────────────────────────────────
    st.subheader("Projects")
    st.dataframe(
        projects.style.applymap(rag_colour, subset=["status"]),
        use_container_width=True,
        hide_index=True,
    )

    # ── Latest weekly status per project ─────────────────────────────────────
    st.subheader("Latest Weekly Status")
    latest_rows = []
    for pid in projects["project_id"]:
        proj_status = status[status["project_id"] == pid]
        if not proj_status.empty:
            latest_rows.append(proj_status.iloc[-1])
    latest_df = pd.DataFrame(latest_rows).reset_index(drop=True)

    st.dataframe(
        latest_df[["project_id", "week_ending", "rag_status",
                   "spi", "cpi", "percent_complete", "issues_open"]]
        .style.applymap(rag_colour, subset=["rag_status"]),
        use_container_width=True,
        hide_index=True,
    )

    # ── SPI trend chart ───────────────────────────────────────────────────────
    st.subheader("SPI Trend — Last 12 Weeks")
    selected_projects = st.multiselect(
        "Select projects",
        options=projects["project_id"].tolist(),
        default=["PRJ001", "PRJ002"],
    )
    if selected_projects:
        chart_data = status[status["project_id"].isin(selected_projects)]
        chart_data = chart_data[chart_data["week_number"] >= 40]
        pivot = chart_data.pivot(
            index="week_number", columns="project_id", values="spi"
        )
        st.line_chart(pivot)

    # ── Open risks ────────────────────────────────────────────────────────────
    st.subheader("Open and Escalated Risks")
    open_risks_df = risks[risks["status"].isin(["Open", "Escalated"])].sort_values(
        "risk_score", ascending=False
    )
    st.dataframe(
        open_risks_df[["risk_id", "project_id", "risk_type",
                        "risk_score", "status", "mitigation_action"]],
        use_container_width=True,
        hide_index=True,
    )

    # ── Milestone delays ──────────────────────────────────────────────────────
    st.subheader("Delayed Milestones")
    delayed_df = milestones[milestones["delay_weeks"] > 0].sort_values(
        "delay_weeks", ascending=False
    )
    st.dataframe(
        delayed_df[["milestone_id", "project_id", "milestone_name",
                     "planned_date", "delay_weeks", "status"]],
        use_container_width=True,
        hide_index=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Single Agent
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🤖 Single Agent":
    st.title("Single Agent Analysis")
    st.caption("Ask the PMO Risk Analyst a question. Watch it reason step by step.")

    # ── Suggested questions ───────────────────────────────────────────────────
    st.subheader("Suggested Questions")
    suggestions = [
        "Which project is at the highest risk right now and why?",
        "What is the schedule performance of PRJ001 ERP Modernisation?",
        "Are there any financial risks I should escalate to the CFO?",
        "Which project has the worst budget performance?",
        "Summarise the delivery risks for PRJ002 Customer Portal 2.0",
        "What is the schedule risk for PRJ003 Data Lake Migration?",
    ]

    col1, col2 = st.columns(2)
    for i, s in enumerate(suggestions):
        col = col1 if i % 2 == 0 else col2
        if col.button(s, key=f"sug_{i}", use_container_width=True):
            st.session_state["agent_question"] = s
            st.rerun()

    st.divider()

    question = st.text_input(
        "Your question:",
        value=st.session_state.get("agent_question", ""),
        placeholder="Ask anything about the PMO portfolio...",
    )

    run_agent = st.button("🚀 Run Agent", type="primary", disabled=not question)

    if run_agent and question:
        st.session_state["agent_question"] = question
        st.divider()

        # Step 1 — Memory
        st.markdown("**Step 1 — Checking memory...**")
        from memory.pmo_memory import retrieve_relevant_analyses, store_analysis
        memory_context = retrieve_relevant_analyses(question, k=3)

        if memory_context:
            with st.expander("🧠 Relevant past analyses found", expanded=False):
                st.text(memory_context[:800])
            st.success("Memory context injected into prompt")
        else:
            st.info("No relevant past analyses — starting fresh")

        # Step 2 — Run agent in background thread
        st.markdown("**Step 2 — Running agent...**")

        agent_queue = queue.Queue()

        def run_agent_thread(q, question, memory_context):
            try:
                from langchain_ollama import ChatOllama
                from langchain.agents import AgentExecutor, create_react_agent
                from langchain.prompts import PromptTemplate
                from agents.pmo_tools import (
                    list_all_projects,
                    get_project_summary,
                    get_weekly_status,
                    get_project_risks,
                    get_milestone_status,
                )

                llm = ChatOllama(
                    base_url=os.getenv("OLLAMA_BASE_URL"),
                    model=os.getenv("OLLAMA_MODEL"),
                    temperature=0,
                    num_predict=1024,
                )

                tools = [
                    list_all_projects,
                    get_project_summary,
                    get_weekly_status,
                    get_project_risks,
                    get_milestone_status,
                ]

                REACT_PROMPT = PromptTemplate.from_template(
                    """You are a senior PMO Risk Analyst with 15 years of experience.

{memory_context}

You have access to the following tools:
{tools}

Use this EXACT format:

Thought: <your reasoning>
Action: <tool name — must be one of [{tool_names}]>
Action Input: <input to the tool>
Observation: <tool result>

When done:
Thought: I now have enough information to answer.
Final Answer: <your complete analysis>

Rules:
- Always check weekly status AND risks before assessing risk.
- Be specific: cite SPI values, risk scores, and dates.
- End with a clear recommendation.

Question: {input}
{agent_scratchpad}"""
                )

                agent    = create_react_agent(llm=llm, tools=tools, prompt=REACT_PROMPT)
                executor = AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=False,
                    max_iterations=10,
                    handle_parsing_errors=True,
                    return_intermediate_steps=True,
                )
                try:
                    from observability.pmo_tracing import get_langfuse_callback
                    langfuse_cb = get_langfuse_callback(
                        session_id="streamlit-agent"
                    )
                    callbacks = [langfuse_cb]
                except Exception:
                    callbacks = []

                result = executor.invoke(
                    {"input": question, "memory_context": memory_context or ""},
                    config={"callbacks": callbacks},
                )
                q.put({"status": "ok", "result": result})

            except Exception as e:
                q.put({"status": "error", "error": str(e)})

        thread = threading.Thread(
            target=run_agent_thread,
            args=(agent_queue, question, memory_context),
            daemon=True,
        )
        thread.start()

        # Animated waiting indicator
        status_placeholder = st.empty()
        dots = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while thread.is_alive():
            status_placeholder.markdown(
                f"{dots[i % len(dots)]}  Agent thinking... "
                f"(typically 60–120 seconds on qwen2.5:7b)"
            )
            time.sleep(0.5)
            i += 1

        thread.join()
        status_placeholder.empty()

        # Step 3 — Display results
        if agent_queue.empty():
            st.error("Agent thread completed but returned no result.")
        else:
            payload = agent_queue.get()

            if payload["status"] == "error":
                st.error(f"Agent error: {payload['error']}")

            else:
                result = payload["result"]

                st.markdown("**Step 3 — Agent reasoning steps:**")
                steps_md = ""
                for idx, (action, observation) in enumerate(
                    result.get("intermediate_steps", []), 1
                ):
                    steps_md += f"**Step {idx}** — Tool: `{action.tool}`\n"
                    steps_md += f"- Input: `{action.tool_input}`\n"
                    steps_md += (
                        f"- Output: {str(observation)[:300]}\n\n"
                    )

                if steps_md:
                    with st.expander("🔧 Tool calls made by agent", expanded=True):
                        st.markdown(steps_md)
                else:
                    st.info("No intermediate steps captured.")

                st.divider()
                st.subheader("✅ Final Answer")
                st.markdown(result["output"])

                store_analysis(
                    question   = question,
                    answer     = result["output"],
                    project_ids= [],
                )
                st.success("Analysis stored in memory for future reference")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Crew Analysis
# ══════════════════════════════════════════════════════════════════════════════

elif page == "👥 Crew Analysis":
    st.title("Multi-Agent Crew Analysis")
    st.caption(
        "Run the full crew: Schedule Agent → Delivery Agent → Executive Summary Agent"
    )

    projects   = load_projects()
    focus_opts = ["Full Portfolio"] + projects["project_id"].tolist()

    col1, col2 = st.columns([2, 1])
    with col1:
        focus = st.selectbox("Analysis scope", focus_opts)
    with col2:
        st.metric("Agents", "3")
        st.caption("Schedule + Delivery + Summary")

    st.info(
        "⏱️ Full portfolio analysis takes 4–8 minutes. "
        "Single project focus takes 2–4 minutes."
    )

    run_crew_btn = st.button("🚀 Run Crew Analysis", type="primary")

    if run_crew_btn:
        focus_project = None if focus == "Full Portfolio" else focus
        st.divider()
        progress = st.progress(0, text="Starting crew...")

        crew_queue = queue.Queue()

        def run_crew_thread(cq, focus_project):
            try:
                from crew.pmo_crew import (
                    schedule_agent,
                    delivery_agent,
                    summary_agent,
                    build_tasks,
                )
                from crewai import Crew, Process

                tasks = build_tasks(focus_project)
                crew  = Crew(
                    agents=[schedule_agent, delivery_agent, summary_agent],
                    tasks=tasks,
                    process=Process.sequential,
                    verbose=False,
                )
                result = crew.kickoff()
                cq.put({"status": "ok", "result": result})
            except Exception as e:
                cq.put({"status": "error", "error": str(e)})

        thread = threading.Thread(
            target=run_crew_thread,
            args=(crew_queue, focus_project),
            daemon=True,
        )
        thread.start()

        progress.progress(10, text="Crew started — Schedule Agent working...")
        elapsed = 0
        while thread.is_alive():
            time.sleep(5)
            elapsed += 5
            pct = min(10 + elapsed, 85)
            if elapsed < 120:
                msg = f"Schedule Agent analysing... ({elapsed}s elapsed)"
            elif elapsed < 240:
                msg = f"Delivery Agent analysing... ({elapsed}s elapsed)"
            else:
                msg = f"Summary Agent writing... ({elapsed}s elapsed)"
            progress.progress(pct, text=msg)

        thread.join()
        progress.progress(90, text="Storing results...")

        if crew_queue.empty():
            st.error("Crew thread returned no result.")
        else:
            payload = crew_queue.get()

            if payload["status"] == "error":
                st.error(f"Crew error: {payload['error']}")
                st.exception(Exception(payload["error"]))
            else:
                result = payload["result"]

                from memory.pmo_memory import store_analysis
                from observability.pmo_tracing import trace_crew_run

                store_analysis(
                    question   = f"Crew analysis: {focus}",
                    answer     = str(result),
                    project_ids= [focus_project] if focus_project else [],
                )
                trace_crew_run(
                    crew_name = "pmo-crew-ui",
                    scope     = focus,
                    result    = str(result),
                )

                progress.progress(100, text="Complete!")
                st.subheader("Executive Summary")
                st.markdown(str(result))
                st.success("✅ Analysis complete and stored in memory")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — Memory Browser
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🧠 Memory Browser":
    st.title("Memory Browser")
    st.caption("Explore what the PMO Copilot has remembered from past analyses")

    from memory.pmo_memory import memory_stats, retrieve_relevant_analyses

    stats = memory_stats()

    col1, col2 = st.columns(2)
    col1.metric("Total Stored Analyses", stats["total_stored"])
    col2.metric("Storage Location", "ChromaDB (local)")

    st.divider()

    st.subheader("Semantic Search")
    st.caption(
        "Search memory by meaning — not keywords. "
        "Try: 'budget problems', 'schedule delays', 'high risk projects'"
    )

    search_query = st.text_input(
        "Search query:",
        placeholder="e.g. budget problems across projects",
    )
    k = st.slider("Number of results", min_value=1, max_value=10, value=3)

    if st.button("🔍 Search Memory", disabled=not search_query):
        with st.spinner("Searching..."):
            results = retrieve_relevant_analyses(search_query, k=k)
        if results:
            st.subheader("Results")
            st.text(results)
        else:
            st.warning("No relevant analyses found in memory.")

    st.divider()

    if st.button("🗑️ Clear All Memory", type="secondary"):
        from memory.pmo_memory import clear_memory
        clear_memory()
        st.success("Memory cleared.")
        st.cache_data.clear()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — System Info
# ══════════════════════════════════════════════════════════════════════════════

elif page == "ℹ️ System Info":
    st.title("System Information")

    st.subheader("Configuration")
    config_data = {
        "Component": [
            "Ollama URL", "LLM Model", "Embed Model",
            "Data Directory", "ChromaDB Path", "Langfuse Host",
        ],
        "Value": [
            os.getenv("OLLAMA_BASE_URL"),
            os.getenv("OLLAMA_MODEL"),
            os.getenv("OLLAMA_EMBED_MODEL"),
            os.getenv("DATA_DIR"),
            os.getenv("CHROMA_DIR"),
            os.getenv("LANGFUSE_HOST"),
        ],
    }
    st.dataframe(
        pd.DataFrame(config_data),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Data Files")
    try:
        file_info = []
        for fname in [
            "projects.csv", "weekly_status.csv",
            "risks.csv", "milestones.csv",
        ]:
            fpath = os.path.join(DATA_DIR, fname)
            df    = pd.read_csv(fpath)
            file_info.append({
                "File":    fname,
                "Rows":    len(df),
                "Columns": len(df.columns),
                "Size":    f"{os.path.getsize(fpath):,} bytes",
            })
        st.dataframe(
            pd.DataFrame(file_info),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as e:
        st.error(f"Error reading data files: {e}")

    st.subheader("Ollama Connection")
    try:
        import requests
        resp = requests.get(
            f"{os.getenv('OLLAMA_BASE_URL')}/api/tags", timeout=5
        )
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            st.success(f"✅ Connected — Models: {', '.join(models)}")
        else:
            st.error(f"❌ Ollama returned status {resp.status_code}")
    except Exception as e:
        st.error(f"❌ Cannot reach Ollama: {e}")

    st.subheader("Langfuse Connection")
    try:
        import requests
        resp = requests.get(
            f"{os.getenv('LANGFUSE_HOST')}/api/public/health", timeout=5
        )
        if resp.status_code == 200:
            st.success("✅ Langfuse is healthy")
        else:
            st.error(f"❌ Langfuse returned status {resp.status_code}")
    except Exception as e:
        st.error(f"❌ Cannot reach Langfuse: {e}")

    st.subheader("Memory Stats")
    try:
        from memory.pmo_memory import memory_stats
        stats = memory_stats()
        st.success(f"✅ ChromaDB — {stats['total_stored']} analyses stored")
        st.caption(f"Path: {stats['chroma_dir']}")
    except Exception as e:
        st.error(f"❌ ChromaDB error: {e}")