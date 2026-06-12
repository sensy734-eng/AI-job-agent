from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.models import Base


def _resolve_database_url(url: str) -> str:
    if url == "sqlite:///./job_agent.db":
        backend_dir = Path(__file__).resolve().parents[2]
        return f"sqlite:///{(backend_dir / 'job_agent.db').as_posix()}"
    return url


settings = get_settings()
database_url = _resolve_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    try:
        _ensure_pgvector_extension()
        Base.metadata.create_all(bind=engine)
        _ensure_sqlite_columns()
        _ensure_pgvector_schema()
    except OperationalError as exc:
        if "already exists" not in str(exc).lower():
            raise


def is_pgvector_enabled() -> bool:
    return settings.vector_backend.lower() == "pgvector" and not database_url.startswith("sqlite")


def active_vector_backend() -> str:
    return "pgvector" if is_pgvector_enabled() else "sqlite"


def _ensure_pgvector_extension() -> None:
    if not is_pgvector_enabled():
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def _ensure_sqlite_columns() -> None:
    if not database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(resume_versions)")).fetchall()
        columns = {row[1] for row in rows}
        if rows and "title" not in columns:
            connection.execute(text("ALTER TABLE resume_versions ADD COLUMN title VARCHAR(120) DEFAULT '优化版本'"))


def _ensure_pgvector_schema() -> None:
    if not is_pgvector_enabled():
        return
    dimension = settings.embedding_dimension
    with engine.begin() as connection:
        connection.execute(
            text(
                f"ALTER TABLE rag_chunks "
                f"ALTER COLUMN embedding TYPE vector({dimension}) "
                f"USING embedding::vector({dimension})"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw "
                "ON rag_chunks USING hnsw (embedding vector_cosine_ops)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_owner_source "
                "ON rag_chunks (owner_id, source)"
            )
        )
