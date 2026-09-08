from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from .config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns() -> None:
    """Add columns to existing tables that were introduced after the DB was first created.

    Lightweight dev-time migration for SQLite. Production Postgres deployments should
    use Alembic instead.
    """
    insp = inspect(engine)
    if not insp.has_table("chat_messages"):
        return
    wanted = {
        "chat_messages": [
            ("model_used", "VARCHAR(128)"),
            ("input_tokens", "INTEGER"),
            ("output_tokens", "INTEGER"),
        ],
        "agent_runs": [
            ("input_tokens", "INTEGER"),
            ("output_tokens", "INTEGER"),
        ],
        "app_settings": [
            ("encrypted_gemini_api_key", "TEXT"),
        ],
    }
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
