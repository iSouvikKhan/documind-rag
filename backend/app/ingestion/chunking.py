from __future__ import annotations

from collections.abc import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.domain import ChunkDraft, PageText


def chunk_pages(pages: Iterable[PageText], chunk_size: int, chunk_overlap: int) -> list[ChunkDraft]:
    """Split each page separately so every chunk keeps an accurate page number."""
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[ChunkDraft] = []
    for page in pages:
        for piece in splitter.split_text(page.text):
            piece = piece.strip()
            if piece:
                chunks.append(ChunkDraft(content=piece, chunk_index=len(chunks), page=page.page))
    return chunks
