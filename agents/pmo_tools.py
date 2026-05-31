"""
Shared PMO tools used by all crew agents.
Extracted from pmo_risk_analyst.py so CrewAI agents can import them.
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