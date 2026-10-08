"""SQL access for documents and chunks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import numpy as np
from psycopg_pool import ConnectionPool

from app.domain import ChunkDraft, Document, RetrievedChunk

_DOC_COLUMNS = "id, filename, content_type, size_bytes, num_chunks, collection, created_at"


class DocumentRepository(Protocol):
    """The operations the services need. Tests provide in-memory fakes."""

    def find_by_hash(self, collection: str, sha256: str) -> Document | None: ...

    def add_document(
        self,
        *,
        collection: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        embedding_model: str,
        chunks: Sequence[ChunkDraft],
        embeddings: Sequence[Sequence[float]],
    ) -> Document: ...

    def list_documents(self, collection: str) -> list[Document]: ...

    def get_document(self, document_id: UUID) -> Document | None: ...

    def delete_document(self, document_id: UUID) -> bool: ...

    def delete_collection(self, collection: str) -> int: ...

    def vector_search(
        self, collection: str, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]: ...

    def keyword_search(self, collection: str, query: str, limit: int) -> list[RetrievedChunk]: ...


def _document(row: dict) -> Document:
    return Document(**row)


def _chunk(row: dict) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        filename=row["filename"],
        content=row["content"],
        chunk_index=row["chunk_index"],
        page=row["page"],
    )


class PostgresRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def ping(self) -> bool:
        with self.pool.connection() as conn:
            conn.execute("SELECT 1")
        return True

    def find_by_hash(self, collection: str, sha256: str) -> Document | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_DOC_COLUMNS} FROM documents WHERE collection = %s AND sha256 = %s",
                (collection, sha256),
            ).fetchone()
        return _document(row) if row else None

    def add_document(
        self,
        *,
        collection: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        embedding_model: str,
        chunks: Sequence[ChunkDraft],
        embeddings: Sequence[Sequence[float]],
    ) -> Document:
        if len(chunks) != len(embeddings):
            raise ValueError("Every chunk needs exactly one embedding")
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                f"""
                INSERT INTO documents
                    (collection, filename, content_type, size_bytes, sha256, num_chunks,
                     embedding_model)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING {_DOC_COLUMNS}
                """,
                (
                    collection,
                    filename,
                    content_type,
                    size_bytes,
                    sha256,
                    len(chunks),
                    embedding_model,
                ),
            ).fetchone()
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO chunks (document_id, chunk_index, page, content, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            row["id"],
                            c.chunk_index,
                            c.page,
                            c.content,
                            np.asarray(e, dtype=np.float32),
                        )
                        for c, e in zip(chunks, embeddings, strict=True)
                    ],
                )
        return _document(row)

    def list_documents(self, collection: str) -> list[Document]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_DOC_COLUMNS} FROM documents WHERE collection = %s "
                "ORDER BY created_at DESC",
                (collection,),
            ).fetchall()
        return [_document(r) for r in rows]

    def get_document(self, document_id: UUID) -> Document | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_DOC_COLUMNS} FROM documents WHERE id = %s", (document_id,)
            ).fetchone()
        return _document(row) if row else None

    def delete_document(self, document_id: UUID) -> bool:
        with self.pool.connection() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            return cur.rowcount > 0

    def delete_collection(self, collection: str) -> int:
        with self.pool.connection() as conn:
            cur = conn.execute("DELETE FROM documents WHERE collection = %s", (collection,))
            return cur.rowcount

    def vector_search(
        self, collection: str, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]:
        query_vec = np.asarray(embedding, dtype=np.float32)
        with self.pool.connection() as conn, conn.transaction():
            # The HNSW index is filtered after the scan, so widen the candidate list a bit.
            conn.execute(f"SET LOCAL hnsw.ef_search = {min(1000, max(40, limit * 4))}")
            rows = conn.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, d.filename, c.content, c.chunk_index,
                       c.page, 1 - (c.embedding <=> %s) AS score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE d.collection = %s
                ORDER BY c.embedding <=> %s
                LIMIT %s
                """,
                (query_vec, collection, query_vec, limit),
            ).fetchall()
        results = []
        for r in rows:
            chunk = _chunk(r)
            chunk.vector_score = float(r["score"])
            results.append(chunk)
        return results

    def keyword_search(self, collection: str, query: str, limit: int) -> list[RetrievedChunk]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, d.filename, c.content, c.chunk_index,
                       c.page, ts_rank_cd(c.tsv, q) AS score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id,
                     -- OR the query terms: questions rarely contain every word of the answer
                     to_tsquery('english',
                                replace(plainto_tsquery('english', %s)::text, ' & ', ' | ')) q
                WHERE d.collection = %s AND c.tsv @@ q
                ORDER BY score DESC
                LIMIT %s
                """,
                (query, collection, limit),
            ).fetchall()
        results = []
        for r in rows:
            chunk = _chunk(r)
            chunk.keyword_score = float(r["score"])
            results.append(chunk)
        return results
