import csv
import random
import os
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/pmo-copilot/.env"))

DATA_DIR = os.getenv("DATA_DIR", os.path.expanduser("~/pmo-copilot/data"))
os.makedirs(DATA_DIR, exist_ok=True)

random.seed(42)

PROJECTS = [
    {"id": "PRJ001", "name": "ERP Modernisation",     "budget": 2500000, "team_size": 12, "domain": "Finance"},
    {"id": "PRJ002", "name": "Customer Portal 2.0",   "budget": 800000,  "team_size": 6,  "domain": "CX"},
    {"id": "PRJ003", "name": "Data Lake Migration",   "budget": 1200000, "team_size": 8,  "domain": "Data"},
    {"id": "PRJ004", "name": "Mobile App Relaunch",   "budget": 600000,  "team_size": 5,  "domain": "Digital"},
    {"id": "PRJ005", "name": "Cybersecurity Uplift",  "budget": 950000,  "team_size": 7,  "domain": "Security"},
]

RISK_TYPES = [
    "Resource unavailability",
    "Scope creep",
    "Integration failure",
    "Vendor delay",
    "Budget overrun",
    "Regulatory compliance",
    "Technical debt",
    "Key person dependency",
]

MITIGATION_ACTIONS = [
    "Engage backup resource from bench",
    "Conduct formal change control review",
    "Escalate to integration lead",
    "Issue vendor performance notice",
    "Request emergency budget review",
    "Engage compliance officer",
    "Schedule tech debt sprint",
    "Cross-train secondary resource",
]

STATUS_CHOICES = ["On Track", "At Risk", "Off Track"]
RAG_CHOICES    = ["Green", "Amber", "Red"]


def weighted_rag():
    return random.choices(RAG_CHOICES, weights=[0.5, 0.35, 0.15])[0]


def rag_to_spi(rag):
    if rag == "Green":
        return round(random.uniform(0.90, 1.10), 2)
    if rag == "Amber":
        return round(random.uniform(0.75, 0.89), 2)
    return round(random.uniform(0.55, 0.74), 2)


def rag_to_cpi(rag):
    if rag == "Green":
        return round(random.uniform(0.92, 1.08), 2)
    if rag == "Amber":
        return round(random.uniform(0.78, 0.91), 2)
    return round(random.uniform(0.60, 0.77), 2)


# ── 1. projects.csv ──────────────────────────────────────────────────────────

start_base = date(2025, 1, 6)

with open(os.path.join(DATA_DIR, "projects.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "project_id", "project_name", "domain", "budget",
        "team_size", "start_date", "planned_end_date", "status",
    ])
    for p in PROJECTS:
        duration_weeks = random.randint(24, 52)
        planned_end    = start_base + timedelta(weeks=duration_weeks)
        w.writerow([
            p["id"], p["name"], p["domain"], p["budget"],
            p["team_size"], start_base.isoformat(), planned_end.isoformat(),
            random.choice(STATUS_CHOICES),
        ])

print("✓  projects.csv written")


# ── 2. weekly_status.csv ─────────────────────────────────────────────────────

with open(os.path.join(DATA_DIR, "weekly_status.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "project_id", "week_number", "week_ending",
        "rag_status", "spi", "cpi",
        "percent_complete", "issues_open", "issues_closed",
        "team_morale", "budget_consumed_pct",
    ])
    for p in PROJECTS:
        pct = 0.0
        for wk in range(1, 53):
            week_end = start_base + timedelta(weeks=wk)
            rag      = weighted_rag()
            spi      = rag_to_spi(rag)
            cpi      = rag_to_cpi(rag)
            pct      = min(100.0, round(pct + random.uniform(1.0, 2.5), 1))
            w.writerow([
                p["id"], wk, week_end.isoformat(),
                rag, spi, cpi,
                pct,
                random.randint(0, 12),
                random.randint(0, 8),
                random.choice(["High", "Medium", "Low"]),
                round(min(100.0, pct * random.uniform(0.9, 1.15)), 1),
            ])

print("✓  weekly_status.csv written")


# ── 3. risks.csv ─────────────────────────────────────────────────────────────

with open(os.path.join(DATA_DIR, "risks.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "risk_id", "project_id", "week_raised",
        "risk_type", "probability", "impact",
        "risk_score", "status", "mitigation_action",
    ])
    risk_id = 1
    for p in PROJECTS:
        num_risks = random.randint(4, 8)
        for _ in range(num_risks):
            week_raised = random.randint(1, 40)
            prob        = round(random.uniform(0.1, 0.9), 2)
            impact      = round(random.uniform(0.2, 1.0), 2)
            score       = round(prob * impact, 2)
            idx         = random.randint(0, len(RISK_TYPES) - 1)
            w.writerow([
                f"RSK{risk_id:03d}", p["id"], week_raised,
                RISK_TYPES[idx],
                prob, impact, score,
                random.choice(["Open", "Mitigated", "Closed", "Escalated"]),
                MITIGATION_ACTIONS[idx],
            ])
            risk_id += 1

print("✓  risks.csv written")


# ── 4. milestones.csv ────────────────────────────────────────────────────────

MILESTONE_NAMES = [
    "Project kickoff",
    "Requirements sign-off",
    "Architecture approved",
    "Development sprint 1 complete",
    "Development sprint 2 complete",
    "System integration testing",
    "User acceptance testing",
    "Go-live",
]

with open(os.path.join(DATA_DIR, "milestones.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "milestone_id", "project_id", "milestone_name",
        "planned_date", "actual_date", "status", "delay_weeks",
    ])
    ms_id = 1
    for p in PROJECTS:
        current = start_base
        for name in MILESTONE_NAMES:
            gap          = timedelta(weeks=random.randint(3, 8))
            planned      = current + gap
            delay        = random.choices([0, 1, 2, 3, 4], weights=[0.4, 0.25, 0.2, 0.1, 0.05])[0]
            actual       = planned + timedelta(weeks=delay) if delay > 0 else planned
            ms_status    = "Delayed" if delay > 0 else "On Time"
            if planned > date.today():
                ms_status = "Planned"
                actual    = None
            w.writerow([
                f"MS{ms_id:03d}", p["id"], name,
                planned.isoformat(),
                actual.isoformat() if actual else "",
                ms_status, delay,
            ])
            current = planned
            ms_id  += 1

print("✓  milestones.csv written")

print("\n── Summary ──────────────────────────────────────────")
print(f"  Projects  : {len(PROJECTS)}")
print(f"  Weekly rows: {len(PROJECTS) * 52}")
print(f"  Data dir  : {DATA_DIR}")
print("─────────────────────────────────────────────────────")