"""
THE COST ENGINE: works out the true cost of a customer order and a safe price.

Pure math only: no database, no AI. Every number the app shows about cost
comes from here, so it can be tested and trusted.

Formula (for the whole order):
    raw material per piece = finished weight / (1 - scrap%)
    material  = qty x raw material per piece x material price per kg
    machine   = qty x machine hours per piece x (machine rate + power cost per hour)
    labour    = qty x labour hours per piece x labour rate
    direct    = material + machine + labour
    overhead  = direct x overhead%
    TOTAL COST = direct + overhead                 (selling below this = loss)
    RECOMMENDED PRICE = total cost x (1 + target margin%)
"""
from dataclasses import dataclass


@dataclass
class CostSettings:
    """The factory's own rates (comes from the FactorySettings table)."""
    labour_rate_per_hr: float
    machine_rate_per_hr: float
    power_cost_per_hr: float
    scrap_percent: float
    overhead_percent: float
    target_margin_percent: float


@dataclass
class OrderInput:
    """What the owner knows about the customer's order."""
    quantity: int
    weight_per_piece_kg: float        # finished part weight
    material_price_per_kg: float      # usually today's market price
    machine_hours_per_piece: float = 0.0
    labour_hours_per_piece: float = 0.0
    owner_price_per_piece: float | None = None  # the price the owner was going to quote


@dataclass
class CostBreakdown:
    """Everything the engine works out. All money in ₹, for the whole order."""
    raw_material_kg_per_piece: float
    material_cost: float
    machine_cost: float
    labour_cost: float
    direct_cost: float
    overhead_cost: float
    total_cost: float
    cost_per_piece: float              # break-even price per piece
    recommended_price_per_piece: float
    recommended_total: float
    # Only filled when the owner gives their own price:
    owner_total: float | None = None
    owner_profit: float | None = None
    owner_margin_percent: float | None = None
    verdict: str = "no_price_given"    # loss / thin_margin / healthy / no_price_given
    # Risk check: what if material gets 10% costlier before the order is made?
    cost_if_material_up_10: float = 0.0


def _r(x: float) -> float:
    """Round money to 2 decimals."""
    return round(x, 2)


def calculate(order: OrderInput, s: CostSettings) -> CostBreakdown:
    if order.quantity <= 0:
        raise ValueError("quantity must be more than 0")
    if order.weight_per_piece_kg <= 0:
        raise ValueError("weight_per_piece_kg must be more than 0")
    if not 0 <= s.scrap_percent < 100:
        raise ValueError("scrap_percent must be between 0 and 99")

    q = order.quantity

    # Scrap: to END with 1 kg of part when 8% is wasted, you must BUY 1 / 0.92 = 1.087 kg
    raw_kg = order.weight_per_piece_kg / (1 - s.scrap_percent / 100)

    material = q * raw_kg * order.material_price_per_kg
    machine = q * order.machine_hours_per_piece * (s.machine_rate_per_hr + s.power_cost_per_hr)
    labour = q * order.labour_hours_per_piece * s.labour_rate_per_hr
    direct = material + machine + labour
    overhead = direct * s.overhead_percent / 100
    total = direct + overhead

    recommended_total = total * (1 + s.target_margin_percent / 100)

    # Same order, material 10% dearer (overhead grows with it)
    total_up_10 = (material * 1.10 + machine + labour) * (1 + s.overhead_percent / 100)

    result = CostBreakdown(
        raw_material_kg_per_piece=round(raw_kg, 4),
        material_cost=_r(material),
        machine_cost=_r(machine),
        labour_cost=_r(labour),
        direct_cost=_r(direct),
        overhead_cost=_r(overhead),
        total_cost=_r(total),
        cost_per_piece=_r(total / q),
        recommended_price_per_piece=_r(recommended_total / q),
        recommended_total=_r(recommended_total),
        cost_if_material_up_10=_r(total_up_10),
    )

    if order.owner_price_per_piece is not None:
        owner_total = order.owner_price_per_piece * q
        profit = owner_total - total
        margin = profit / total * 100
        result.owner_total = _r(owner_total)
        result.owner_profit = _r(profit)
        result.owner_margin_percent = round(margin, 2)
        if profit < 0:
            result.verdict = "loss"
        elif margin < s.target_margin_percent / 2:
            result.verdict = "thin_margin"
        else:
            result.verdict = "healthy"

    return result
