"""
Root entrypoint for production initial database seeding.

Delegates directly to database/seed_initialization.py.
"""
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

_backend_path = _repo_root / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from database.seed_initialization import main

if __name__ == "__main__":
    main()
