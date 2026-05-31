#!/bin/bash
NEW_IP=$1
if [ -z "$NEW_IP" ]; then
  echo "Usage: ./update-ollama-ip.sh <new-ip>"
  exit 1
fi
sed -i "s|OLLAMA_BASE_URL=http://[0-9.]*:11434|OLLAMA_BASE_URL=http://${NEW_IP}:11434|g" ~/pmo-copilot/.env
sed -i "s|OLLAMA_API_BASE=http://[0-9.]*:11434|OLLAMA_API_BASE=http://${NEW_IP}:11434|g" ~/pmo-copilot/.env
kubectl patch configmap pmo-config \
  --type merge \
  -p "{\"data\":{\"OLLAMA_BASE_URL\":\"http://${NEW_IP}:11434\",\"OLLAMA_API_BASE\":\"http://${NEW_IP}:11434\"}}"
kubectl rollout restart deployment pmo-copilot
echo "Done — Ollama now points to ${NEW_IP}"
