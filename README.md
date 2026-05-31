# PMO Copilot — Local AI Portfolio Analysis

> A complete agentic AI system that analyses project portfolios, assesses risks, recalls previous assessments, and generates executive summaries — running entirely on your home network with zero cloud dependencies.

Built by **Mukesh Shende** as a hands-on weekend bootcamp to learn agentic AI architecture by building a real, working system from scratch.

---

## What This Is

PMO Copilot is a multi-agent AI system that acts as a PMO analyst. It reads project data from CSV files, reasons through schedule performance and delivery risks using the ReACT pattern, remembers previous analyses using vector embeddings, and produces executive-ready summaries.

Everything runs locally. No OpenAI. No Azure. No cloud APIs. After the initial setup you can disconnect the internet and the system continues working.

---

## A Note Before You Start

This project was built as a learning experiment — a hands-on attempt to understand agentic AI architecture by building a complete system step by step, using AI tools throughout the process.

The code has been tested and validated on the hardware and software versions listed in [TESTED_ON.md](./TESTED_ON.md). That said, local AI systems are sensitive to environment — LLM outputs vary between model versions, hardware affects inference speed and quality, and dependency combinations can behave differently across machines.

You are encouraged to follow along, learn from it, and adapt it to your setup. Read the documentation carefully before running each step. Apply your own judgement when things behave unexpectedly — they sometimes will. The troubleshooting sections in each part document the real problems encountered during the build and how they were resolved.

This is a learning lab, not a production system. Treat it as a starting point, not a blueprint.

---

## Architecture

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
│  │  Schedule Agent │ Delivery Agent │ Exec Summary │    │
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
│  Windows Laptop — Ollama                                 │
│  qwen2.5:7b + nomic-embed-text                           │
└──────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Version |
|---|---|---|
| LLM inference | Ollama — qwen2.5:7b | 0.24.x |
| Embeddings | nomic-embed-text | F16 |
| Agent framework | LangChain | 0.3.25 |
| Multi-agent crew | CrewAI | 0.86.0 |
| Vector memory | ChromaDB (embedded) | 1.5.9 |
| Observability | Langfuse (self-hosted) | 2.95.11 |
| UI | Streamlit | 1.45.1 |
| Orchestration | K3s | v1.35.5 |
| Python | Python | 3.12.3 |

---

## Hardware Requirements

| Machine | Role | Minimum |
|---|---|---|
| Linux laptop | K3s host — all services | 8GB RAM |
| Windows laptop | Ollama host — LLM inference | 8GB RAM, GPU optional |

> **Single machine:** Run both on one Linux host with at least 16GB RAM.

---

## Prerequisites

**On the Linux laptop:**
- Xubuntu 24.04 or Ubuntu 24.04 compatible
- K3s installed and running
- Docker installed
- Python 3.10+

