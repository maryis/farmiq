from __future__ import annotations

import math
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Animal,
    AnimalGroup,
    Farm,
    FeedIngredient,
    FeedInventory,
    Integration,
    KnowledgeChunk,
    Organization,
    RationItem,
    RationPlan,
    SensorObservation,
)
from app.services.health import evaluate_farm

DEMO_SLUG = "green-meadow-demo"


async def seed_demo(session: AsyncSession) -> Farm:
    existing = await session.scalar(select(Farm).where(Farm.slug == DEMO_SLUG))
    if existing:
        return existing

    rng = random.Random(42)
    org = Organization(name="FarmIQ Demo")
    session.add(org)
    await session.flush()
    farm = Farm(
        organization_id=org.id,
        name="Green Meadow Dairy",
        slug=DEMO_SLUG,
        is_demo=True,
        country_code="NL",
        timezone="Europe/Amsterdam",
    )
    session.add(farm)
    await session.flush()

    groups = [
        AnimalGroup(farm_id=farm.id, name="Fresh cows", stage="fresh", target_dmi_kg=20.5, target_vem=21000, target_dve_g=1850, min_ndf_g=6500, oeb_min_g=-150),
        AnimalGroup(farm_id=farm.id, name="High production", stage="high", target_dmi_kg=22.5, target_vem=22900, target_dve_g=1980, min_ndf_g=7000, oeb_min_g=-150),
        AnimalGroup(farm_id=farm.id, name="Mid lactation", stage="mid", target_dmi_kg=20.5, target_vem=20300, target_dve_g=1700, min_ndf_g=6900, oeb_min_g=-200),
        AnimalGroup(farm_id=farm.id, name="Late lactation", stage="late", target_dmi_kg=18.5, target_vem=17900, target_dve_g=1450, min_ndf_g=6500, oeb_min_g=-250),
    ]
    session.add_all(groups)
    await session.flush()

    special_tags = ["NL-0184", "NL-0441", "NL-0081", "NL-0382"]
    other_tags = [f"NL-{n:04d}" for n in range(1, 118) if f"NL-{n:04d}" not in special_tags]
    tags = special_tags + other_tags
    animals = []
    for idx, tag in enumerate(tags[:120]):
        group = groups[idx % 4]
        dim_ranges = {"fresh": (5, 35), "high": (36, 100), "mid": (101, 210), "late": (211, 320)}
        lo, hi = dim_ranges[group.stage]
        dim = rng.randint(lo, hi)
        if tag == "NL-0441":
            group = groups[0]
            dim = 12
        if tag == "NL-0184":
            group = groups[1]
            dim = 63
        animal = Animal(
            farm_id=farm.id,
            group_id=group.id,
            external_id=tag,
            name=f"Cow {tag[-4:]}",
            parity=rng.randint(1, 5),
            days_in_milk=dim,
            body_condition_score=round(rng.uniform(2.6, 3.55), 2),
        )
        session.add(animal)
        animals.append(animal)
    await session.flush()

    feed_specs = [
        ("Grass silage", 0.43, 930, 82, 20, 470, 0.12, 7.0, 11.0, 52000, 2600),
        ("Maize silage", 0.35, 985, 60, -25, 390, 0.11, 5.0, 9.0, 38000, 2100),
        ("Production concentrate", 0.88, 1060, 125, 25, 220, 0.38, 2.0, 6.5, 9000, 850),
        ("Soy/rapeseed blend", 0.89, 1080, 190, 90, 180, 0.50, 0.0, 2.5, 4500, 280),
        ("Wheat straw", 0.86, 650, 35, -40, 720, 0.08, 0.2, 1.5, 6000, 180),
    ]
    ingredients = []
    for spec in feed_specs:
        name, dm, vem, dve, oeb, ndf, price, low, high, stock, daily = spec
        ing = FeedIngredient(
            farm_id=farm.id,
            name=name,
            dry_matter_fraction=dm,
            vem_per_kg_dm=vem,
            dve_g_per_kg_dm=dve,
            oeb_g_per_kg_dm=oeb,
            ndf_g_per_kg_dm=ndf,
            price_eur_per_kg_dm=price,
            min_kg_dm=low,
            max_kg_dm=high,
            source="demo-lab-analysis",
        )
        session.add(ing)
        ingredients.append((ing, stock, daily))
    await session.flush()
    for ing, stock, daily in ingredients:
        session.add(FeedInventory(farm_id=farm.id, ingredient_id=ing.id, stock_kg_as_fed=stock, daily_use_kg_as_fed=daily))

    high_group = groups[1]
    current = RationPlan(
        farm_id=farm.id,
        group_id=high_group.id,
        name="Current ration - High production",
        status="current",
        milk_price_eur_per_kg=0.47,
    )
    session.add(current)
    await session.flush()
    current_amounts = {
        "Grass silage": 9.2,
        "Maize silage": 7.0,
        "Production concentrate": 4.8,
        "Soy/rapeseed blend": 1.0,
        "Wheat straw": 0.4,
    }
    current_cost = 0.0
    for ing, _, _ in ingredients:
        kg = current_amounts[ing.name]
        current_cost += kg * ing.price_eur_per_kg_dm
        session.add(RationItem(plan_id=current.id, ingredient_id=ing.id, kg_dm_per_cow_day=kg))
    current.cost_eur_per_cow_day = current_cost

    session.add(Integration(farm_id=farm.id, provider="demo", status="connected", config_json={"mode": "synthetic-nrt"}, last_sync_at=datetime.now(timezone.utc)))
    session.add(Integration(farm_id=farm.id, provider="lely", status="not_connected", config_json={"recommended": True}))

    now = datetime.now(timezone.utc)
    observations = []
    for idx, animal in enumerate(animals):
        stage_factor = max(0.55, 1.15 - animal.days_in_milk / 500)
        base_milk = 38 * stage_factor + rng.uniform(-2.2, 2.2)
        base_rum = 520 + rng.uniform(-35, 35)
        base_activity = 100 + rng.uniform(-12, 12)
        base_feed = 21.0 * stage_factor + 5 + rng.uniform(-1, 1)
        base_cond = 4.6 + rng.uniform(-0.3, 0.3)

        # one stable personal-baseline observation per day, 14 days
        for day in range(14, 0, -1):
            ts = now - timedelta(days=day, hours=rng.randint(0, 4))
            vals = {
                "milk_yield": (base_milk * rng.uniform(0.96, 1.04), "kg/day"),
                "rumination": (base_rum * rng.uniform(0.95, 1.05), "min/day"),
                "activity": (base_activity * rng.uniform(0.92, 1.08), "index"),
                "feed_intake": (base_feed * rng.uniform(0.95, 1.05), "kg DM/day"),
                "conductivity": (base_cond * rng.uniform(0.96, 1.04), "mS/cm"),
            }
            for kind, (value, unit) in vals.items():
                observations.append(SensorObservation(farm_id=farm.id, animal_id=animal.id, kind=kind, value=value, unit=unit, observed_at=ts, source="demo"))

        # hourly last-day data; special cows develop recent anomalies in the final 8 hours
        for hour in range(24, 0, -1):
            ts = now - timedelta(hours=hour)
            recent = hour <= 8
            mods = {"milk_yield": 1.0, "rumination": 1.0, "activity": 1.0, "feed_intake": 1.0, "conductivity": 1.0}
            if recent and animal.external_id == "NL-0184":
                mods.update(milk_yield=0.79, rumination=0.72, activity=0.86, conductivity=1.28)
            if recent and animal.external_id == "NL-0441":
                mods.update(milk_yield=0.88, rumination=0.74, feed_intake=0.76, activity=0.88)
            if recent and animal.external_id == "NL-0081":
                mods.update(activity=0.48, rumination=0.88)
            if recent and animal.external_id == "NL-0382":
                mods.update(feed_intake=0.79, rumination=0.86, milk_yield=0.93)
            vals = {
                "milk_yield": (base_milk * mods["milk_yield"] * rng.uniform(0.985, 1.015), "kg/day"),
                "rumination": (base_rum * mods["rumination"] * rng.uniform(0.98, 1.02), "min/day"),
                "activity": (base_activity * mods["activity"] * rng.uniform(0.96, 1.04), "index"),
                "feed_intake": (base_feed * mods["feed_intake"] * rng.uniform(0.985, 1.015), "kg DM/day"),
                "conductivity": (base_cond * mods["conductivity"] * rng.uniform(0.985, 1.015), "mS/cm"),
            }
            for kind, (value, unit) in vals.items():
                observations.append(SensorObservation(farm_id=farm.id, animal_id=animal.id, kind=kind, value=value, unit=unit, observed_at=ts, source="demo"))
    session.add_all(observations)

    knowledge = [
        KnowledgeChunk(
            title="CVB feed evaluation and VEM system",
            source_url="https://www.cvbdiervoeding.nl/",
            language="en",
            tags=["feed", "VEM", "DVE", "nutrition", "CVB", "rantsoen"],
            content="Dutch dairy rations are commonly evaluated using CVB concepts such as VEM for energy and DVE/OEB for protein balance. FarmIQ keeps these as explicit constraints and expects farm or licensed feed-analysis values rather than inventing composition data.",
        ),
        KnowledgeChunk(
            title="ICAR dairy cattle health recording",
            source_url="https://www.icar.org/Guidelines/07.1-Functional-traits-Dairy-cattle-health.pdf",
            language="en",
            tags=["mastitis", "lameness", "ketosis", "health", "ICAR", "gezondheid"],
            content="Standardized dairy health recording distinguishes observed health events from sensor-derived warnings. FarmIQ therefore presents early risk signals as decision support and captures farmer confirmation as a separate outcome label.",
        ),
        KnowledgeChunk(
            title="FarmIQ HealthIQ interpretation",
            source_url="https://www.icar.org/",
            language="en",
            tags=["rumination", "activity", "baseline", "risk", "alert"],
            content="A useful sensor alert compares a cow with her own recent stable baseline and combines multiple signals. A change in rumination, activity, milk or feed intake is evidence to inspect, not by itself a clinical diagnosis.",
        ),
    ]
    session.add_all(knowledge)
    await session.commit()
    await evaluate_farm(session, farm.id)
    return farm


