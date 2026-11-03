import uuid
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.models import Base, Farm, Organization, AnimalGroup, Animal, FeedIngredient, FeedInventory, RationPlan, RationItem
from app.services.feed import optimize_ration


@pytest.mark.asyncio
async def test_optimizer_returns_feasible_ration():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        org = Organization(name="Test")
        session.add(org); await session.flush()
        farm = Farm(organization_id=org.id, name="F", slug=f"f-{uuid.uuid4()}")
        session.add(farm); await session.flush()
        group = AnimalGroup(farm_id=farm.id, name="High", stage="high", target_dmi_kg=20, target_vem=19000, target_dve_g=1500, min_ndf_g=6000, oeb_min_g=-300)
        session.add(group); await session.flush()
        for i in range(20):
            session.add(Animal(farm_id=farm.id, group_id=group.id, external_id=f"C{i}", days_in_milk=80, body_condition_score=3.0))
        rough = FeedIngredient(farm_id=farm.id, name="Roughage", dry_matter_fraction=.4, vem_per_kg_dm=950, dve_g_per_kg_dm=65, oeb_g_per_kg_dm=-10, ndf_g_per_kg_dm=450, price_eur_per_kg_dm=.12, min_kg_dm=10, max_kg_dm=18)
        conc = FeedIngredient(farm_id=farm.id, name="Concentrate", dry_matter_fraction=.88, vem_per_kg_dm=1100, dve_g_per_kg_dm=180, oeb_g_per_kg_dm=40, ndf_g_per_kg_dm=150, price_eur_per_kg_dm=.38, min_kg_dm=2, max_kg_dm=8)
        session.add_all([rough, conc]); await session.flush()
        session.add_all([
            FeedInventory(farm_id=farm.id, ingredient_id=rough.id, stock_kg_as_fed=50000, daily_use_kg_as_fed=1500),
            FeedInventory(farm_id=farm.id, ingredient_id=conc.id, stock_kg_as_fed=10000, daily_use_kg_as_fed=300),
        ])
        plan = RationPlan(farm_id=farm.id, group_id=group.id, name="Current", status="current")
        session.add(plan); await session.flush()
        session.add_all([RationItem(plan_id=plan.id, ingredient_id=rough.id, kg_dm_per_cow_day=15), RationItem(plan_id=plan.id, ingredient_id=conc.id, kg_dm_per_cow_day=5)])
        await session.commit()

        result = await optimize_ration(session, farm.id, group.id)
        assert result["totals"]["vem"] >= result["requirements"]["required_vem"] - 1
        assert result["totals"]["dve_g"] >= result["requirements"]["required_dve_g"] - 1
        assert result["items"]
    await engine.dispose()
