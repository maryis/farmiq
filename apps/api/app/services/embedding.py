from __future__ import annotations

import httpx

from app.config import settings


async def embed_text(text: str) -> list[float] | None:
    if not settings.embedding_base_url:
        return None
    headers = (
        {"Authorization": f"Bearer {settings.embedding_api_key}"}
        if settings.embedding_api_key
        else {}
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.embedding_base_url.rstrip('/')}/embeddings",
            headers=headers,
            json={"model": settings.embedding_model, "input": text},
        )
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
        return [float(value) for value in vector]
