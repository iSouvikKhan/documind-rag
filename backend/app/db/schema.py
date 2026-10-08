"""Idempotent schema creation, run at startup."""

from __future__ import annotations

import logging

import psycopg

logger = logging.getLogger(__name__)


class SchemaError(RuntimeError):
    pass


def schema_sql(embedding_dim: int) -> list[str]:
    return [
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS documents (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            collection      text        NOT NULL DEFAULT 'default',
            filename        text        NOT NULL,
            content_type    text        NOT NULL,
            size_bytes      integer     NOT NULL CHECK (size_bytes >= 0),
            sha256          char(64)    NOT NULL,
            num_chunks      integer     NOT NULL DEFAULT 0,
            embedding_model text        NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (collection, sha256)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS chunks (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id uuid    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index integer NOT NULL,
            page        integer,
            content     text    NOT NULL,
            embedding   vector({int(embedding_dim)}) NOT NULL,
            tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        )
        """,
        "CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id)",
        "CREATE INDEX IF NOT EXISTS documents_collection_idx ON documents (collection)",
        "CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv)",
        "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
        "ON chunks USING hnsw (embedding vector_cosine_ops)",
    ]


def ensure_schema(database_url: str, embedding_dim: int, connect_timeout: int = 5) -> None:
    """Create the extension, tables and indexes if missing, and verify the vector size."""
    try:
        with psycopg.connect(
            database_url, autocommit=True, connect_timeout=connect_timeout
        ) as conn:
            for statement in schema_sql(embedding_dim):
                conn.execute(statement)
            row = conn.execute(
                """
                SELECT atttypmod FROM pg_attribute
                WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'
                """
            ).fetchone()
    except psycopg.errors.InsufficientPrivilege as exc:
        raise SchemaError(
            "Not allowed to create the 'vector' extension. Run `CREATE EXTENSION vector;` "
            "once as a superuser in the documind database."
        ) from exc
    except psycopg.errors.FeatureNotSupported as exc:
        raise SchemaError(f"pgvector is not installed in this PostgreSQL server: {exc}") from exc
    except psycopg.OperationalError as exc:
        raise SchemaError(f"Cannot connect to PostgreSQL: {exc}") from exc

    existing_dim = row[0] if row else None
    if existing_dim and existing_dim != embedding_dim:
        raise SchemaError(
            f"The chunks table stores {existing_dim}-dimensional vectors but EMBEDDING_DIM="
            f"{embedding_dim}. Use the original embedding settings or drop the tables "
            "(DROP TABLE chunks, documents;) to re-ingest with the new model."
        )
    logger.info("Database schema ready (embedding dim %s)", embedding_dim)
