#!/usr/bin/env bash
sudo lsof -i :8081
cd ./agentic
source .venv/bin/activate
AGENTIC_EXECUTION_MODE=local python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

