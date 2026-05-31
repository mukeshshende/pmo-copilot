# Part 1 — Architecture and Foundation

## What We Are Building

A complete AI PMO Copilot that analyses project portfolio data, assesses risks, tracks trends, recalls previous assessments, and generates executive summaries.

It runs entirely on your home network. No OpenAI. No Azure. No cloud APIs of any kind. After the initial setup, you can disconnect the internet and everything continues working.

This is a learning lab. The goal is to understand agentic AI architecture by building a real, working system — not a toy example.

By the end of this series you will have:

- A working multi-agent AI system
- Persistent semantic memory
- Full observability with trace capture
- A browser-based UI
- Everything running on Kubernetes

---

## Hardware Requirements

You need two machines on the same local network:

| Machine | Role | Minimum Spec |
|---|---|---|
| Linux laptop | Runs K3s — hosts all services | 8GB RAM, 20GB free disk |
| Windows laptop | Runs Ollama — LLM inference | 8GB RAM, GPU optional |

The Linux machine hosts Kubernetes (K3s), the containerised application, Langfuse observability, and the Postgres database. The Windows machine runs Ollama which serves all LLM inference requests over the local network.

This split exists because LLM inference is memory-intensive. Keeping it on a separate machine protects the K3s node from memory pressure.

> **Single machine alternative:** If you only have one machine, you can run Ollama and K3s on the same Linux host — but you will need at least 16GB RAM.

---

## The Five Core Concepts

Before writing any code, understand these five concepts. Every component in this system maps to one of them.

### 1. ReACT — Reasoning and Acting

ReACT is the reasoning pattern your agents use. Instead of answering a question immediately, the agent loops through:

```
Thought     → "I need to check schedule variance for Project Alpha"
Action      → call tool: get_weekly_status("PRJ001")
Observation → SPI=0.72, 3 delayed milestones
Thought     → "SPI below 0.8 indicates schedule risk"
Action      → call tool: get_project_risks("PRJ001")
Observation → RSK001 budget overrun score=0.76 escalated
Thought     → "I now have enough information to answer"
Final Answer → "PRJ001 is at HIGH risk. SPI declined..."
```

The agent decides which tools to call based on what it observes. Nobody hardcodes the sequence. The LLM reasons its way to the answer.

### 2. LangChain — The Wiring

LangChain connects your LLM to your tools, your memory, and your prompts. Think of it as the wiring harness of the system. It handles the ReACT loop, parses tool calls, manages conversation state, and provides a callback system for observability.

### 3. CrewAI — The Team

CrewAI lets you define a team of agents, each with a role, goal, and backstory. The Coordinator delegates work to specialists. Each specialist has access only to the tools relevant to their role. Outputs flow from one agent to the next.

Think of it as the org chart of your AI system.

### 4. ChromaDB — The Memory

ChromaDB is a vector database that runs embedded — no separate server needed. When an agent produces an analysis, you store it as a vector embedding. Later, when a similar question is asked, ChromaDB finds the most semantically similar past analyses and injects them into the prompt.

This is how the system remembers previous assessments across sessions.

### 5. Langfuse — The Observability

Langfuse captures every LLM call, tool call, and agent step as a trace. You get a web UI showing exactly what your agents did, how long each step took, and what tokens were consumed. It runs as a pod inside K3s — no cloud required.

---

## Dependency Matrix

Every component runs locally. This table confirms zero internet dependency after initial setup.

