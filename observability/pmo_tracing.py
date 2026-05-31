"""
Phase 5 — PMO Observability Module
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
    Returns the trace URL for reference.
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
    Traces a single agent run — used by the single agent from Phase 2/3.
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