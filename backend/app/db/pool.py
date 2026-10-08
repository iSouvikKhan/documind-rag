from __future__ import annotations

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)
    conn.row_factory = dict_row


def create_pool(
    database_url: str, min_size: int, max_size: int, connect_timeout: int = 5
) -> ConnectionPool:
    """A synchronous pool. Sync psycopg also works on Windows' default event loop."""
    pool = ConnectionPool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        configure=_configure,
        open=False,
        kwargs={"connect_timeout": connect_timeout},
    )
    pool.open(wait=True, timeout=10)
    return pool