| Component | Runs On | External Dependency | Internet Required |
|---|---|---|---|
| Streamlit UI | K3s / Linux | None | **NO** |
| CrewAI | K3s / Linux | None | **NO** |
| LangChain | K3s / Linux | None | **NO** |
| ChromaDB | K3s / Linux | None (embedded) | **NO** |
| Langfuse server | K3s / Linux | None (self-hosted) | **NO** |
| PostgreSQL | K3s / Linux | None (self-hosted) | **NO** |
| Ollama | Windows laptop | None (local inference) | **NO** |
| qwen2.5:7b model | Windows laptop | Pre-downloaded once | **NO** |
| nomic-embed-text | Windows laptop | Pre-downloaded once | **NO** |
| CSV data | Linux filesystem | None | **NO** |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  K3s Cluster — Linux Laptop                             │
│                                                         │
│  ┌──────────────┐    ┌────────────────────────────┐     │
│  │ Streamlit UI │    │ Langfuse Server :30300     │     │
│  │ :30501       │    └──────────────┬─────────────┘     │
│  └──────┬───────┘                   │                   │
│         │                    ┌──────▼──────┐            │
│  ┌──────▼────────────────┐   │  Postgres   │            │
│  │  CrewAI Coordinator   │   │  PVC 2Gi    │            │
│  └──────┬────────────────┘   └─────────────┘            │
│         │                                               │
│  ┌──────▼──────────────────────────────────────────┐    │
│  │  Specialist Agents                              │    │
│  │  Schedule  │  Delivery  │  Executive Summary    │    │
│  └──────┬──────────────────────────────────────────┘    │
│         │                                               │
│  ┌──────▼──────┐    ┌──────────────┐                    │
│  │  LangChain  │    │   ChromaDB   │                    │
│  │  tools      │    │   memory     │                    │
│  └──────┬──────┘    └──────────────┘                    │
│         │                                               │
└─────────┼───────────────────────────────────────────────┘
          │ http://windows-laptop-ip:11434
┌─────────▼────────────────────────────────────────────────┐
│  Windows Laptop                                          │
│  Ollama — qwen2.5:7b + nomic-embed-text                  │
└──────────────────────────────────────────────────────────┘
```

---

## Network Design

The two machines communicate over your home LAN.

| Service | Host | Port | Access |
|---|---|---|---|
| PMO Copilot UI | Linux laptop | 30501 | LAN browser |
| Langfuse UI | Linux laptop | 30300 | LAN browser |
| Ollama API | Windows laptop | 11434 | Internal only |
| Postgres | Linux laptop | 5432 | Internal K3s only |

---

## Project Structure

```
pmo-copilot/
├── .env.example              ← config template
├── .gitignore
├── Dockerfile                ← python:3.12-slim
├── .dockerignore
├── requirements.txt          ← minimal direct dependencies
├── TESTED_ON.md              ← exact versions
│
├── data/
│   ├── generate_data.py      ← synthetic data generator
│   └── *.csv                 ← 5 projects, 52 weeks
│
├── agents/
│   ├── pmo_tools.py          ← 6 shared LangChain tools
│   └── pmo_risk_analyst.py   ← single ReACT agent
│
├── memory/
│   └── pmo_memory.py         ← ChromaDB store/retrieve
│
├── crew/
│   └── pmo_crew.py           ← CrewAI 3-agent crew
│
├── observability/
│   └── pmo_tracing.py        ← Langfuse trace functions
│
├── ui/
│   └── app.py                ← Streamlit 5-page UI
│
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml.example
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── langfuse-pvc.yaml
│   ├── langfuse-postgres.yaml
│   └── langfuse-server.yaml
│
└── scripts/
    ├── start-demo.sh
    └── demo-status.sh
```

---

## Prerequisites

### On the Linux laptop

**Install K3s:**

```bash
curl -sfL https://get.k3s.io | sh -
```

Configure kubectl without sudo:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
echo 'export KUBECONFIG=~/.kube/config' >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
kubectl get nodes
```

Expected:
```
NAME        STATUS   ROLES                  AGE   VERSION
<hostname>  Ready    control-plane,master   1m    v1.35.x+k3s1
```

**Install Docker:**

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker
```

**Fix Docker DNS** — required on K3s machines:

```bash
sudo bash -c 'cat > /etc/docker/daemon.json << EOF
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}
EOF'
sudo systemctl restart docker
```

Verify:

```bash
docker --version
docker compose version
```

**Install Python tools:**

```bash
sudo apt-get install -y python3-venv python3-pip curl git
```

---

### On the Windows laptop

**Install Ollama** from [https://ollama.com](https://ollama.com).

Pull the required models:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

Verify:

```bash
ollama list
```

Expected:
```
NAME                    SIZE
qwen2.5:7b             4.7 GB
nomic-embed-text       274 MB
```

**Allow LAN access to Ollama.**

By default Ollama only listens on localhost. To allow the Linux laptop to reach it, add a system environment variable on Windows:

```
Variable name  : OLLAMA_HOST
Variable value : 0.0.0.0
```

Go to: System Properties → Advanced → Environment Variables → System variables → New

Then restart Ollama.

Verify from the Linux laptop:

```bash
curl http://<windows-laptop-ip>:11434/api/tags
```

Expected: JSON response listing your models.

---

## Environment Setup

Clone the repository on the Linux laptop:

```bash
git clone https://github.com/mukeshshende/pmo-copilot.git
cd pmo-copilot
```

Create Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install --upgrade pip setuptools==69.5.1
pip install -r requirements.txt
```

