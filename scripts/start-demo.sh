#!/bin/bash
echo "================================================"
echo "  PMO Copilot — Demo Startup"
echo "================================================"
DELL_IP=$(hostname -I | awk '{print $1}')

# Step 1 — Check K3s is running
echo ""
echo "1. Checking K3s..."
K3S_STATUS=$(kubectl get nodes 2>/dev/null | grep "Ready" | awk '{print $2}')
if [ "$K3S_STATUS" = "Ready" ]; then
  echo "   ✅ K3s node is Ready"
else
  echo "   ❌ K3s not ready — starting..."
  sudo systemctl start k3s
  sleep 10
fi

# Step 2 — Check all pods
echo ""
echo "2. Checking pods..."
PMO_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^pmo-copilot" | awk '{print $2}')
LF_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-server" | awk '{print $2}')
PG_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-postgres" | awk '{print $2}')

if [ "$PMO_POD" = "1/1" ] && [ "$LF_POD" = "1/1" ] && [ "$PG_POD" = "1/1" ]; then
  echo "   ✅ All pods running"
else
  echo "   ⏳ Some pods not ready — waiting 60 seconds..."
  sleep 60
  PMO_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^pmo-copilot" | awk '{print $2}')
  LF_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-server" | awk '{print $2}')
  PG_POD=$(kubectl get pods -n pmo-copilot 2>/dev/null | grep "^langfuse-postgres" | awk '{print $2}')
  if [ "$PMO_POD" = "1/1" ] && [ "$LF_POD" = "1/1" ] && [ "$PG_POD" = "1/1" ]; then
    echo "   ✅ All pods now running"
  else
    echo "   ❌ Pods still not ready — check: kubectl get pods -n pmo-copilot"
  fi
fi

# Step 3 — Check Langfuse health
echo ""
echo "3. Checking Langfuse..."
LANGFUSE_STATUS=$(curl -s http://127.0.0.1:30300/api/public/health 2>/dev/null)
if echo "$LANGFUSE_STATUS" | grep -qi "ok"; then
  echo "   ✅ Langfuse is healthy"
else
  echo "   ⏳ Langfuse still starting — waiting 30 seconds..."
  sleep 30
  LANGFUSE_STATUS=$(curl -s http://127.0.0.1:30300/api/public/health 2>/dev/null)
  if echo "$LANGFUSE_STATUS" | grep -qi "ok"; then
    echo "   ✅ Langfuse is healthy"
  else
    echo "   ❌ Langfuse not responding — check: kubectl logs deployment/langfuse-server -n pmo-copilot"
  fi
fi

# Step 4 — Check Ollama
echo ""
echo "4. Checking Ollama on Windows laptop..."
OLLAMA_STATUS=$(curl -s http://192.168.1.16:11434/api/tags 2>/dev/null)
if echo "$OLLAMA_STATUS" | grep -qi "qwen2.5"; then
  echo "   ✅ Ollama is reachable — qwen2.5:7b available"
else
  echo "   ❌ Cannot reach Ollama at 192.168.1.16:11434"
  echo "   → Make sure Ollama is running on the Windows laptop"
fi

# Step 5 — Final summary
echo ""
echo "================================================"
echo "  Demo Ready — Access Points"
echo "================================================"
echo ""
echo "  PMO Copilot UI  : http://${DELL_IP}:30501"
echo "  Langfuse Traces : http://${DELL_IP}:30300"
echo "  Ollama API      : http://192.168.1.16:11434"
echo ""
echo "  All services running on K3s — no Docker Compose needed"
echo "================================================"
