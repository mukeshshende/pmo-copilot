# Part 6 — Containerisation and K3s Deployment

## What We Are Building

A fully containerised deployment where every service runs inside K3s — the PMO Copilot application, Langfuse observability, and the Postgres database. After this part the system starts automatically on boot, restarts on failure, and is accessible from any device on your home network.

By the end of this part you will have:

- A Docker image containing the PMO Copilot application
- All services running as pods in the `pmo-copilot` K3s namespace
- Automatic restarts via K3s health probes
- Persistent storage for ChromaDB memory and Langfuse traces
- A single command to check system health

---

## Architecture Overview

```
K3s cluster — pmo-copilot namespace
├── pmo-copilot pod        :30501  ← Streamlit UI + Agents
├── langfuse-server pod    :30300  ← Observability UI
├── langfuse-postgres pod  :5432   ← Internal only
└── PVC 2Gi                        ← Postgres data on Dell disk

Windows laptop
└── Ollama                 :11434  ← LLM inference (external)
```

Docker is used only for building images. K3s uses its own container runtime (containerd) — they are completely separate.

---

## Important — Update These Values Before Deploying

Three files contain values specific to the build environment. Update them to match your setup before applying any manifests.

**`k8s/configmap.yaml` — Windows laptop IP:**
```yaml
OLLAMA_BASE_URL: "http://<your-windows-laptop-ip>:11434"
OLLAMA_API_BASE: "http://<your-windows-laptop-ip>:11434"
```

**`k8s/langfuse-server.yaml` — Linux laptop IP:**
```yaml
- name: NEXTAUTH_URL
  value: "http://<your-linux-laptop-ip>:30300"
```

**`k8s/deployment.yaml` — Linux username in hostPath volumes:**
```yaml
volumes:
  - name: data-volume
    hostPath:
      path: /home/<your-username>/pmo-copilot/data
  - name: chroma-volume
    hostPath:
      path: /home/<your-username>/pmo-copilot/memory/chroma_db
```

Find your Linux username:
```bash
echo $USER
```

Find your Linux laptop IP:
```bash
hostname -I | awk '{print $1}'
```

---

## The Dockerfile

```dockerfile
FROM python:3.12-slim

# System dependencies needed by chromadb and crewai
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first — Docker caches this layer
# so rebuilds are fast if only code changes
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools==69.5.1
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full project
COPY . .

# Create directories that must exist at runtime
RUN mkdir -p /app/memory/chroma_db /app/data

# Expose Streamlit port
EXPOSE 8501

# Health check — confirms Streamlit is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Streamlit
CMD ["streamlit", "run", "ui/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
```

### Key Dockerfile Decisions

**Why `python:3.12-slim` not `python:3.12`:**
The full Python image includes many packages not needed at runtime — compilers, documentation, test tools. `slim` strips these down to ~50MB base. The application installs only what it needs via `requirements.txt`.

**Why `COPY requirements.txt .` before `COPY . .`:**
Docker builds in layers. Each instruction creates a cached layer. By copying `requirements.txt` first and running pip install before copying application code, the expensive pip install step is only re-run when `requirements.txt` changes. Code changes alone use the cached pip layer — rebuilds go from 15 minutes to under 2 minutes.

**Why `setuptools==69.5.1` installed before `-r requirements.txt`:**
CrewAI 0.86.0 imports `pkg_resources` which was removed from Python 3.12's standard library. It is provided by `setuptools`. Installing a specific version before the main requirements ensures the correct version is in place before CrewAI's dependencies are resolved.

**Why `mkdir -p /app/memory/chroma_db /app/data`:**
When K3s mounts the hostPath volumes, the mount points must exist inside the container. If the directories don't exist, the volume mount fails silently and the application cannot find its data. Creating them in the Dockerfile guarantees they exist regardless of mount status.

**Why `--server.headless=true`:**
In a container there is no browser to auto-open. Headless mode suppresses the browser launch attempt and runs Streamlit as a pure server.

---

## The `.dockerignore` File

The `.dockerignore` file prevents large directories from being copied into the build context:

