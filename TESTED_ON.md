# Tested On

This project was built and tested on the following hardware and software.
If your versions differ significantly, some steps may need adjustment.

## Hardware

| Machine | Spec | Role |
|---|---|---|
| Linux laptop | Xubuntu 24.04 LTS, 8GB RAM minimum | K3s host — runs all services |
| Windows 11 laptop | Ryzen 7, RTX 5050 GPU, 24GB RAM | Ollama host — LLM inference |

## Software Versions

| Component | Version | Notes |
|---|---|---|
| OS (K3s host) | Xubuntu 24.04 LTS | Ubuntu 24.04 compatible |
| Python | 3.12.3 | 3.10+ required |
| K3s | v1.35.5+k3s1 | Single node |
| Docker | 26.x | Used for image builds only |
| Ollama | 0.24.x | Running on Windows laptop |
| qwen2.5:7b | Q4_K_M quantisation | Primary LLM — 4.7GB |
| nomic-embed-text | F16 | Embeddings — 274MB |
| LangChain | 0.3.25 | |
| langchain-ollama | 0.3.3 | |
| langchain-chroma | 0.2.4 | |
| langchain-community | 0.3.24 | |
| CrewAI | 0.86.0 | |
| ChromaDB | 1.5.9 | Embedded mode — no server needed |
| Langfuse | 2.95.11 | Self-hosted in K3s |
| Streamlit | 1.45.1 | |
| pandas | 2.2.3 | |
| python-dotenv | 1.1.0 | |
| setuptools | 69.5.1 | Required for pkg_resources on Python 3.12 |

## Ollama Models Required

Pull these on the Windows laptop before starting:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

## Known Version Constraints

- **setuptools must be 69.5.1** — newer versions break `pkg_resources` import in CrewAI 0.86.0 on Python 3.12
- **CrewAI LLM must use `ollama/` prefix** — `model="ollama/qwen2.5:7b"` not `model="qwen2.5:7b"`
- **requirements.txt uses direct deps only** — `pip freeze` output causes packaging version conflicts in Docker
- **K3s and Docker have separate image stores** — must run `docker save | k3s ctr images import` after every build
- **Docker DNS on K3s machines** — add `{"dns":["8.8.8.8","8.8.4.4"]}` to `/etc/docker/daemon.json`

## Minimum Hardware Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| K3s host RAM | 4GB | 8GB |
| K3s host disk | 20GB free | 50GB free |
| Ollama host RAM | 8GB | 16GB+ |
| Ollama host GPU | None (CPU only) | 6GB+ VRAM |

## Alternative LLM Options

If `qwen2.5:7b` is too large for your hardware, these smaller models work:

| Model | Size | Quality |
|---|---|---|
| `llama3.2:3b` | 2GB | Good for simple queries |
| `qwen2.5:7b` | 4.7GB | Recommended — best reasoning |
| `gpt-oss:20b` | 13GB | Best quality if GPU has capacity |
