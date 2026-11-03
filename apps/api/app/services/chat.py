from __future__ import annotations

import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Animal, HealthRisk
from app.services.feed import OptimizationError, optimize_ration
from app.services.knowledge import retrieve

DUTCH_HINTS = {"welke", "koeien", "vandaag", "waarom", "voer", "melk", "gezondheid", "aandacht", "rantsoen", "risico"}


def detect_language(message: str, requested: str) -> str:
    if requested in {"en", "nl"}:
        return requested
    words = {word.lower().strip(".,?!:;") for word in message.split()}
    return "nl" if words & DUTCH_HINTS else "en"


async def _farm_context(session: AsyncSession, farm_id: uuid.UUID, message: str) -> dict:
    risks = (await session.scalars(
        select(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.active).order_by(HealthRisk.score.desc()).limit(8)
    )).all()
    animal_ids = {risk.animal_id for risk in risks}
    animals = (await session.scalars(select(Animal).where(Animal.id.in_(animal_ids)))) .all() if animal_ids else []
    animal_map = {a.id: a for a in animals}
    context = {
        "top_risks": [
            {
                "cow": animal_map.get(r.animal_id).external_id if animal_map.get(r.animal_id) else str(r.animal_id),
                "risk": r.risk_type,
                "score": r.score,
                "severity": r.severity,
                "evidence": r.evidence,
            }
            for r in risks
        ]
    }

    match = re.search(r"NL[- ]?0*(\d{1,4})", message, re.IGNORECASE)
    if match:
        normalized = f"NL-{int(match.group(1)):04d}"
        animal = await session.scalar(select(Animal).where(Animal.farm_id == farm_id, Animal.external_id == normalized))
        if animal:
            cow_risks = (await session.scalars(
                select(HealthRisk).where(HealthRisk.farm_id == farm_id, HealthRisk.animal_id == animal.id, HealthRisk.active).order_by(HealthRisk.score.desc())
            )).all()
            context["selected_cow"] = {
                "id": animal.external_id,
                "days_in_milk": animal.days_in_milk,
                "parity": animal.parity,
                "bcs": animal.body_condition_score,
                "risks": [{"type": r.risk_type, "score": r.score, "evidence": r.evidence} for r in cow_risks],
            }
    return context


def _fallback_answer(language: str, message: str, context: dict, docs: list, feed_context: dict | None) -> str:
    selected = context.get("selected_cow")
    if selected:
        if selected["risks"]:
            top = selected["risks"][0]
            evidence = "; ".join(item.get("message", item.get("signal", "")) for item in top["evidence"][:3])
            if language == "nl":
                return f"{selected['id']} heeft momenteel een {top['type']}-risicoscore van {top['score']:.0f}/100. Belangrijkste signalen: {evidence}. Dit is een vroeg waarschuwingssignaal, geen diagnose; controleer de koe en volg het bedrijfs-/dierenartsprotocol."
            return f"{selected['id']} currently has a {top['type']} risk score of {top['score']:.0f}/100. Main signals: {evidence}. This is an early-warning signal, not a diagnosis; inspect the cow and follow your farm/veterinary protocol."
        return (f"Voor {selected['id']} is er momenteel geen actieve HealthIQ-waarschuwing." if language == "nl" else f"There is currently no active HealthIQ alert for {selected['id']}.")

    lower = message.lower()
    if any(word in lower for word in ["attention", "aandacht", "risk", "risico", "health", "gezondheid"]):
        risks = context.get("top_risks", [])[:4]
        if not risks:
            return "Er zijn momenteel geen actieve HealthIQ-waarschuwingen." if language == "nl" else "There are currently no active HealthIQ alerts."
        summary = ", ".join(f"{r['cow']} ({r['risk']} {r['score']:.0f})" for r in risks)
        return (f"Deze koeien verdienen vandaag de meeste aandacht: {summary}. Open HealthIQ voor de onderliggende signalen en bevestig of verwerp de waarschuwing na controle." if language == "nl" else f"These cows need the most attention today: {summary}. Open HealthIQ for the underlying signals, then confirm or dismiss the alert after inspection.")

    if feed_context:
        saving = feed_context["saving_eur_per_cow_day"]
        group = feed_context["group_name"]
        if language == "nl":
            return f"Voor {group} vindt FeedIQ een haalbaar scenario met ongeveer €{saving:.2f} besparing per koe per dag. De aanbeveling respecteert DM-, VEM-, DVE-, NDF-, OEB- en voorraadbeperkingen en beperkt grote dagelijkse voerveranderingen."
        return f"For {group}, FeedIQ found a feasible scenario saving about €{saving:.2f} per cow per day. It respects DM, VEM, DVE, NDF, OEB and inventory constraints while limiting abrupt daily ration changes."

    if docs:
        doc = docs[0]
        return (f"Op basis van de kennisbron '{doc.title}': {doc.content}" if language == "nl" else f"Based on the knowledge source '{doc.title}': {doc.content}")

    return ("Ik kan vragen beantwoorden over koeien, HealthIQ-risico's, voer, voorraad en rantsoenscenario's. Probeer bijvoorbeeld: ‘Welke koeien hebben vandaag aandacht nodig?’" if language == "nl" else "I can answer questions about cows, HealthIQ risks, feed, inventory and ration scenarios. Try: 'Which cows need attention today?'")


async def answer(session: AsyncSession, farm_id: uuid.UUID, message: str, requested_language: str) -> dict:
    language = detect_language(message, requested_language)
    context = await _farm_context(session, farm_id, message)
    docs = await retrieve(session, message)
    feed_context = None
    lower = message.lower()
    if any(word in lower for word in ["feed", "ration", "voer", "rantsoen", "cost", "kosten"]):
        from app.models import AnimalGroup
        group = await session.scalar(select(AnimalGroup).where(AnimalGroup.farm_id == farm_id, AnimalGroup.stage == "high"))
        if group:
            try:
                feed_context = await optimize_ration(session, farm_id, group.id)
                context["feed_scenario"] = feed_context
            except OptimizationError:
                pass

    sources = [{"title": d.title, "url": d.source_url} for d in docs]
    fallback = _fallback_answer(language, message, context, docs, feed_context)

    if not settings.llm_base_url:
        return {"answer": fallback, "language": language, "sources": sources, "tool_context": context}

    prompt = {
        "role": "system",
        "content": (
            "You are Ask-IQ, a dairy farm decision-support assistant. Answer in Dutch if language=nl, otherwise English. "
            "Use only the supplied farm context and knowledge. Never diagnose disease; describe risk and recommend inspection/professional protocols. "
            "Do not invent sensor values, feed analyses, citations or actions. Be concise and farmer-friendly."
        ),
    }
    user = {"role": "user", "content": f"language={language}\nquestion={message}\nfarm_context={context}\nknowledge={[d.content for d in docs]}"}
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={"model": settings.llm_model, "messages": [prompt, user], "temperature": 0.2},
            )
            response.raise_for_status()
            generated = response.json()["choices"][0]["message"]["content"]
            return {"answer": generated, "language": language, "sources": sources, "tool_context": context}
    except Exception:
        return {"answer": fallback, "language": language, "sources": sources, "tool_context": context}
