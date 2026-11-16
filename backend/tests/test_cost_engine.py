"""Tests for the cost engine. Run from backend/:  pytest -v

Every expected number below was worked out by hand, so if these pass,
the engine's math is correct."""
import pytest

from app.services.cost_engine import CostSettings, OrderInput, calculate

# Simple round numbers so the hand calculations are easy to follow
SETTINGS = CostSettings(
    labour_rate_per_hr=100,
    machine_rate_per_hr=300,
    power_cost_per_hr=100,
    scrap_percent=20,          # buy 1 / 0.8 = 1.25 kg for every 1 kg of finished part
    overhead_percent=10,
    target_margin_percent=20,
)

ORDER = OrderInput(
    quantity=100,
    weight_per_piece_kg=2,          # x 1.25 = 2.5 kg raw per piece
    material_price_per_kg=60,
    machine_hours_per_piece=0.5,
    labour_hours_per_piece=0.5,
)


def test_full_breakdown():
    r = calculate(ORDER, SETTINGS)
    assert r.raw_material_kg_per_piece == 2.5
    assert r.material_cost == 15000      # 100 x 2.5 kg x ₹60
    assert r.machine_cost == 20000       # 100 x 0.5 h x (300 + 100)
    assert r.labour_cost == 5000         # 100 x 0.5 h x 100
    assert r.direct_cost == 40000
    assert r.overhead_cost == 4000       # 10% of 40,000
    assert r.total_cost == 44000
    assert r.cost_per_piece == 440
    assert r.recommended_total == 52800  # 44,000 x 1.20
    assert r.recommended_price_per_piece == 528
    assert r.verdict == "no_price_given"


def test_owner_price_below_cost_is_a_loss():
    order = OrderInput(**{**ORDER.__dict__, "owner_price_per_piece": 400})
    r = calculate(order, SETTINGS)
    assert r.owner_total == 40000
    assert r.owner_profit == -4000       # 40,000 - 44,000
    assert r.verdict == "loss"


def test_thin_margin():
    order = OrderInput(**{**ORDER.__dict__, "owner_price_per_piece": 470})
    r = calculate(order, SETTINGS)
    assert r.owner_profit == 3000        # 47,000 - 44,000
    assert r.owner_margin_percent == 6.82  # below half of the 20% target
    assert r.verdict == "thin_margin"


def test_healthy_margin():
    order = OrderInput(**{**ORDER.__dict__, "owner_price_per_piece": 530})
    r = calculate(order, SETTINGS)
    assert r.verdict == "healthy"


def test_material_price_risk():
    r = calculate(ORDER, SETTINGS)
    # material 15,000 -> 16,500; direct 41,500; + 10% overhead = 45,650
    assert r.cost_if_material_up_10 == 45650


def test_no_machine_or_labour_time():
    order = OrderInput(quantity=10, weight_per_piece_kg=1, material_price_per_kg=100)
    r = calculate(order, SETTINGS)
    assert r.machine_cost == 0
    assert r.labour_cost == 0
    assert r.material_cost == 1250       # 10 x 1.25 kg x ₹100


@pytest.mark.parametrize("bad", [
    {"quantity": 0},
    {"weight_per_piece_kg": 0},
])
def test_bad_input_is_rejected(bad):
    order = OrderInput(**{**ORDER.__dict__, **bad})
    with pytest.raises(ValueError):
        calculate(order, SETTINGS)
