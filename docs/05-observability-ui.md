# Part 5 — Observability and UI

## What We Are Building

Two things in this part:

1. **Langfuse observability** — a self-hosted web UI running in K3s that captures every LLM call, tool call, and agent step as a structured trace with timing, token counts, inputs, and outputs.

2. **Streamlit UI** — a five-page browser application that wraps everything built in Parts 2–4 into an interface a non-technical PMO user can operate.

By the end of this part you will have:

- Langfuse deployed in K3s capturing agent traces automatically
- Every single agent run producing a detailed trace with tool calls visible
- Every crew run producing a summary trace
- A browser UI accessible from any device on your home network
- Agent runs that stay responsive in the UI using background threading

---

## Part A — Langfuse Observability

### Why Observability Matters for Agentic Systems

With a traditional API call you know exactly what happened — you sent a request, you got a response. With an agentic system, a single user question triggers:

- Multiple LLM calls as the agent reasons through the ReACT loop
- Multiple tool calls with specific inputs and outputs
- Retry attempts when the LLM breaks the expected format
- Memory retrieval that injects context into the prompt

Without observability you are flying blind. You cannot tell why an agent produced a particular answer, which tool call took 30 seconds, or whether a parse error was recovered correctly.

Langfuse captures all of this as a **trace** — a hierarchical record of every event in the agent's execution, with timestamps, token counts, and inputs/outputs at every step.

### Langfuse Architecture in K3s

Langfuse runs as two pods inside the `pmo-copilot` namespace:

```
langfuse-server pod  :30300  ← web UI + API
langfuse-postgres pod :5432   ← stores traces (internal only)
langfuse-postgres-pvc  2Gi   ← persistent storage on Dell disk
```

The PMO Copilot pod reaches Langfuse via internal K3s DNS:
```
http://langfuse-server:3000
```

External browser access via NodePort:
```
http://<linux-laptop-ip>:30300
```

### Deploy Langfuse to K3s

**Create the Postgres PVC:**

```bash
kubectl apply -f k8s/langfuse-pvc.yaml
```

**Deploy Postgres:**

```bash
kubectl apply -f k8s/langfuse-postgres.yaml
```

Wait for Postgres to be ready:

```bash
kubectl get pods -w | grep langfuse-postgres
```

Expected:
```
langfuse-postgres-xxx   1/1   Running   0   36s
```

**Deploy Langfuse server:**

```bash
kubectl apply -f k8s/langfuse-server.yaml
```

Wait for Langfuse to initialise — takes 60–90 seconds while it creates the database schema:

```bash
kubectl get pods -w | grep langfuse-server
```

Expected:
```
langfuse-server-xxx   1/1   Running   0   105s
```

**Verify health:**

```bash
curl -s http://127.0.0.1:30300/api/public/health
```

Expected:
```json
{"status":"OK","version":"2.95.11"}
```

### Create Your Langfuse Account and API Keys

Open browser at `http://<linux-laptop-ip>:30300`:

1. Click **Sign Up** — enter any email and password (local only, no verification)
2. Create organisation — name it `PMO Copilot`
3. Create project — name it `pmo-dev`
4. Go to **Settings → API Keys**
5. Click **Create new API key**
6. Copy both keys — you will not see the secret key again:
   - Public key: `pk-lf-...`
   - Secret key: `sk-lf-...`

**Add keys to `.env`:**

```bash
nano .env
```

Set:
```
LANGFUSE_PUBLIC_KEY=pk-lf-your-actual-key
LANGFUSE_SECRET_KEY=sk-lf-your-actual-key
LANGFUSE_HOST=http://<linux-laptop-ip>:30300
```

**Create K3s secret:**

```bash
kubectl create secret generic pmo-secrets \
  --from-literal=LANGFUSE_PUBLIC_KEY=pk-lf-your-actual-key \
  --from-literal=LANGFUSE_SECRET_KEY=sk-lf-your-actual-key
```

**Update ConfigMap with Langfuse internal URL:**

```bash
kubectl apply -f k8s/configmap.yaml
```

Verify:
```bash
kubectl get configmap pmo-config -o jsonpath='{.data.LANGFUSE_HOST}'
```

Expected:
```
http://langfuse-server:3000
```

---

### The Tracing Module — `observability/pmo_tracing.py`

