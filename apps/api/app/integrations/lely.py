from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.integrations.base import NormalizedObservation


class LelyAdapter:
    """Cloud adapter boundary for the Lely third-party API.

    Exact payload field names and partner URLs must be validated against the contract issued with
    legitimate integration credentials. Endpoint paths are configurable instead of guessed in code.
    """

    provider = "lely"

    def __init__(self) -> None:
        self.base_url = settings.lely_api_base_url
        self.token_url = settings.lely_token_url
        self.client_id = settings.lely_client_id
        self.client_secret = settings.lely_client_secret
        self.scope = settings.lely_scope
        self.paths = {
            "rumination": settings.lely_ruminations_path,
            "activity": settings.lely_activities_path,
            "milk_yield": settings.lely_milk_visits_path,
            "feed_intake": settings.lely_feed_visits_path,
        }

    @property
    def configured(self) -> bool:
        return all([self.base_url, self.token_url, self.client_id, self.client_secret])

    async def _token(self, client: httpx.AsyncClient) -> str:
        if not self.configured:
            raise RuntimeError("Lely credentials are not configured")
        data = {"grant_type": "client_credentials"}
        if self.scope:
            data["scope"] = self.scope
        response = await client.post(
            self.token_url,
            data=data,
            auth=(self.client_id, self.client_secret),
        )
        response.raise_for_status()
        return response.json()["access_token"]

    async def pull(self, stream: str, watermark: str | None) -> tuple[list[NormalizedObservation], str | None]:
        if stream not in self.paths:
            raise ValueError(f"Unsupported Lely stream: {stream}")
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._token(client)
            params = {"from": watermark} if watermark else {}
            response = await client.get(
                f"{self.base_url.rstrip('/')}/{self.paths[stream].lstrip('/')}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        # Partner payload mapping is intentionally conservative. A deployment can adapt these aliases
        # without touching domain services; unknown rows fail loudly instead of silently corrupting data.
        rows = payload.get("items", payload if isinstance(payload, list) else [])
        normalized = []
        newest = watermark
        for row in rows:
            animal_id = row.get("lifeNumber") or row.get("animalId") or row.get("animal_id")
            timestamp = row.get("timestamp") or row.get("dateTime") or row.get("observedAt")
            value = row.get("value")
            if value is None:
                value = row.get("amount") or row.get("minutes") or row.get("yield")
            if not animal_id or timestamp is None or value is None:
                raise RuntimeError(f"Unmapped Lely {stream} payload; update adapter aliases for the issued API contract")
            observed_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
            unit = row.get("unit") or {"rumination": "min/day", "activity": "index", "milk_yield": "kg/day", "feed_intake": "kg/day"}[stream]
            normalized.append(NormalizedObservation(
                external_animal_id=str(animal_id),
                kind=stream,
                value=float(value),
                unit=unit,
                observed_at=observed_at,
                source_event_id=str(row.get("id")) if row.get("id") is not None else None,
                metadata={"raw_type": row.get("type")},
            ))
            iso = observed_at.isoformat()
            newest = max(newest or iso, iso)
        return normalized, newest
