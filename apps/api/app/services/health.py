from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Animal, HealthFeedback, HealthRisk, SensorObservation

MODEL_VERSION = "eu-rules-personal-baseline-v1"


def _pct_change(recent: list[float], baseline: list[float]) -> float | None:
    if not recent or not baseline:
        return None
    base = mean(baseline)
    if abs(base) < 1e-9:
        return None
    return (mean(recent) - base) / base * 100.0


def _severity(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "watch"


def _evidence(label: str, pct: float | None, direction: str = "drop") -> dict | None:
    if pct is None:
        return None
    is_relevant = pct < -5 if direction == "drop" else pct > 5
    if not is_relevant:
        return None
    return {
        "signal": label,
        "change_pct": round(pct, 1),
        "message": f"{label} {'decreased' if pct < 0 else 'increased'} {abs(pct):.1f}% vs personal baseline",
    }


def score_animal(animal: Animal, signal_changes: dict[str, float | None]) -> list[dict]:
    milk = signal_changes.get("milk_yield")
    rum = signal_changes.get("rumination")
    activity = signal_changes.get("activity")
    feed = signal_changes.get("feed_intake")
    conductivity = signal_changes.get("conductivity")

    drop = lambda value: max(0.0, -(value or 0.0))
    rise = lambda value: max(0.0, value or 0.0)

    mastitis = 18 + 1.15 * drop(milk) + 0.85 * drop(rum) + 0.75 * rise(conductivity)
    ketosis = 12 + (22 if 3 <= animal.days_in_milk <= 45 else 0) + 1.15 * drop(feed) + 0.7 * drop(rum) + 0.45 * drop(milk)
    lameness = 15 + 1.45 * drop(activity) + 0.45 * drop(rum)

    candidates = [
        ("mastitis", mastitis, [
            _evidence("Milk yield", milk), _evidence("Rumination", rum), _evidence("Milk conductivity", conductivity, "rise")
        ]),
        ("ketosis", ketosis, [
            _evidence("Feed intake", feed), _evidence("Rumination", rum), _evidence("Milk yield", milk),
            {"signal": "Lactation stage", "value": animal.days_in_milk, "message": f"{animal.days_in_milk} days in milk"} if 3 <= animal.days_in_milk <= 45 else None,
        ]),
        ("lameness", lameness, [
            _evidence("Activity", activity), _evidence("Rumination", rum)
        ]),
    ]

    results = []
    for risk_type, score, evidence in candidates:
        score = min(99.0, round(score, 1))
        if score < 45:
            continue
        results.append({
            "risk_type": risk_type,
            "score": score,
            "severity": _severity(score),
            "evidence": [item for item in evidence if item],
        })
    return results


async def evaluate_farm(session: AsyncSession, farm_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=15)
    recent_cutoff = now - timedelta(hours=8)
    baseline_cutoff = now - timedelta(hours=24)

    animals = (await session.scalars(select(Animal).where(Animal.farm_id == farm_id, Animal.active))).all()
    feedback_rows = (await session.execute(
        select(HealthRisk.animal_id, HealthRisk.risk_type, HealthFeedback.outcome, HealthFeedback.created_at)
        .join(HealthFeedback, HealthFeedback.risk_id == HealthRisk.id)
        .where(HealthRisk.farm_id == farm_id, HealthFeedback.created_at >= now - timedelta(hours=12))
    )).all()
    suppressed = {(animal_id, risk_type) for animal_id, risk_type, outcome, _ in feedback_rows if outcome in {"confirmed", "dismissed", "resolved"}}
    obs = (await session.scalars(
        select(SensorObservation).where(
            SensorObservation.farm_id == farm_id, SensorObservation.observed_at >= cutoff
        )
    )).all()

    grouped: dict[uuid.UUID, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"recent": [], "baseline": []})
    )
    for row in obs:
        observed_at = row.observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        bucket = "recent" if observed_at >= recent_cutoff else "baseline" if observed_at < baseline_cutoff else None
        if bucket:
            grouped[row.animal_id][row.kind][bucket].append(row.value)

    # Preserve historical rows because farmer feedback references them; only deactivate the previous snapshot.
    await session.execute(update(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active).values(active=False))
    created = 0
    for animal in animals:
        signal_changes = {}
        for kind in ("milk_yield", "rumination", "activity", "feed_intake", "conductivity"):
            values = grouped[animal.id][kind]
            signal_changes[kind] = _pct_change(values["recent"], values["baseline"])
        for scored in score_animal(animal, signal_changes):
            if (animal.id, scored["risk_type"]) in suppressed:
                continue
            session.add(HealthRisk(
                farm_id=farm_id,
                animal_id=animal.id,
                detected_at=now,
                model_version=MODEL_VERSION,
                active=True,
                **scored,
            ))
            created += 1
    await session.commit()
    return created
