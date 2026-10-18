"""Admin bootstrapping entrypoint delegating to backend/scripts/create_admin.py."""
import sys
from pathlib import Path

# Add backend directory
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.create_admin import create_admin

if __name__ == "__main__":
    create_admin()
