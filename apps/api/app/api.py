from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.demo import DEMO_SLUG
from app.models import (
    Animal,
    AnimalGroup,
    Farm,
    FarmMembership,
    FeedIngredient,
    FeedInventory,
    HealthFeedback,
    HealthRisk,
    Integration,
    Organization,
    SensorObservation,
    User,
)
from app.schemas import ChatRequest, ChatResponse, FeedbackRequest, LoginRequest, OptimizeRequest, RegisterRequest, TokenResponse
from app.security import create_token, ensure_farm_access, hash_password, optional_user, verify_password
from app.services.chat import answer
from app.services.feed import OptimizationError, optimize_ration

router = APIRouter(prefix="/v1")


@router.post("/auth/register", response_model=TokenResponse)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    if await session.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), display_name=body.display_name)
    org = Organization(name=f"{body.farm_name} organization")
    session.add_all([user, org])
    await session.flush()
    slug_base = re.sub(r"[^a-z0-9]+", "-", body.farm_name.lower()).strip("-") or "farm"
    slug = f"{slug_base}-{str(uuid.uuid4())[:8]}"
    farm = Farm(organization_id=org.id, name=body.farm_name, slug=slug, country_code="NL", timezone="Europe/Amsterdam")
    session.add(farm)
    await session.flush()
    session.add(FarmMembership(user_id=user.id, farm_id=farm.id, role="owner"))
    await session.commit()
    return TokenResponse(access_token=create_token(user.id), farm_id=farm.id)


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    membership = await session.scalar(select(FarmMembership).where(FarmMembership.user_id == user.id).order_by(FarmMembership.created_at))
    if not membership:
        raise HTTPException(status_code=403, detail="User has no farm")
    return TokenResponse(access_token=create_token(user.id), farm_id=membership.farm_id)


@router.get("/demo")
async def demo(session: AsyncSession = Depends(get_session)):
    farm = await session.scalar(select(Farm).where(Farm.slug == DEMO_SLUG))
    if not farm:
        raise HTTPException(status_code=503, detail="Demo farm not seeded")
    return {"farm_id": str(farm.id), "name": farm.name, "slug": farm.slug}


async def _animal_map(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Animal]:
    if not ids:
        return {}
    rows = (await session.scalars(select(Animal).where(Animal.id.in_(ids)))).all()
    return {row.id: row for row in rows}


@router.get("/farms/{farm_id}/dashboard")
async def dashboard(
    farm_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(optional_user),
):
    farm = await ensure_farm_access(session, farm_id, user)
    risks = (await session.scalars(select(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active).order_by(HealthRisk.score.desc()).limit(6))).all()
    amap = await _animal_map(session, {r.animal_id for r in risks})
    inventory_rows = (await session.execute(
        select(FeedInventory, FeedIngredient).join(FeedIngredient, FeedIngredient.id == FeedInventory.ingredient_id).where(FeedInventory.farm_id == farm_id)
    )).all()
    inventory = []
    for inv, ing in inventory_rows:
        days = inv.stock_kg_as_fed / inv.daily_use_kg_as_fed if inv.daily_use_kg_as_fed else 999
        inventory.append({"name": ing.name, "stock_kg": round(inv.stock_kg_as_fed), "days_remaining": round(days, 1), "warning": days < inv.reorder_threshold_days})
    high_group = await session.scalar(select(AnimalGroup).where(AnimalGroup.farm_id == farm_id, AnimalGroup.stage == "high"))
    feed = None
    if high_group:
        try:
            feed = await optimize_ration(session, farm_id, high_group.id)
        except OptimizationError:
            feed = None
    animal_count = await session.scalar(select(func.count()).select_from(Animal).where(Animal.farm_id == farm_id, Animal.active)) or 0
    active_alert_count = await session.scalar(select(func.count()).select_from(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active)) or 0
    high_alert_count = await session.scalar(select(func.count()).select_from(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active, HealthRisk.severity == "high")) or 0
    now = datetime.now(timezone.utc)
    recent_from = now - timedelta(hours=8)
    baseline_from = now - timedelta(hours=32)
    baseline_to = now - timedelta(hours=24)
    recent_milk = await session.scalar(select(func.avg(SensorObservation.value)).where(SensorObservation.farm_id == farm_id, SensorObservation.kind == "milk_yield", SensorObservation.observed_at >= recent_from))
    baseline_milk = await session.scalar(select(func.avg(SensorObservation.value)).where(SensorObservation.farm_id == farm_id, SensorObservation.kind == "milk_yield", SensorObservation.observed_at >= baseline_from, SensorObservation.observed_at < baseline_to))
    milk_change = ((recent_milk - baseline_milk) / baseline_milk * 100) if recent_milk and baseline_milk else 0.0
    return {
        "farm": {"id": str(farm.id), "name": farm.name},
        "stats": {"animals": animal_count, "active_alerts": active_alert_count, "high_alerts": high_alert_count, "milk_change_pct": round(milk_change, 1)},
        "risks": [
            {"id": str(r.id), "cow": amap[r.animal_id].external_id, "risk_type": r.risk_type, "score": r.score, "severity": r.severity, "evidence": r.evidence, "detected_at": r.detected_at}
            for r in risks if r.animal_id in amap
        ],
        "inventory": sorted(inventory, key=lambda row: row["days_remaining"]),
        "feed_opportunity": feed,
    }


