from __future__ import annotations

import uuid
from dataclasses import dataclass

try:
    from ortools.linear_solver import pywraplp
except ImportError:  # production image installs OR-Tools
    pywraplp = None
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Animal, AnimalGroup, FeedIngredient, FeedInventory, HealthRisk, RationItem, RationPlan

STANDARD = "CVB-VEM2022-compatible-contract-v1"


class OptimizationError(RuntimeError):
    pass


async def _current_ration(session: AsyncSession, farm_id: uuid.UUID, group_id: uuid.UUID) -> dict[uuid.UUID, float]:
    plan = await session.scalar(
        select(RationPlan).where(
            RationPlan.farm_id == farm_id,
            RationPlan.group_id == group_id,
            RationPlan.status == "current",
        ).order_by(RationPlan.created_at.desc())
    )
    if not plan:
        return {}
    rows = (await session.scalars(select(RationItem).where(RationItem.plan_id == plan.id))).all()
    return {row.ingredient_id: row.kg_dm_per_cow_day for row in rows}


async def optimize_ration(
    session: AsyncSession,
    farm_id: uuid.UUID,
    group_id: uuid.UUID,
    milk_price: float = 0.47,
    horizon_days: int = 7,
    price_overrides: dict[str, float] | None = None,
    persist: bool = False,
) -> dict:
    group = await session.get(AnimalGroup, group_id)
    if group is None or group.farm_id != farm_id:
        raise OptimizationError("Unknown group")

    ingredients = (await session.scalars(select(FeedIngredient).where(FeedIngredient.farm_id == farm_id))).all()
    inventories = (await session.scalars(select(FeedInventory).where(FeedInventory.farm_id == farm_id))).all()
    inventory_by_ingredient = {row.ingredient_id: row for row in inventories}
    current = await _current_ration(session, farm_id, group_id)
    cow_count = await session.scalar(select(func.count()).select_from(Animal).where(Animal.group_id == group_id, Animal.active)) or 1
    avg_bcs = await session.scalar(select(func.avg(Animal.body_condition_score)).where(Animal.group_id == group_id, Animal.active)) or 3.0
    high_risk_count = await session.scalar(
        select(func.count()).select_from(HealthRisk).join(Animal, Animal.id == HealthRisk.animal_id).where(
            HealthRisk.farm_id == farm_id, HealthRisk.active, HealthRisk.severity == "high", Animal.group_id == group_id
        )
    ) or 0

    # Small transparent adjustments: milk economics and BCS affect the energy target, while active high-risk cows make change limits conservative.
    price_factor = max(0.97, min(1.03, 1 + (milk_price - 0.47) * 0.12))
    bcs_factor = 1.015 if avg_bcs < 2.75 else 0.99 if avg_bcs > 3.5 else 1.0
    required_vem = group.target_vem * price_factor * bcs_factor
    required_dve = group.target_dve_g
    max_change = 0.8 if high_risk_count else 1.5

    if pywraplp is None:
        raise OptimizationError("OR-Tools is not installed; install the API production dependencies")
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if not solver:
        raise OptimizationError("OR-Tools linear solver is unavailable")

    variables = {}
    change_vars = {}
    costs = {}
    price_overrides = price_overrides or {}

    for ing in ingredients:
        inv = inventory_by_ingredient.get(ing.id)
        inventory_max = ing.max_kg_dm
        if inv:
            dm_stock = inv.stock_kg_as_fed * ing.dry_matter_fraction
            inventory_max = min(inventory_max, dm_stock / max(cow_count * horizon_days, 1))
        cur = current.get(ing.id, 0.0)
        low = max(ing.min_kg_dm, cur - max_change if current else ing.min_kg_dm)
        high = min(inventory_max, cur + max_change if current else inventory_max)
        if high < low:
            high = low
        x = solver.NumVar(low, high, f"x_{ing.id}")
        variables[ing.id] = x
        change = solver.NumVar(0, solver.infinity(), f"delta_{ing.id}")
        solver.Add(change >= x - cur)
        solver.Add(change >= cur - x)
        change_vars[ing.id] = change
        costs[ing.id] = price_overrides.get(str(ing.id), ing.price_eur_per_kg_dm)

    total_dm = solver.Sum(variables.values())
    solver.Add(total_dm >= max(0, group.target_dmi_kg - 1.2))
    solver.Add(total_dm <= group.target_dmi_kg + 1.2)
    solver.Add(solver.Sum(variables[i.id] * i.vem_per_kg_dm for i in ingredients) >= required_vem)
    solver.Add(solver.Sum(variables[i.id] * i.dve_g_per_kg_dm for i in ingredients) >= required_dve)
    solver.Add(solver.Sum(variables[i.id] * i.ndf_g_per_kg_dm for i in ingredients) >= group.min_ndf_g)
    solver.Add(solver.Sum(variables[i.id] * i.oeb_g_per_kg_dm for i in ingredients) >= group.oeb_min_g)

    objective = solver.Objective()
    for ing in ingredients:
        objective.SetCoefficient(variables[ing.id], costs[ing.id])
        objective.SetCoefficient(change_vars[ing.id], 0.025)
    objective.SetMinimization()

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        raise OptimizationError("No feasible ration found for the current nutrition/inventory constraints")

    items = []
    totals = {"dm_kg": 0.0, "vem": 0.0, "dve_g": 0.0, "oeb_g": 0.0, "ndf_g": 0.0}
    optimized_cost = 0.0
    current_cost = 0.0
    for ing in ingredients:
        new = variables[ing.id].solution_value()
        old = current.get(ing.id, 0.0)
        price = costs[ing.id]
        optimized_cost += new * price
        current_cost += old * price
        totals["dm_kg"] += new
        totals["vem"] += new * ing.vem_per_kg_dm
        totals["dve_g"] += new * ing.dve_g_per_kg_dm
        totals["oeb_g"] += new * ing.oeb_g_per_kg_dm
        totals["ndf_g"] += new * ing.ndf_g_per_kg_dm
        if new > 0.02 or old > 0.02:
            items.append({
                "ingredient_id": str(ing.id),
                "name": ing.name,
                "current_kg_dm": round(old, 2),
                "recommended_kg_dm": round(new, 2),
                "change_kg_dm": round(new - old, 2),
                "price_eur_per_kg_dm": round(price, 3),
            })

    saving = current_cost - optimized_cost
    result = {
        "standard": STANDARD,
        "group_id": str(group.id),
        "group_name": group.name,
        "cow_count": cow_count,
        "milk_price_eur_per_kg": milk_price,
        "cost_current_eur_per_cow_day": round(current_cost, 2),
        "cost_recommended_eur_per_cow_day": round(optimized_cost, 2),
        "saving_eur_per_cow_day": round(saving, 2),
        "saving_eur_per_month_group": round(saving * cow_count * 30, 0),
        "requirements": {
            "target_dmi_kg": group.target_dmi_kg,
            "required_vem": round(required_vem),
            "required_dve_g": round(required_dve),
            "min_ndf_g": round(group.min_ndf_g),
            "oeb_min_g": round(group.oeb_min_g),
        },
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "items": sorted(items, key=lambda row: row["recommended_kg_dm"], reverse=True),
        "explanation": [
            f"Balanced {cow_count} cows in {group.name} against DM, VEM, DVE, NDF and OEB constraints.",
            f"Milk price context adjusted the VEM target by {(price_factor - 1) * 100:+.1f}%.",
            f"Average BCS is {avg_bcs:.2f}; BCS energy adjustment is {(bcs_factor - 1) * 100:+.1f}%.",
            f"Daily ingredient movement was capped at {max_change:.1f} kg DM per cow to avoid abrupt ration changes.",
        ],
        "disclaimer": "Decision-support scenario. Validate ingredient analyses and ration changes with a qualified dairy nutritionist.",
    }

    if persist:
        plan = RationPlan(
            farm_id=farm_id,
            group_id=group_id,
            name=f"FeedIQ scenario - {group.name}",
            status="scenario",
            milk_price_eur_per_kg=milk_price,
            cost_eur_per_cow_day=optimized_cost,
            nutrition_summary=result["totals"],
        )
        session.add(plan)
        await session.flush()
        for item in items:
            session.add(RationItem(
                plan_id=plan.id,
                ingredient_id=uuid.UUID(item["ingredient_id"]),
                kg_dm_per_cow_day=item["recommended_kg_dm"],
            ))
        await session.commit()
        result["plan_id"] = str(plan.id)

    return result
