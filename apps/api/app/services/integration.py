from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.lely import LelyAdapter
from app.models import Animal, Integration, SensorObservation, SyncCursor


async def sync_lely(session: AsyncSession, integration_id: uuid.UUID) -> dict:
    integration = await session.get(Integration, integration_id)
    if not integration or integration.provider != "lely":
        raise RuntimeError("Unknown Lely integration")
    adapter = LelyAdapter()
    if not adapter.configured:
        integration.status = "needs_credentials"
        integration.last_error = "Lely partner credentials are not configured in the secret environment"
        await session.commit()
        return {"inserted": 0, "status": integration.status}

    total = 0
    for stream in ("rumination", "activity", "milk_yield", "feed_intake"):
        cursor = await session.scalar(select(SyncCursor).where(SyncCursor.integration_id == integration.id, SyncCursor.stream == stream))
        if cursor is None:
            cursor = SyncCursor(integration_id=integration.id, stream=stream)
            session.add(cursor)
            await session.flush()
        rows, watermark = await adapter.pull(stream, cursor.watermark)
        for item in rows:
            animal = await session.scalar(select(Animal).where(Animal.farm_id == integration.farm_id, Animal.external_id == item.external_animal_id))
            if not animal:
                continue
            duplicate = await session.scalar(select(SensorObservation.id).where(
                SensorObservation.animal_id == animal.id,
                SensorObservation.kind == item.kind,
                SensorObservation.observed_at == item.observed_at,
                SensorObservation.source == "lely",
            ))
            if duplicate:
                continue
            session.add(SensorObservation(
                farm_id=integration.farm_id,
                animal_id=animal.id,
                kind=item.kind,
                value=item.value,
                unit=item.unit,
                observed_at=item.observed_at,
                source="lely",
                source_event_id=item.source_event_id,
                metadata_json=item.metadata,
            ))
            await session.flush()
            total += 1
        cursor.watermark = watermark or cursor.watermark
    integration.status = "connected"
    integration.last_sync_at = datetime.now(timezone.utc)
    integration.last_error = None
    await session.commit()
    return {"inserted": total, "status": integration.status}
