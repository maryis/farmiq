from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import KnowledgeChunk
from app.services.embedding import embed_text


async def main() -> None:
    async with SessionLocal() as session:
        chunks = (
            await session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.embedding.is_(None)))
        ).all()
        updated = 0
        for chunk in chunks:
            vector = await embed_text(f"{chunk.title}\n{chunk.content}")
            if vector:
                chunk.embedding = vector
                updated += 1
        await session.commit()
        print(f"embedded {updated} knowledge chunks")


if __name__ == "__main__":
    asyncio.run(main())
