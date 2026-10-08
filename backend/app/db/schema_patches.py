"""Lightweight column patches for evolving models (SQLite + Postgres)."""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def ensure_schema_patches() -> None:
    """Add new columns when create_all will not alter an existing DB."""
    url = str(engine.url)
    is_sqlite = url.startswith("sqlite")
    patches = [
        ("exam_sessions", "quiz_score", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
        ("exam_sessions", "quiz_max_score", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
        ("exam_sessions", "quiz_percent", "REAL DEFAULT 0", "DOUBLE PRECISION DEFAULT 0"),
        ("exam_sessions", "display_name", "TEXT DEFAULT ''", "VARCHAR(200) DEFAULT ''"),
    ]
    with engine.begin() as conn:
        for table, column, sqlite_type, pg_type in patches:
            coltype = sqlite_type if is_sqlite else pg_type
            if is_sqlite:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
            else:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"
                    )
                )
