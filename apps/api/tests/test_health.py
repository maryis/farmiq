from types import SimpleNamespace
from app.services.health import score_animal


def test_mastitis_signal_is_explainable():
    animal = SimpleNamespace(days_in_milk=80)
    risks = score_animal(animal, {
        "milk_yield": -21,
        "rumination": -28,
        "activity": -10,
        "feed_intake": -8,
        "conductivity": 28,
    })
    mastitis = next(row for row in risks if row["risk_type"] == "mastitis")
    assert mastitis["score"] >= 70
    assert len(mastitis["evidence"]) >= 2


def test_early_lactation_contributes_to_ketosis():
    animal = SimpleNamespace(days_in_milk=12)
    risks = score_animal(animal, {
        "milk_yield": -12,
        "rumination": -22,
        "activity": -8,
        "feed_intake": -25,
        "conductivity": 0,
    })
    ketosis = next(row for row in risks if row["risk_type"] == "ketosis")
    assert ketosis["score"] >= 70
