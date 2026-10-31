"""Environment and configuration settings for Metrologic."""

import os
from pathlib import Path

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

for env_path in [BASE_DIR / ".env", ROOT_DIR / ".env"]:
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

WORKSPACE = os.getenv("WORKSPACE", "plant-1")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?directConnection=true")
MONGODB_DB = os.getenv("MONGODB_DB", "metrologic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "voyage-3-large")
CACHE_DIR = os.getenv("CACHE_DIR", str(BASE_DIR / ".cache"))
# Remote LLM provider.  OFFLINE=1 uses disk caches only.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
# Model name for the selected provider (e.g. "llama3.2:1b" for ollama,
# "gemini-2.5-flash-lite" for the Google API).
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
# Google Gemini API key (required when LLM_PROVIDER=gemini).
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
OFFLINE = int(os.getenv("OFFLINE", "0"))
