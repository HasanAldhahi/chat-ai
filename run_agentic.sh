#!/usr/bin/env bash

sudo lsof -ti :8081 | xargs -r sudo kill -9
sudo lsof -ti :8080 | xargs -r sudo kill -9
sudo lsof -ti :8001 | xargs -r sudo kill -9
sudo lsof -i :8081
cd ./agentic
source .venv/bin/activate
WATCHFILES_FORCE_POLLING=true AGENTIC_EXECUTION_MODE=local python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload --timeout-graceful-shutdown 2