Copy and configure `.env`:

```bash
cp .env.example .env
nano .env
```

Set these values replacing the placeholders:

```bash
OLLAMA_BASE_URL=http://<windows-laptop-ip>:11434
OLLAMA_API_BASE=http://<windows-laptop-ip>:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
DATA_DIR=/home/<your-username>/pmo-copilot/data
CHROMA_DIR=/home/<your-username>/pmo-copilot/memory/chroma_db
LANGFUSE_HOST=http://<linux-laptop-ip>:30300
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
```

> The Langfuse keys will be generated in Part 5 after deploying Langfuse to K3s. Leave the placeholders for now.

---

## Synthetic Data Generation

The system analyses PMO portfolio data. We use synthetic CSV data so you can follow along without real project data.

The generator creates:

| File | Contents |
|---|---|
| `projects.csv` | 5 projects across Finance, CX, Data, Digital, Security domains |
| `weekly_status.csv` | 52 weeks × 5 projects = 260 rows with RAG status, SPI, CPI |
| `risks.csv` | ~34 risks with probability, impact, score, and mitigation actions |
| `milestones.csv` | 40 milestones (8 per project) with planned dates and delay tracking |

Generate the data:

```bash
source venv/bin/activate
python3 data/generate_data.py
```

Expected output:

```
✓  projects.csv written
✓  weekly_status.csv written
✓  risks.csv written
✓  milestones.csv written

── Summary ──────────────────────────────────────────
  Projects  : 5
  Weekly rows: 260
  Data dir  : /home/<user>/pmo-copilot/data
─────────────────────────────────────────────────────
```

Verify row counts:

```bash
wc -l data/*.csv
```

Expected:

```
   41 data/milestones.csv
    6 data/projects.csv
   35 data/risks.csv
  261 data/weekly_status.csv
```

> The generator uses `random.seed(42)` — every run produces identical output. This makes debugging deterministic.

Preview the projects:

```bash
cat data/projects.csv
```

Expected:

```
project_id,project_name,domain,budget,team_size,start_date,planned_end_date,status
PRJ001,ERP Modernisation,Finance,2500000,12,2025-01-06,2025-11-10,On Track
PRJ002,Customer Portal 2.0,CX,800000,6,2025-01-06,2025-06-23,Off Track
PRJ003,Data Lake Migration,Data,1200000,8,2025-01-06,2025-12-08,On Track
PRJ004,Mobile App Relaunch,Digital,600000,5,2025-01-06,2025-09-29,On Track
PRJ005,Cybersecurity Uplift,Security,950000,7,2025-01-06,2026-01-05,On Track
```

Notice PRJ002 is already `Off Track` with a planned end date in the past. This gives your agents something genuinely problematic to analyse.

---

## Validation Checkpoint

Before proceeding to Part 2, confirm all prerequisites are met:

```bash
# Python version — needs 3.10+
python3 --version

# K3s node ready
kubectl get nodes

# Docker working
docker ps

# Ollama reachable from Linux laptop
curl http://<windows-laptop-ip>:11434/api/tags

# Data files exist
ls -lh data/*.csv

# All Python packages installed
source venv/bin/activate
python3 -c "import langchain, crewai, chromadb, streamlit; print('All packages OK')"
```

All six checks passing means you are ready for Part 2.

---

## What's Next

In Part 2 we build the first agent — a PMO Risk Analyst that reads the CSV data, reasons through it using the ReACT loop, and produces grounded risk assessments citing specific SPI values and risk scores.

→ [Part 2 — Building Your First ReACT Agent](./02-single-agent.md)