```python
"""
PMO Observability Module
Demonstrates: Langfuse tracing, LLM call capture, Tool call capture,
              Agent step tracking, Token counting
"""

import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

from langfuse import Langfuse
from langfuse.callback import CallbackHandler

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST       = os.getenv("LANGFUSE_HOST", "http://localhost:3000")


def get_langfuse_client() -> Langfuse:
    """Returns a configured Langfuse client."""
    return Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )


def get_langfuse_callback(session_id: str = None, user_id: str = "pmo-analyst") -> CallbackHandler:
    """
    Returns a LangChain-compatible Langfuse callback handler.
    Every LLM call and tool call made through LangChain is
    automatically captured as a trace in Langfuse.
    """
    return CallbackHandler(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
        session_id=session_id,
        user_id=user_id,
        trace_name="pmo-agent-run",
    )


def trace_crew_run(crew_name: str, scope: str, result: str) -> str:
    """
    Manually traces a CrewAI crew run in Langfuse.
    CrewAI does not natively support LangChain callbacks,
    so we create the trace manually after the crew completes.
    """
    lf    = get_langfuse_client()
    trace = lf.trace(
        name    = f"crew-run: {crew_name}",
        input   = {"scope": scope},
        output  = {"summary": result[:500]},
        tags    = ["crew", "pmo", crew_name],
    )
    lf.flush()
    trace_url = f"{LANGFUSE_HOST}/trace/{trace.id}"
    print(f"  [Langfuse] Trace recorded: {trace_url}")
    return trace.id


def trace_agent_run(question: str, answer: str, agent_name: str) -> str:
    """
    Traces a single agent terminal run in Langfuse.
    Captures the question as input and the final answer as output.
    """
    lf    = get_langfuse_client()
    trace = lf.trace(
        name    = f"agent-run: {agent_name}",
        input   = {"question": question},
        output  = {"answer": answer[:500]},
        tags    = ["agent", "pmo", agent_name],
    )
    lf.flush()
    return trace.id


if __name__ == "__main__":
    print("\n── Langfuse observability self-test ─────────────────")

    print("\n1. Testing client connection...")
    lf = get_langfuse_client()
    print(f"   Connected to: {LANGFUSE_HOST}")

    print("\n2. Creating a sample PMO trace...")
    trace_id = trace_crew_run(
        crew_name = "pmo-crew",
        scope     = "Full Portfolio — self test",
        result    = (
            "Portfolio health is Amber. PRJ001 and PRJ002 require immediate "
            "attention due to schedule delays and budget overrun risks."
        ),
    )
    print(f"   Trace ID: {trace_id}")

    print("\n3. Creating a sample agent trace...")
    agent_trace_id = trace_agent_run(
        question   = "Which project is at highest risk?",
        answer     = "PRJ002 Customer Portal 2.0 — SPI=0.64, budget overrun escalated.",
        agent_name = "pmo-risk-analyst",
    )
    print(f"   Trace ID: {agent_trace_id}")

    print(f"\n── Open {LANGFUSE_HOST}/traces to view ──────────────")
    print("── Self-test complete ───────────────────────────────")
```

### Key Design Decisions Explained

**Why two tracing approaches:**

| Approach | Used for | How |
|---|---|---|
| `get_langfuse_callback` | Single agent (LangChain) | Automatic — every LLM + tool call captured |
| `trace_crew_run` | CrewAI crew | Manual — single summary trace after crew completes |

LangChain's callback system fires on every LLM call and tool invocation. CrewAI does not expose LangChain's callback hooks, so crew runs are traced manually with a single summary record.

**Why `lf.flush()` after every manual trace:**
Langfuse batches trace uploads for performance. `flush()` forces immediate upload — without it, traces may not appear in the UI if the process exits before the batch timer fires.

**Why `LANGFUSE_HOST` defaults to `http://localhost:3000`:**
When running the tracing module directly from the terminal during development, `localhost:3000` is a sensible default. In K3s the host is overridden by the ConfigMap to `http://langfuse-server:3000`.

### Test the Tracing Module

```bash
cd ~/pmo-copilot
source venv/bin/activate
python3 observability/pmo_tracing.py
```

