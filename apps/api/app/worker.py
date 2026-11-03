from __future__ import annotations

import asyncio

from celery import Celery
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.demo import DEMO_SLUG, simulate_demo_tick
from app.models import Farm, Integration
from app.services.health import evaluate_farm
from app.services.integration import sync_lely

celery_app = Celery("farmiq", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "Europe/Amsterdam"
celery_app.conf.beat_schedule = {
    "demo-nrt-every-5-min": {"task": "app.worker.demo_tick", "schedule": 300.0},
    "health-every-5-min": {"task": "app.worker.health_tick", "schedule": 300.0},
    "integrations-every-2-min": {"task": "app.worker.integration_tick", "schedule": 120.0},
}


@celery_app.task(name="app.worker.demo_tick")
def demo_tick():
    async def run():
        async with SessionLocal() as session:
            farm = await session.scalar(select(Farm).where(Farm.slug == DEMO_SLUG))
            if farm:
                return await simulate_demo_tick(session, farm)
        return 0
    return asyncio.run(run())


@celery_app.task(name="app.worker.health_tick")
def health_tick():
    async def run():
        async with SessionLocal() as session:
            farms = (await session.scalars(select(Farm))).all()
            total = 0
            for farm in farms:
                total += await evaluate_farm(session, farm.id)
            return total
    return asyncio.run(run())


@celery_app.task(name="app.worker.integration_tick")
def integration_tick():
    async def run():
        async with SessionLocal() as session:
            integrations = (await session.scalars(select(Integration).where(Integration.provider == "lely", Integration.status.in_(["connected", "pending", "needs_credentials"])))).all()
            results = []
            for integration in integrations:
                try:
                    results.append(await sync_lely(session, integration.id))
                except Exception as exc:
                    integration.status = "error"
                    integration.last_error = str(exc)[:1000]
                    await session.commit()
            return results
    return asyncio.run(run())
