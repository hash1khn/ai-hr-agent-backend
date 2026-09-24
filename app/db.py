from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "init.sql"

_pool: ConnectionPool | None = None


def _db_hint() -> str:
    if get_settings().is_remote_db:
        return "Check DATABASE_URL (and sslmode=require). Enable the vector extension."
    return "Start Postgres with pgvector: docker compose up db"


def connect() -> None:
    global _pool
    settings = get_settings()
    _pool = ConnectionPool(
        conninfo=settings.dsn,
        min_size=0,
        max_size=8,
        timeout=settings.pool_timeout,
        kwargs={"row_factory": dict_row, "connect_timeout": settings.connect_timeout},
        open=True,
    )
    try:
        with psycopg.connect(
            settings.dsn,
            connect_timeout=settings.connect_timeout,
        ) as conn:
            conn.execute("SELECT 1")
            _apply_schema(conn)
            conn.commit()
        logger.info("Connected to Postgres (pgvector)")
    except Exception as exc:
        logger.error("Postgres unavailable (%s). %s", exc, _db_hint())


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def require_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


def _apply_schema(conn: psycopg.Connection) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    exists = conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'companies'
        """
    ).fetchone()
    if not exists:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        for statement in _sql_statements(sql):
            conn.execute(statement)
    _apply_migrations(conn)


def _apply_migrations(conn: psycopg.Connection) -> None:
    """Idempotent upgrades for databases that already have the base schema."""
    conn.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'ALL_EMPLOYEES'
        """
    )
    conn.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'documents_visibility_check'
          ) THEN
            ALTER TABLE documents
            ADD CONSTRAINT documents_visibility_check
            CHECK (visibility IN ('ALL_EMPLOYEES', 'ADMIN_ONLY'));
          END IF;
        END
        $$
        """
    )
    _apply_rls(conn)


_RLS_TABLES = ("documents", "document_chunks", "conversations", "messages")

_RLS_POLICIES = {
    "documents": """
        CREATE POLICY documents_tenant_isolation ON documents
          USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
          WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
    """,
    "document_chunks": """
        CREATE POLICY document_chunks_tenant_isolation ON document_chunks
          USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
          WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
    """,
    "conversations": """
        CREATE POLICY conversations_tenant_isolation ON conversations
          USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
          WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
    """,
    "messages": """
        CREATE POLICY messages_tenant_isolation ON messages
          USING (
            EXISTS (
              SELECT 1 FROM conversations conv
              WHERE conv.id = conversation_id
                AND conv.company_id = NULLIF(current_setting('app.company_id', true), '')::uuid
            )
          )
          WITH CHECK (
            EXISTS (
              SELECT 1 FROM conversations conv
              WHERE conv.id = conversation_id
                AND conv.company_id = NULLIF(current_setting('app.company_id', true), '')::uuid
            )
          )
    """,
}


def _apply_rls(conn: psycopg.Connection) -> None:
    for table in _RLS_TABLES:
        conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        conn.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        conn.execute(_RLS_POLICIES[table])


def _sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
    leftover = "\n".join(buf).strip()
    if leftover:
        statements.append(leftover)
    return statements


class _ScopedConnection:
    """Re-applies a transaction-local GUC after commit/rollback so pooled connections stay safe."""

    def __init__(self, conn, apply) -> None:
        self._conn = conn
        self._apply = apply
        self._apply(conn)

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        self._conn.commit()
        self._apply(self._conn)

    def rollback(self):
        self._conn.rollback()
        self._apply(self._conn)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _set_company_id(conn, company_id: str) -> None:
    conn.execute("SELECT set_config('app.company_id', %s, true)", (str(company_id),))


def _disable_row_security(conn) -> None:
    conn.execute("SET LOCAL row_security = off")


@contextmanager
def connection() -> Iterator:
    try:
        with require_pool().connection() as conn:
            yield conn
    except Exception as exc:
        message = str(exc)
        if isinstance(exc, PoolTimeout) or any(
            token in message.lower()
            for token in ("connection refused", "enotfound", "connection", "timeout", "ssl")
        ):
            raise RuntimeError(f"Postgres unavailable. {_db_hint()} — {message}") from exc
        raise


@contextmanager
def tenant_connection(company_id: str) -> Iterator:
    """Request-scoped connection with transaction-local tenant GUC for RLS."""
    with connection() as conn:
        yield _ScopedConnection(conn, lambda c: _set_company_id(c, company_id))


@contextmanager
def bypass_rls_connection() -> Iterator:
    """Internal jobs (ingestion failure paths) that must load a row before tenant scope is known."""
    with connection() as conn:
        yield _ScopedConnection(conn, _disable_row_security)
