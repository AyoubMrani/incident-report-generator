"""
db — the Postgres data layer.

Replaces the single-file SQLite store. Postgres is not an upgrade for its own
sake: it is what lets identity (users), durability (concurrent writers) and
search (tsvector + pgvector) be one schema instead of three subsystems.

  models.py   SQLAlchemy 2.x typed models — the schema
  session.py  engine + session factory, built once per process
"""

from app.db.session import Database, get_database_url

__all__ = ["Database", "get_database_url"]
