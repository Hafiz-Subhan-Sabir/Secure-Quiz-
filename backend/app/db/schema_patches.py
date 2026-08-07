"""Lightweight SQLite column patches for evolving models."""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def ensure_schema_patches() -> None:
    """Add new columns when create_all will not alter an existing SQLite DB."""
    url = str(engine.url)
    if not url.startswith("sqlite"):
        return
    patches = [
        ("exam_sessions", "quiz_score", "INTEGER DEFAULT 0"),
        ("exam_sessions", "quiz_max_score", "INTEGER DEFAULT 0"),
        ("exam_sessions", "quiz_percent", "REAL DEFAULT 0"),
    ]
    with engine.begin() as conn:
        for table, column, coltype in patches:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {r[1] for r in rows}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