```
venv/
.venv/
memory/chroma_db/
*.tar
.env
.git/
__pycache__/
*.pyc
```

Without `.dockerignore` the build context would include the entire Python virtual environment (1.5GB) and ChromaDB data. With it, the build context is under 2MB — dramatically faster builds.

---

## The `requirements.txt` — Direct Dependencies Only

```
# Core LLM and agent frameworks
langchain==0.3.25
langchain-ollama==0.3.3
langchain-community==0.3.24
langchain-chroma==0.2.4
crewai==0.86.0

# Memory
chromadb==1.5.9

# Observability
langfuse==2.36.2

# UI
streamlit==1.45.1

# Data
pandas==2.2.3
faker==37.1.0

# Config
python-dotenv==1.1.0

# HTTP
requests==2.34.2

# Required by crewai on Python 3.12
setuptools==69.5.1
```

**Why not `pip freeze` output:**
`pip freeze` pins every transitive dependency to an exact version. In a clean Docker environment the dependency resolver is stricter than in a development venv — pinned transitive dependencies frequently conflict. For example, `langfuse==2.36.2` requires `packaging<24.0` but `build==1.5.0` requires `packaging>=24.0`. With direct dependencies only, pip resolves transitive versions freely and finds a compatible set.

---

## Fix Docker DNS

On machines running K3s, the system DNS configuration uses `systemd-resolved` with a stub resolver at `127.0.0.53`. Docker containers cannot reach this address and fail to resolve `deb.debian.org` during `apt-get update`.

Fix by telling Docker to use public DNS:

```bash
sudo bash -c 'cat > /etc/docker/daemon.json << EOF
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}
EOF'
sudo systemctl restart docker
```

Verify Docker containers can resolve DNS:

```bash
docker run --rm python:3.12-slim python3 -c "import socket; print(socket.gethostbyname('deb.debian.org'))"
```

Expected: an IP address, not an error.

---

## Build the Docker Image

```bash
cd ~/pmo-copilot
docker build -t pmo-copilot:v1 .
```

Expected build stages:
```
[1/8] FROM python:3.12-slim          ← base image
[2/8] RUN apt-get update             ← gcc, g++, curl
[3/8] WORKDIR /app
[4/8] COPY requirements.txt          ← fast
[5/8] RUN pip install setuptools     ← 30 seconds
[6/8] RUN pip install -r requirements.txt  ← 8-15 minutes
[7/8] COPY . .                       ← fast
[8/8] RUN mkdir -p ...               ← fast
```

Expected final line:
```
naming to docker.io/library/pmo-copilot:v1
```

Verify the image exists:
```bash
docker images | grep pmo-copilot
```

Expected:
```
pmo-copilot   v1   <hash>   2 minutes ago   ~2GB
```

---

## Import Image into K3s

K3s uses containerd as its container runtime — completely separate from Docker. An image built with `docker build` is not visible to K3s until explicitly imported.

```bash
# Export from Docker
docker save pmo-copilot:v1 -o /tmp/pmo-copilot-v1.tar

# Import into K3s containerd
sudo k3s ctr images import /tmp/pmo-copilot-v1.tar

# Verify K3s can see it
sudo k3s ctr images list | grep pmo-copilot
```

Expected:
```
docker.io/library/pmo-copilot:v1   ...   560.1 MiB   linux/amd64
```

This import step is required every time you rebuild the image.

---

## K3s Manifests

### Namespace — `k8s/namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: pmo-copilot
```

A namespace isolates all PMO Copilot resources from K3s system pods. Everything in this series lives in the `pmo-copilot` namespace.

### ConfigMap — `k8s/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pmo-config
  namespace: pmo-copilot
data:
  OLLAMA_BASE_URL: "http://<windows-laptop-ip>:11434"
  OLLAMA_API_BASE: "http://<windows-laptop-ip>:11434"
  OLLAMA_MODEL: "qwen2.5:7b"
  OLLAMA_EMBED_MODEL: "nomic-embed-text"
  DATA_DIR: "/app/data"
  CHROMA_DIR: "/app/memory/chroma_db"
  LANGFUSE_HOST: "http://langfuse-server:3000"
