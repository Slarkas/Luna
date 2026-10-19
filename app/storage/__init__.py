"""Shared database singleton for Luna application."""

from .database import Database

_db_instance: Database | None = None

def get_database() -> Database:
    """Return or create the shared database instance with default production path."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

__all__ = ["Database", "get_database"]