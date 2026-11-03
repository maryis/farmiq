from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import KnowledgeChunk
from app.services.embedding import embed_text


async def _vector_retrieve(
    session: AsyncSession, query: str, limit: int
) -> list[KnowledgeChunk]:
    if not settings.embedding_base_url:
        return []
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return []
    vector = await embed_text(query)
    if not vector:
        return []
    # pgvector's cosine-distance operator. The generic JSON fallback is only used on non-Postgres DBs.
    rows = (
        await session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.embedding.is_not(None))
            .order_by(KnowledgeChunk.embedding.op("<=>")(vector))
            .limit(limit)
        )
    ).all()
    return list(rows)


async def retrieve(session: AsyncSession, query: str, limit: int = 3) -> list[KnowledgeChunk]:
    try:
        vector_rows = await _vector_retrieve(session, query, limit)
        if vector_rows:
            return vector_rows
    except Exception:
        # RAG remains useful if the embedding service is down; do not take Ask-IQ down with it.
        pass

    rows = (await session.scalars(select(KnowledgeChunk))).all()
    terms = {term.lower().strip(".,?!:;()") for term in query.split() if len(term) > 3}
    scored = []
    for row in rows:
        haystack = f"{row.title} {row.content} {' '.join(row.tags or [])}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored[:limit]]