@router.get("/farms/{farm_id}/animals")
async def animals(farm_id: uuid.UUID, limit: int = 200, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    rows = (await session.scalars(select(Animal).where(Animal.farm_id == farm_id, Animal.active).order_by(Animal.external_id).limit(min(limit, 500)))).all()
    active_risks = (await session.scalars(select(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active))).all()
    risk_map = {}
    for risk in active_risks:
        risk_map.setdefault(risk.animal_id, []).append(risk)
    return [
        {"id": str(a.id), "external_id": a.external_id, "name": a.name, "parity": a.parity, "days_in_milk": a.days_in_milk, "bcs": a.body_condition_score, "top_risk": max((r.score for r in risk_map.get(a.id, [])), default=0)}
        for a in rows
    ]


@router.get("/farms/{farm_id}/animals/{animal_id}")
async def animal_detail(farm_id: uuid.UUID, animal_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    animal = await session.get(Animal, animal_id)
    if not animal or animal.farm_id != farm_id:
        raise HTTPException(status_code=404, detail="Animal not found")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    obs = (await session.scalars(select(SensorObservation).where(SensorObservation.animal_id == animal_id, SensorObservation.observed_at >= cutoff).order_by(SensorObservation.observed_at))).all()
    risks = (await session.scalars(select(HealthRisk).where(HealthRisk.animal_id == animal_id, HealthRisk.active).order_by(HealthRisk.score.desc()))).all()
    return {
        "animal": {"id": str(animal.id), "external_id": animal.external_id, "name": animal.name, "parity": animal.parity, "days_in_milk": animal.days_in_milk, "bcs": animal.body_condition_score},
        "observations": [{"kind": o.kind, "value": o.value, "unit": o.unit, "observed_at": o.observed_at} for o in obs],
        "risks": [{"id": str(r.id), "risk_type": r.risk_type, "score": r.score, "severity": r.severity, "evidence": r.evidence} for r in risks],
    }


@router.get("/farms/{farm_id}/health-risks")
async def health_risks(farm_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    risks = (await session.scalars(select(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active).order_by(HealthRisk.score.desc()))).all()
    amap = await _animal_map(session, {r.animal_id for r in risks})
    return [{"id": str(r.id), "cow": amap[r.animal_id].external_id, "risk_type": r.risk_type, "score": r.score, "severity": r.severity, "evidence": r.evidence, "detected_at": r.detected_at} for r in risks if r.animal_id in amap]


@router.post("/farms/{farm_id}/health-risks/{risk_id}/feedback")
async def health_feedback(farm_id: uuid.UUID, risk_id: uuid.UUID, body: FeedbackRequest, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    risk = await session.get(HealthRisk, risk_id)
    if not risk or risk.farm_id != farm_id:
        raise HTTPException(status_code=404, detail="Risk not found")
    session.add(HealthFeedback(farm_id=farm_id, risk_id=risk_id, outcome=body.outcome, note=body.note))
    if body.outcome in {"dismissed", "resolved", "confirmed"}:
        risk.active = False
    await session.commit()
    return {"ok": True, "risk_active": risk.active}


@router.get("/farms/{farm_id}/feed/groups")
async def feed_groups(farm_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    rows = (await session.scalars(select(AnimalGroup).where(AnimalGroup.farm_id == farm_id).order_by(AnimalGroup.created_at))).all()
    return [{"id": str(g.id), "name": g.name, "stage": g.stage, "target_dmi_kg": g.target_dmi_kg} for g in rows]


@router.post("/farms/{farm_id}/feed/groups/{group_id}/optimize")
async def feed_optimize(farm_id: uuid.UUID, group_id: uuid.UUID, body: OptimizeRequest, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    try:
        return await optimize_ration(session, farm_id, group_id, body.milk_price_eur_per_kg, body.horizon_days, body.price_overrides, body.persist)
    except OptimizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/farms/{farm_id}/inventory")
async def inventory(farm_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    rows = (await session.execute(select(FeedInventory, FeedIngredient).join(FeedIngredient).where(FeedInventory.farm_id == farm_id))).all()
    return [{"ingredient_id": str(ing.id), "name": ing.name, "stock_kg_as_fed": round(inv.stock_kg_as_fed, 1), "daily_use_kg_as_fed": round(inv.daily_use_kg_as_fed, 1), "days_remaining": round(inv.stock_kg_as_fed / inv.daily_use_kg_as_fed, 1) if inv.daily_use_kg_as_fed else None, "price_eur_per_kg_dm": ing.price_eur_per_kg_dm, "dry_matter_fraction": ing.dry_matter_fraction} for inv, ing in rows]


@router.get("/farms/{farm_id}/integrations")
async def integrations(farm_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, farm_id, user)
    rows = (await session.scalars(select(Integration).where(Integration.farm_id == farm_id).order_by(Integration.provider))).all()
    return [{"id": str(row.id), "provider": row.provider, "status": row.status, "last_sync_at": row.last_sync_at, "last_error": row.last_error, "config": row.config_json} for row in rows]


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    await ensure_farm_access(session, body.farm_id, user)
    return await answer(session, body.farm_id, body.message, body.language)