async def simulate_demo_tick(session: AsyncSession, farm: Farm) -> int:
    """Append a 5-minute synthetic observation set so shared demo deployments keep moving."""
    rng = random.Random(int(datetime.now(timezone.utc).timestamp() // 300))
    animals = (await session.scalars(select(Animal).where(Animal.farm_id == farm.id, Animal.active))).all()
    ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ts = ts - timedelta(minutes=ts.minute % 5)
    existing = await session.scalar(select(SensorObservation.id).where(SensorObservation.farm_id == farm.id, SensorObservation.observed_at == ts, SensorObservation.source == "demo-nrt"))
    if existing:
        return 0
    rows = []
    for animal in animals:
        stage_factor = max(0.55, 1.15 - animal.days_in_milk / 500)
        base = {
            "milk_yield": (38 * stage_factor, "kg/day"),
            "rumination": (520.0, "min/day"),
            "activity": (100.0, "index"),
            "feed_intake": (21.0 * stage_factor + 5, "kg DM/day"),
            "conductivity": (4.6, "mS/cm"),
        }
        for kind, (value, unit) in base.items():
            drift = 1 + 0.012 * math.sin(ts.minute / 60 * math.pi * 2) + rng.uniform(-0.01, 0.01)
            rows.append(SensorObservation(farm_id=farm.id, animal_id=animal.id, kind=kind, value=value * drift, unit=unit, observed_at=ts, source="demo-nrt"))
    session.add_all(rows)
    await session.commit()
    return len(rows)
