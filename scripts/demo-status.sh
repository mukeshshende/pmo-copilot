#!/bin/bash
echo "================================================"
echo "  PMO Copilot — System Status"
echo "================================================"
DELL_IP=$(hostname -I | awk '{print $1}')

# K3s pod — PMO Copilot
POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^pmo-copilot" | awk '{print $2}')
if [ "$POD" = "1/1" ]; then
  echo "  ✅ PMO Copilot pod   : Running"
else
  echo "  ❌ PMO Copilot pod   : NOT running"
fi

# K3s pod — Langfuse server
LF_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-server" | awk '{print $2}')
if [ "$LF_POD" = "1/1" ]; then
  echo "  ✅ Langfuse pod      : Running"
else
  echo "  ❌ Langfuse pod      : NOT running"
fi

# K3s pod — Postgres
PG_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-postgres" | awk '{print $2}')
if [ "$PG_POD" = "1/1" ]; then
  echo "  ✅ Postgres pod      : Running"
else
  echo "  ❌ Postgres pod      : NOT running"
fi

# Streamlit UI health
STREAMLIT=$(curl -s http://127.0.0.1:30501/_stcore/health 2>/dev/null)
if echo "$STREAMLIT" | grep -qi "ok"; then
  echo "  ✅ Streamlit UI      : http://${DELL_IP}:30501"
else
  echo "  ❌ Streamlit UI      : Not responding"
fi

# Langfuse health
LANGFUSE=$(curl -s http://127.0.0.1:30300/api/public/health 2>/dev/null)
if echo "$LANGFUSE" | grep -qi "ok"; then
  echo "  ✅ Langfuse          : http://${DELL_IP}:30300"
else
  echo "  ❌ Langfuse          : Not responding"
fi

# Ollama
OLLAMA=$(curl -s http://192.168.1.16:11434/api/tags 2>/dev/null)
if echo "$OLLAMA" | grep -qi "qwen2.5"; then
  echo "  ✅ Ollama (Windows)  : http://192.168.1.16:11434"
else
  echo "  ❌ Ollama (Windows)  : Not reachable"
fi

echo "================================================"
