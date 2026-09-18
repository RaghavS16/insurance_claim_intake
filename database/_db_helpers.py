"""
Shared database connection helper for standalone database scripts.

Provides a backend-path bootstrap and a SessionLocal factory so that
``seed_admin.py`` and ``verify_db.py`` don't each duplicate the
``sys.path`` manipulation.
"""
import sys
from pathlib import Path

# Add the backend package to sys.path so its modules are importable.
_backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

# These imports must come after the sys.path manipulation above.
from src.database.session import SessionLocal  # noqa: E402  # pylint: disable=wrong-import-position

__all__ = ["SessionLocal"]