Expected:
```
── Langfuse observability self-test ─────────────────

1. Testing client connection...
   Connected to: http://<linux-laptop-ip>:30300

2. Creating a sample PMO trace...
  [Langfuse] Trace recorded: http://<ip>:30300/trace/<uuid>
   Trace ID: <uuid>

3. Creating a sample agent trace...
   Trace ID: <uuid>

── Open http://<ip>:30300/traces to view ──────────────
── Self-test complete ───────────────────────────────
```

Open `http://<linux-laptop-ip>:30300` in your browser and navigate to **Traces** — you should see both test traces.

### Run the Agent with Full Tracing

```bash
python3 agents/pmo_risk_analyst.py "Which project is at highest risk?"
```

Open Langfuse → Traces. Click the `pmo-agent-run` trace. You will see:

- A nested hierarchy of spans
- Each LLM call with its input prompt and output text
- Each tool call with its input arguments and returned text
- Latency for each step
- Token counts per LLM call
- The session tagged as `single-agent-run`
- The user tagged as `pmo-analyst`

---

## Part B — Streamlit UI

### The Five-Page Application

The UI wraps everything built in Parts 2–4 into a browser interface.

| Page | Purpose |
|---|---|
| 🏠 Portfolio Overview | Live view of all CSV data — KPIs, tables, SPI trend chart |
| 🤖 Single Agent | Ask questions, watch reasoning steps, see Final Answer |
| 👥 Crew Analysis | Run the full 3-agent crew with progress tracking |
| 🧠 Memory Browser | Search stored analyses semantically |
| ℹ️ System Info | Connection health checks for all services |

### The Complete UI File — `ui/app.py`

```python
"""
PMO Copilot Streamlit UI
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

# Support both local dev and container (/app)
# expanduser("~/pmo-copilot") fails in container where ~ = /root
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

    total      = len(projects)
    on_track   = len(projects[projects["status"] == "On Track"])
    off_track  = len(projects[projects["status"] == "Off Track"])
    at_risk    = len(projects[projects["status"] == "At Risk"])
    open_risks = len(risks[risks["status"].isin(["Open", "Escalated"])])
    delayed_ms = len(milestones[milestones["delay_weeks"] > 0])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Projects",     total)
    c2.metric("On Track",           on_track)
    c3.metric("At Risk",            at_risk)
    c4.metric("Off Track",          off_track,
              delta=f"-{off_track}" if off_track else None)
    c5.metric("Open Risks",         open_risks)
    c6.metric("Delayed Milestones", delayed_ms)

    st.divider()

    st.subheader("Projects")
    st.dataframe(
        projects.style.applymap(rag_colour, subset=["status"]),
        use_container_width=True,
        hide_index=True,
    )

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

        st.markdown("**Step 1 — Checking memory...**")
        from memory.pmo_memory import retrieve_relevant_analyses, store_analysis
        memory_context = retrieve_relevant_analyses(question, k=3)

        if memory_context:
            with st.expander("🧠 Relevant past analyses found", expanded=False):
                st.text(memory_context[:800])
            st.success("Memory context injected into prompt")
        else:
            st.info("No relevant past analyses — starting fresh")

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

                # Langfuse callback inside thread — failures never break the UI
                try:
                    from observability.pmo_tracing import get_langfuse_callback
                    langfuse_cb = get_langfuse_callback(session_id="streamlit-agent")
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

        # Animated spinner — updates every 0.5s while agent runs in background
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
                    steps_md += f"- Output: {str(observation)[:300]}\n\n"

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

        # Progress bar with time-based stage labels
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
```

---

## Key Implementation Details

### The Streamlit Blocking Problem and Fix

Streamlit runs everything in a single main thread. When you call a function that takes 60–120 seconds (like an LLM agent), the entire UI freezes — no updates, no spinner, browser shows stale page.

The fix is to run the agent in a background thread and poll for results:

```python
# 1. Create a queue for the result
agent_queue = queue.Queue()

# 2. Define the work function
def run_agent_thread(q, question, memory_context):
    # ... all agent code here ...
    q.put({"status": "ok", "result": result})

# 3. Start thread
thread = threading.Thread(target=run_agent_thread, args=(...), daemon=True)
thread.start()

# 4. Poll while thread runs — UI stays responsive
while thread.is_alive():
    status_placeholder.markdown(f"{dots[i % len(dots)]} Agent thinking...")
    time.sleep(0.5)
    i += 1

# 5. Get result after thread completes
thread.join()
payload = agent_queue.get()
```

