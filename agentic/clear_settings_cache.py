#!/usr/bin/env python3
import sys
# Clear settings cache by importing and clearing the lru_cache
app_path = "/home/cloud/chat-ai/agentic"
sys.path.insert(0, app_path)

from app.config import get_settings
from goose_runtime.config import reset_settings_cache

print("Clearing agentic settings cache...")
get_settings.cache_clear()

print("Clearing goose_runtime settings cache...")
reset_settings_cache()

print("Settings caches cleared.")