```

The ConfigMap replaces the `.env` file for pods running in K3s. Every key becomes an environment variable inside the container. `LANGFUSE_HOST` uses K3s internal DNS (`langfuse-server:3000`) — not the external NodePort address.

### Secret — `k8s/secret.yaml.example`

```yaml
# Copy to secret.yaml and fill in your actual Langfuse API keys
# Never commit secret.yaml to git
apiVersion: v1
kind: Secret
metadata:
  name: pmo-secrets
  namespace: pmo-copilot
type: Opaque
stringData:
  LANGFUSE_PUBLIC_KEY: "pk-lf-your-public-key-here"
  LANGFUSE_SECRET_KEY: "sk-lf-your-secret-key-here"
```

Secrets store sensitive values separately from ConfigMaps. Kubernetes base64-encodes the values at rest. The `secret.yaml.example` template is committed to git — the actual `secret.yaml` with real keys is in `.gitignore`.

Create the secret via kubectl (safer than a file with real keys):
```bash
kubectl create secret generic pmo-secrets \
  --from-literal=LANGFUSE_PUBLIC_KEY=pk-lf-your-actual-key \
  --from-literal=LANGFUSE_SECRET_KEY=sk-lf-your-actual-key \
  -n pmo-copilot
```

### PMO Copilot Deployment — `k8s/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pmo-copilot
  namespace: pmo-copilot
  labels:
    app: pmo-copilot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pmo-copilot
  template:
    metadata:
      labels:
        app: pmo-copilot
    spec:
      containers:
        - name: pmo-copilot
          image: pmo-copilot:v1
          imagePullPolicy: Never
          ports:
            - containerPort: 8501
          envFrom:
            - configMapRef:
                name: pmo-config
            - secretRef:
                name: pmo-secrets
          volumeMounts:
            - name: data-volume
              mountPath: /app/data
            - name: chroma-volume
              mountPath: /app/memory/chroma_db
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /_stcore/health
              port: 8501
            initialDelaySeconds: 60
            periodSeconds: 30
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /_stcore/health
              port: 8501
            initialDelaySeconds: 30
            periodSeconds: 10
            failureThreshold: 3
      volumes:
        - name: data-volume
          hostPath:
            path: /home/<your-username>/pmo-copilot/data
            type: Directory
        - name: chroma-volume
          hostPath:
            path: /home/<your-username>/pmo-copilot/memory/chroma_db
            type: Directory
```

**Key fields explained:**

| Field | Value | Why |
|---|---|---|
| `imagePullPolicy: Never` | Never | Uses local image — never attempts registry pull |
| `envFrom: configMapRef` | pmo-config | All ConfigMap keys become env vars |
| `envFrom: secretRef` | pmo-secrets | Langfuse API keys injected securely |
| `resources.requests` | 512Mi / 250m | Minimum guaranteed resources |
| `resources.limits` | 1Gi / 1000m | Maximum allowed — protects 8GB RAM node |
| `livenessProbe` | `/_stcore/health` | K3s restarts pod if health fails 3 times |
| `readinessProbe` | `/_stcore/health` | K3s waits for ready before routing traffic |
| `hostPath volumes` | Dell filesystem | Data and memory persist outside the container |

### PMO Copilot Service — `k8s/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: pmo-copilot
  namespace: pmo-copilot
  labels:
    app: pmo-copilot
spec:
  type: NodePort
  selector:
    app: pmo-copilot
  ports:
    - name: streamlit
      protocol: TCP
      port: 8501
      targetPort: 8501
      nodePort: 30501
```

NodePort exposes the service on port 30501 of every node's IP. Access the UI at `http://<linux-laptop-ip>:30501` from any device on the home network. Kubernetes NodePort range is 30000–32767.