This pattern applies to any long-running operation in Streamlit. The `daemon=True` flag means the thread is automatically killed if the Streamlit process exits.

### Why `verbose=False` in the UI Executor

The terminal agent uses `verbose=True` which prints every Thought/Action/Observation to stdout. In the UI this would flood the Streamlit logs with no benefit to the user. Instead `return_intermediate_steps=True` captures all tool calls and makes them available for display in the UI expander.

### Why `sys.path` Uses `abspath(__file__)`

```python
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
```

`os.path.expanduser("~/pmo-copilot")` expands `~` to the home directory of the current user. In a Docker container, the process runs as root — `~` expands to `/root`, not `/app` where the code lives. Using `abspath(__file__)` finds the project root relative to the file itself, regardless of which user is running the process.

### Why Langfuse Callback Uses `try/except`

```python
try:
    from observability.pmo_tracing import get_langfuse_callback
    langfuse_cb = get_langfuse_callback(session_id="streamlit-agent")
    callbacks = [langfuse_cb]
except Exception:
    callbacks = []
```

If Langfuse is unreachable — network issue, pod restarting, wrong API key — the agent still runs. Observability failure never blocks the user. The `try/except` makes tracing optional at runtime, not a hard dependency.

### Why `@st.cache_data` on CSV Loaders

```python
@st.cache_data
def load_projects():
    return pd.read_csv(os.path.join(DATA_DIR, "projects.csv"))
```

Streamlit re-runs the entire script on every user interaction — button click, page change, slider move. Without caching, every interaction would re-read all four CSV files from disk. `@st.cache_data` caches the return value after the first call. Subsequent calls return the cached DataFrame instantly.

---

## Run the UI

```bash
cd ~/pmo-copilot
source venv/bin/activate
streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
```

Open from any device on your home network:
```
http://<linux-laptop-ip>:8501
```

---

## Page-by-Page Validation

**Portfolio Overview:**
- KPI metrics row shows 6 numbers
- Projects table has colour-coded status column
- SPI trend chart renders for PRJ001 and PRJ002
- Risks table sorted by score descending

**Single Agent:**
- Click any suggested question — it populates the text input
- Click Run Agent — animated spinner appears
- After 60–120 seconds — tool calls expander and Final Answer appear
- `Analysis stored in memory` confirmation shows at the bottom

**Crew Analysis:**
- Select Full Portfolio, click Run Crew Analysis
- Progress bar advances with stage labels
- Executive summary appears when complete

**Memory Browser:**
- Total Stored Analyses shows a number greater than zero
- Search `budget problems` — returns relevant past analyses
- Results use semantically similar content, not keyword matches

**System Info:**
- All three connection checks show green ✅

---

## Common Failures and Fixes

**Single Agent page hangs with no spinner update:**
The agent thread started but Ollama stopped responding. Open a new terminal:
```bash
curl http://<windows-laptop-ip>:11434/api/tags
```
If no response — restart Ollama on Windows.

**`ModuleNotFoundError: No module named 'memory'`:**
The `sys.path` fix is not in place. Confirm the file starts with:
```python
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
```

**Langfuse health check shows red on System Info page:**
```bash
curl -s http://127.0.0.1:30300/api/public/health
```
If returns `{"status":"OK"}` — the UI health check URL is wrong. Confirm `LANGFUSE_HOST` in `.env` uses the correct IP and port 30300.

**Crew Analysis page errors on import:**
```bash
cd ~/pmo-copilot
python3 -c "from crew.pmo_crew import schedule_agent; print('OK')"
```
Fix any import errors shown before re-running the UI.

---

## Validation Checkpoint

Before proceeding to Part 6, confirm:

```bash
# Tracing self-test passes
python3 observability/pmo_tracing.py

# UI starts without errors
streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
```

All five pages must load. Single Agent page must complete a run and show tool calls. Langfuse UI must show the resulting trace.

---

## What's Next

The system works end-to-end and is fully observable. In Part 6 we containerise the application with Docker and deploy it to K3s so it starts automatically on boot, restarts on failure, and runs identically on any machine.

→ [Part 6 — Containerisation and K3s Deployment](./06-deployment.md)