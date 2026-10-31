"""Environment and configuration settings for Metrologic."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = os.getenv("WORKSPACE", "plant-1")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?directConnection=true")
MONGODB_DB = os.getenv("MONGODB_DB", "metrologic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
EMBED_MODEL = os.getenv("EMBED_MODEL", "voyage-3-large")
CACHE_DIR = os.getenv("CACHE_DIR", str(BASE_DIR / ".cache"))
OFFLINE = int(os.getenv("OFFLINE", "0"))