### Langfuse PVC — `k8s/langfuse-pvc.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: langfuse-postgres-pvc
  namespace: pmo-copilot
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 2Gi
```

A PersistentVolumeClaim reserves 2GB of storage on the Dell's local disk for Postgres data. The `local-path` storage class is built into K3s — no additional storage configuration needed. `WaitForFirstConsumer` binding mode means the PVC stays `Pending` until the first pod mounts it.

### Langfuse Postgres — `k8s/langfuse-postgres.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langfuse-postgres
  namespace: pmo-copilot
  labels:
    app: langfuse-postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: langfuse-postgres
  template:
    metadata:
      labels:
        app: langfuse-postgres
    spec:
      containers:
        - name: postgres
          image: postgres:15-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_USER
              value: "langfuse"
            - name: POSTGRES_PASSWORD
              value: "langfuse_pass"
            - name: POSTGRES_DB
              value: "langfuse"
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
          readinessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - langfuse
            initialDelaySeconds: 10
            periodSeconds: 5
            failureThreshold: 6
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: langfuse-postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: langfuse-postgres
  namespace: pmo-copilot
  labels:
    app: langfuse-postgres
spec:
  type: ClusterIP
  selector:
    app: langfuse-postgres
  ports:
    - port: 5432
      targetPort: 5432
```

Postgres uses a `ClusterIP` service — accessible only from within the K3s cluster. No external exposure. The `pg_isready` readiness probe confirms the database is accepting connections before Langfuse server tries to connect.

### Langfuse Server — `k8s/langfuse-server.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langfuse-server
  namespace: pmo-copilot
  labels:
    app: langfuse-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: langfuse-server
  template:
    metadata:
      labels:
        app: langfuse-server
    spec:
      containers:
        - name: langfuse
          image: langfuse/langfuse:2
          ports:
            - containerPort: 3000
          env:
            - name: DATABASE_URL
              value: "postgresql://langfuse:langfuse_pass@langfuse-postgres:5432/langfuse"
            - name: NEXTAUTH_SECRET
              value: "pmo-copilot-secret-key-2026"
            - name: SALT
              value: "pmo-copilot-salt-2026"
            - name: NEXTAUTH_URL
              value: "http://<your-linux-laptop-ip>:30300"
            - name: TELEMETRY_ENABLED
              value: "false"
            - name: LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES
              value: "false"
            - name: HOSTNAME
              value: "0.0.0.0"
          resources:
            requests:
              memory: "256Mi"
              cpu: "200m"
            limits:
              memory: "512Mi"
              cpu: "1000m"
          readinessProbe:
            httpGet:
              path: /api/public/health
              port: 3000
            initialDelaySeconds: 60
            periodSeconds: 15
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: /api/public/health
              port: 3000
            initialDelaySeconds: 90
            periodSeconds: 30
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: langfuse-server
  namespace: pmo-copilot
  labels:
    app: langfuse-server
spec:
  type: NodePort
  selector:
    app: langfuse-server
  ports:
    - name: http
      protocol: TCP
      port: 3000
      targetPort: 3000
      nodePort: 30300
```

`DATABASE_URL` uses K3s internal DNS — `langfuse-postgres` resolves to the Postgres ClusterIP service within the namespace. `readinessProbe initialDelaySeconds: 60` gives Langfuse time to run database migrations on first start.

---

## Deploy Everything

### Step 1 — Create namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

Set as default namespace for this session:

```bash
kubectl config set-context --current --namespace=pmo-copilot
```

### Step 2 — Apply ConfigMap

```bash
kubectl apply -f k8s/configmap.yaml
```

### Step 3 — Create Secret

```bash
kubectl create secret generic pmo-secrets \
  --from-literal=LANGFUSE_PUBLIC_KEY=pk-lf-your-actual-key \
  --from-literal=LANGFUSE_SECRET_KEY=sk-lf-your-actual-key
```

### Step 4 — Deploy Langfuse storage

```bash
kubectl apply -f k8s/langfuse-pvc.yaml
```

### Step 5 — Deploy Langfuse Postgres

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

### Step 6 — Deploy Langfuse server

```bash
kubectl apply -f k8s/langfuse-server.yaml
```

Wait for Langfuse to initialise — takes 60–105 seconds:

```bash
kubectl get pods -w | grep langfuse-server
```

Expected:
```
langfuse-server-xxx   1/1   Running   0   105s
```

### Step 7 — Deploy PMO Copilot

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Watch the rollout:

```bash
kubectl get pods -w
```

Expected — all three pods `1/1 Running`:
```
NAME                               READY   STATUS    RESTARTS
langfuse-postgres-xxx              1/1     Running   0
langfuse-server-xxx                1/1     Running   0
pmo-copilot-xxx                    1/1     Running   0
```

---

## Verify the Deployment

```bash
# All pods running
kubectl get pods