**On the Windows laptop:**
- Ollama installed from [https://ollama.com](https://ollama.com)
- Models pulled:
```
  ollama pull qwen2.5:7b
  ollama pull nomic-embed-text
```
- `OLLAMA_HOST=0.0.0.0` set in Windows environment variables

See [Part 1](./docs/01-architecture.md) for complete setup instructions.

---

## Quick Start

For readers who have completed the prerequisites:

```bash
# Clone the repository
git clone https://github.com/mukeshshende/pmo-copilot.git
cd pmo-copilot

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools==69.5.1
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # set your Ollama IP, paths, and Langfuse keys

# Generate synthetic data
python3 data/generate_data.py

# Test single agent (terminal)
python3 agents/pmo_risk_analyst.py

# Build and deploy to K3s
docker build -t pmo-copilot:v1 .
docker save pmo-copilot:v1 -o /tmp/pmo-copilot-v1.tar
sudo k3s ctr images import /tmp/pmo-copilot-v1.tar
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl create secret generic pmo-secrets \
  --from-literal=LANGFUSE_PUBLIC_KEY=pk-lf-your-key \
  --from-literal=LANGFUSE_SECRET_KEY=sk-lf-your-key
kubectl apply -f k8s/langfuse-pvc.yaml
kubectl apply -f k8s/langfuse-postgres.yaml
kubectl apply -f k8s/langfuse-server.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Access points after deployment:
```
PMO Copilot UI  : http://<linux-laptop-ip>:30501
Langfuse Traces : http://<linux-laptop-ip>:30300
```

---

## Documentation — Step by Step

Follow the parts in order. Each part builds on the previous.

| Part | Topic | Git Tag |
|---|---|---|
| [Part 1 — Architecture and Foundation](./docs/01-architecture.md) | Hardware setup, core concepts, synthetic data | `part-1-foundation` |
| [Part 2 — Building Your First ReACT Agent](./docs/02-single-agent.md) | LangChain, tools, ReACT loop | `part-2-single-agent` |
| [Part 3 — Giving Your Agent Memory](./docs/03-memory.md) | ChromaDB, vector embeddings, semantic search | `part-3-memory` |
| [Part 4 — Building a Multi-Agent Crew](./docs/04-crew.md) | CrewAI, agent roles, sequential execution | `part-4-crew` |
| [Part 5 — Observability and UI](./docs/05-observability-ui.md) | Langfuse, Streamlit, threading pattern | `part-5-observability-ui` |
| [Part 6 — Containerisation and K3s Deployment](./docs/06-deployment.md) | Docker, K3s manifests, rolling updates | `part-6-deployment` |

To checkout the code at any specific part:
```bash
git checkout part-3-memory
```

---

## Repository Structure

```
pmo-copilot/
├── .env.example              ← config template — copy to .env
├── .gitignore
├── Dockerfile
├── .dockerignore
├── requirements.txt          ← 14 direct dependencies
├── TESTED_ON.md              ← exact versions and constraints
│
├── data/
│   ├── generate_data.py      ← synthetic PMO data generator
│   └── *.csv                 ← 5 projects, 52 weeks of data
│
├── agents/
│   ├── pmo_tools.py          ← 6 shared LangChain tools
│   └── pmo_risk_analyst.py   ← single ReACT agent
│
├── memory/
│   └── pmo_memory.py         ← ChromaDB store and retrieve
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
├── scripts/
│   ├── start-demo.sh         ← startup script
│   ├── demo-status.sh        ← health check
│   └── update-ollama-ip.sh   ← emergency IP change helper
│
└── docs/
    ├── 01-architecture.md
    ├── 02-single-agent.md
    ├── 03-memory.md
    ├── 04-crew.md
    ├── 05-observability-ui.md
    └── 06-deployment.md
```

---

## Useful Commands

```bash
# Check all pod status
kubectl get pods -n pmo-copilot

# View live app logs
kubectl logs deployment/pmo-copilot -f -n pmo-copilot

# Restart app after rebuild
kubectl rollout restart deployment pmo-copilot -n pmo-copilot

# Check system health
./scripts/demo-status.sh

# Update Ollama IP if Windows laptop IP changes
./scripts/update-ollama-ip.sh <new-ip>

# Tear everything down
kubectl delete namespace pmo-copilot
```

---

## Agentic AI Concepts Covered

| Concept | Where it appears |
|---|---|
| ReACT reasoning loop | Part 2 — Thought/Action/Observation pattern |
| Tool calling | Part 2 — agent autonomously selects tools |
| Prompt engineering | Part 2 — docstrings as tool descriptions |
| Vector embeddings | Part 3 — 768-dimension semantic vectors |
| Semantic memory | Part 3 — retrieval by meaning not keywords |
| Multi-agent orchestration | Part 4 — CrewAI sequential crew |
| Agent specialisation | Part 4 — role, goal, backstory per agent |
| Context passing | Part 4 — outputs flow between agents |
| Observability | Part 5 — every LLM call traced |
| Container deployment | Part 6 — Docker + K3s |

---

## Tested On

See [TESTED_ON.md](./TESTED_ON.md) for exact software versions, known constraints, and alternative model options.

---

## Author

Built by **Mukesh Shende**