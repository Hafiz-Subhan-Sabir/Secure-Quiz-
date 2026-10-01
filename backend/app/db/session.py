from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Normalize Railway-style postgres:// URLs for SQLAlchemy + psycopg3
_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+psycopg://" + _db_url[len("postgres://") :]
elif _db_url.startswith("postgresql://") and "+psycopg" not in _db_url:
    _db_url = "postgresql+psycopg://" + _db_url[len("postgresql://") :]

is_sqlite = _db_url.startswith("sqlite")

connect_args: dict = {}
engine_kwargs: dict = {
    "future": True,
    "pool_pre_ping": True,
}

if is_sqlite:
    connect_args = {"check_same_thread": False, "timeout": 30}
else:
    engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)

engine = create_engine(_db_url, connect_args=connect_args, **engine_kwargs)


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    if not is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
    expire_on_commit=False,
)
