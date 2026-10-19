"""Auto-seed demo data and launch FastAPI server on port 8000 for Playwright E2E tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
backend_dir = Path(__file__).resolve().parent
for p in (str(repo_root), str(backend_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

env = (os.environ.get("ENVIRONMENT") or "development").lower().strip()
if not os.environ.get("DEMO_PASSWORD"):
    if env not in ("prod", "production"):
        os.environ["DEMO_PASSWORD"] = "DemoPass123!"
    else:
        raise RuntimeError("DEMO_PASSWORD environment variable is required to run e2e server.")
os.environ.setdefault("ENVIRONMENT", "development")

try:
    from database.seed_demo import seed_demo
    seed_demo()
except Exception as exc:
    print(f"[WARN] seed_demo warning during E2E startup: {exc}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, log_level="warning")