# All services with correct ports
kubectl get services

# PMO Copilot health
curl -s http://127.0.0.1:30501/_stcore/health

# Langfuse health
curl -s http://127.0.0.1:30300/api/public/health
```

Expected services:
```
NAME                TYPE        CLUSTER-IP     PORT(S)
langfuse-postgres   ClusterIP   10.43.x.x      5432/TCP
langfuse-server     NodePort    10.43.x.x      3000:30300/TCP
pmo-copilot         NodePort    10.43.x.x      8501:30501/TCP
```

Open from any device on the home network:
```
PMO Copilot UI  : http://<linux-laptop-ip>:30501
Langfuse Traces : http://<linux-laptop-ip>:30300
```

---

## Rolling Updates

When you change application code, rebuild and redeploy without downtime:

```bash
# Rebuild image
docker build -t pmo-copilot:v1 .

# Import into K3s containerd
docker save pmo-copilot:v1 -o /tmp/pmo-copilot-v1.tar
sudo k3s ctr images import /tmp/pmo-copilot-v1.tar

# Trigger rolling restart
kubectl rollout restart deployment pmo-copilot
```

K3s starts the new pod before terminating the old one — zero downtime.

Watch the rollout:
```bash
kubectl get pods -w
```

You will see:
```
pmo-copilot-new-xxx   0/1   Running      ← new pod starting
pmo-copilot-new-xxx   1/1   Running      ← new pod ready
pmo-copilot-old-xxx   1/1   Terminating  ← old pod stopping
pmo-copilot-old-xxx   0/1   Completed    ← old pod removed
```

---

## Auto-Start on Boot

K3s starts automatically on boot via systemd. All deployments in K3s restart automatically when the K3s service starts.

Verify K3s is enabled:
```bash
sudo systemctl is-enabled k3s
```

Expected: `enabled`

Docker containers with `restart: unless-stopped` also restart automatically when the Docker daemon starts. Since Langfuse is now in K3s, Docker only needs to be running for image builds — not for serving any application traffic.

---

## Useful Operational Commands

```bash
# Check all pod status
kubectl get pods

# View live logs for PMO app
kubectl logs deployment/pmo-copilot -f

# View live logs for Langfuse
kubectl logs deployment/langfuse-server -f

# Check resource usage
kubectl top pods

# Describe a pod for detailed events
kubectl describe pod <pod-name>

# Restart a specific deployment
kubectl rollout restart deployment pmo-copilot

# Scale up replicas (if RAM allows)
kubectl scale deployment pmo-copilot --replicas=2

# Tear down everything
kubectl delete namespace pmo-copilot
```

---

## Complete Status Check Script

```bash
#!/bin/bash
# scripts/demo-status.sh
echo "================================================"
echo "  PMO Copilot — System Status"
echo "================================================"
DELL_IP=$(hostname -I | awk '{print $1}')

POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^pmo-copilot" | awk '{print $2}')
[ "$POD" = "1/1" ] && echo "  ✅ PMO Copilot pod   : Running" || echo "  ❌ PMO Copilot pod   : NOT running"

LF_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-server" | awk '{print $2}')
[ "$LF_POD" = "1/1" ] && echo "  ✅ Langfuse pod      : Running" || echo "  ❌ Langfuse pod      : NOT running"

PG_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-postgres" | awk '{print $2}')
[ "$PG_POD" = "1/1" ] && echo "  ✅ Postgres pod      : Running" || echo "  ❌ Postgres pod      : NOT running"

STREAMLIT=$(curl -s http://127.0.0.1:30501/_stcore/health 2>/dev/null)
echo "$STREAMLIT" | grep -qi "ok" && echo "  ✅ Streamlit UI      : http://${DELL_IP}:30501" || echo "  ❌ Streamlit UI      : Not responding"

LANGFUSE=$(curl -s http://127.0.0.1:30300/api/public/health 2>/dev/null)
echo "$LANGFUSE" | grep -qi "ok" && echo "  ✅ Langfuse          : http://${DELL_IP}:30300" || echo "  ❌ Langfuse          : Not responding"

OLLAMA=$(curl -s http://192.168.1.16:11434/api/tags 2>/dev/null)
echo "$OLLAMA" | grep -qi "qwen2.5" && echo "  ✅ Ollama (Windows)  : http://192.168.1.16:11434" || echo "  ❌ Ollama (Windows)  : Not reachable"

echo "================================================"
```

---

## Common Failures and Fixes

**`ErrImageNeverPull`:**
K3s cannot find the image in containerd. Run the import step:
```bash
docker save pmo-copilot:v1 -o /tmp/pmo-copilot-v1.tar
sudo k3s ctr images import /tmp/pmo-copilot-v1.tar
kubectl rollout restart deployment pmo-copilot
```

**`FileNotFoundError` in pod logs:**
The hostPath volume path is wrong. Check the actual path:
```bash
ls /home/$USER/pmo-copilot/data/
```
Update `deployment.yaml` with the correct path and redeploy.

**Docker build fails on `apt-get update`:**
DNS not configured for Docker containers:
```bash
sudo bash -c 'cat > /etc/docker/daemon.json << EOF
{"dns": ["8.8.8.8", "8.8.4.4"]}
EOF'
sudo systemctl restart docker
```

**`packaging` version conflict during pip install:**
The `requirements.txt` has pinned transitive dependencies. Use the direct-deps-only version from this repository — do not replace it with `pip freeze` output.

**Pod stays in `Pending` state:**
Check for resource constraints:
```bash
kubectl describe pod <pod-name>
```
Look for `Insufficient memory` or `Insufficient cpu` in the Events section. Reduce resource requests if needed.

**Langfuse pod `CrashLoopBackOff`:**
Postgres is not ready when Langfuse starts. Check Postgres pod status:
```bash
kubectl get pods | grep postgres
kubectl logs deployment/langfuse-postgres
```
Wait for Postgres to be `1/1 Running` before Langfuse can initialise.

---

## Validation Checkpoint

The deployment is complete when all of these pass:

```bash
# All three pods running
kubectl get pods
# Expected: 3 pods, all 1/1 Running

# PMO Copilot accessible
curl -s http://127.0.0.1:30501/_stcore/health
# Expected: ok

# Langfuse accessible
curl -s http://127.0.0.1:30300/api/public/health
# Expected: {"status":"OK",...}

# Ollama reachable
curl http://<windows-laptop-ip>:11434/api/tags
# Expected: JSON with model list

# Run a quick agent analysis
source venv/bin/activate
python3 agents/pmo_risk_analyst.py "What is the status of PRJ001?"
# Expected: Final Answer with specific data

# Trace appears in Langfuse
# Open http://<linux-laptop-ip>:30300 → Traces
# Expected: pmo-agent-run trace from the agent run above
```

---

## Congratulations

You have built a complete, local-first agentic AI system:

| Component | Technology | Status |
|---|---|---|
| LLM inference | Ollama qwen2.5:7b | Windows laptop |
| Embeddings | nomic-embed-text | Ollama |
| Single ReACT agent | LangChain 0.3.25 | K3s pod |
| Multi-agent crew | CrewAI 0.86.0 | K3s pod |
| Vector memory | ChromaDB 1.5.9 | K3s pod (hostPath) |
| Observability | Langfuse 2.95.11 | K3s pod |
| Database | Postgres 15 | K3s pod (PVC) |
| UI | Streamlit 1.45.1 | K3s pod |
| Orchestration | K3s v1.35.5 | Linux laptop |

**Internet required: NO. Cloud APIs: ZERO.**

The system starts automatically on boot. Every component is observable. Memory persists across restarts. The UI is accessible from any device on your home network.