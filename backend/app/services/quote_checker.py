"""
The quote CHECKER: is this supplier's price fair?

For each item it compares the quoted price with
  1. today's market price,
  2. what the factory last paid for the same material,
  3. the cheapest regular supplier for that material,
and works out how much the factory would save at a fair price.

Plain Python and database lookups only. No AI.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import models
from app.services import price_service

# A supplier needs some margin, so up to 3% above market counts as a fair price.
FAIR_MARKUP_PERCENT = 3.0
# More than 6% above market is flagged as overpriced.
OVERPRICED_ABOVE_PERCENT = 6.0


@dataclass
class ItemCheck:
    description: str
    material_id: int | None
    material_name: str | None
    quantity_kg: float
    price_per_kg: float
    market_price: float | None = None
    difference_percent: float | None = None   # +11 = 11% above market
    fair_price: float | None = None           # market + 3%
    potential_saving: float = 0.0             # ₹ for this line at the fair price
    last_paid_price: float | None = None
    last_paid_supplier: str | None = None
    best_supplier: str | None = None          # who usually sells this cheapest
    best_supplier_markup: float | None = None
    verdict: str = "unknown"                  # overpriced / fair / good_deal / unknown


@dataclass
class QuoteCheck:
    items: list[ItemCheck]
    verdict: str                              # overpriced / fair / good_deal / unknown
    potential_saving: float
    summary: str
    worst_item: ItemCheck | None = field(default=None)


def classify(difference_percent: float | None) -> str:
    """Turn '% above market' into a verdict word."""
    if difference_percent is None:
        return "unknown"
    if difference_percent > OVERPRICED_ABOVE_PERCENT:
        return "overpriced"
    if difference_percent < 0:
        return "good_deal"
    return "fair"


def saving_at_fair_price(price_per_kg: float, market_price: float, quantity_kg: float) -> float:
    """₹ the factory would save if this line were priced at market + 3%."""
    fair = market_price * (1 + FAIR_MARKUP_PERCENT / 100)
    return round(max(0.0, (price_per_kg - fair) * quantity_kg), 2)


def _last_purchase(db: Session, material_id: int) -> models.Purchase | None:
    return (
        db.query(models.Purchase)
        .filter(models.Purchase.material_id == material_id)
        .order_by(models.Purchase.date.desc())
        .first()
    )


def _best_supplier(db: Session, material_id: int) -> tuple[str, float] | None:
    """The supplier with the lowest average markup over market for this material."""
    by_supplier: dict[str, list[float]] = {}
    purchases = db.query(models.Purchase).filter(models.Purchase.material_id == material_id).all()
    for p in purchases:
        m = price_service.purchase_markup(db, p)
        if m is not None:
            by_supplier.setdefault(p.supplier.name, []).append(m)
    if not by_supplier:
        return None
    name, markups = min(by_supplier.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    return name, round(sum(markups) / len(markups), 2)


def check_item(db: Session, description: str, material_id: int | None,
               quantity_kg: float, price_per_kg: float) -> ItemCheck:
    item = ItemCheck(description=description, material_id=material_id, material_name=None,
                     quantity_kg=quantity_kg, price_per_kg=price_per_kg)
    material = db.get(models.Material, material_id) if material_id else None
    if material is None:
        item.material_id = None
        return item   # unknown material: we can't judge the price
    item.material_name = f"{material.name} {material.grade}"

    latest = price_service.get_latest_price(db, material.id)
    if latest:
        item.market_price = latest.price_per_unit
        item.difference_percent = price_service.percent_change(latest.price_per_unit, price_per_kg)
        item.fair_price = round(latest.price_per_unit * (1 + FAIR_MARKUP_PERCENT / 100), 2)
        item.potential_saving = saving_at_fair_price(price_per_kg, latest.price_per_unit, quantity_kg)

    last = _last_purchase(db, material.id)
    if last:
        item.last_paid_price = last.price_per_unit
        item.last_paid_supplier = last.supplier.name

    best = _best_supplier(db, material.id)
    if best:
        item.best_supplier, item.best_supplier_markup = best

    item.verdict = classify(item.difference_percent)
    return item


def check_quote(db: Session, items: list[dict]) -> QuoteCheck:
    """items: [{description, material_id, quantity_kg, price_per_kg}, ...]"""
    checks = [check_item(db, **i) for i in items]
    # Judge on the items we could price; items we couldn't match don't change the verdict
    verdicts = {c.verdict for c in checks} - {"unknown"}
    if "overpriced" in verdicts:
        verdict = "overpriced"
    elif verdicts == {"good_deal"}:
        verdict = "good_deal"
    elif verdicts:
        verdict = "fair"
    else:
        verdict = "unknown"

    saving = round(sum(c.potential_saving for c in checks), 2)
    judged = [c for c in checks if c.difference_percent is not None]
    worst = max(judged, key=lambda c: c.difference_percent) if judged else None
    return QuoteCheck(items=checks, verdict=verdict, potential_saving=saving,
                      summary=_summary(checks, verdict, saving, worst), worst_item=worst)


def _summary(checks: list[ItemCheck], verdict: str, saving: float, worst: ItemCheck | None) -> str:
    """A short plain-English verdict, built from the numbers (not by the AI)."""
    if verdict == "unknown":
        return "Could not match these items to known materials, so the price can't be judged."
    if verdict == "good_deal":
        return "Good deal: every item is priced below today's market rate."
    if verdict == "fair":
        return f"Fair quote: all items are within {OVERPRICED_ABOVE_PERCENT:.0f}% of today's market price."
    over = [c for c in checks if c.verdict == "overpriced"]
    text = (f"Overpriced: {len(over)} of {len(checks)} items are well above market. "
            f"Worst is {worst.material_name} at ₹{worst.price_per_kg:.2f}/kg, "
            f"{worst.difference_percent:.1f}% above today's ₹{worst.market_price:.2f}/kg. "
            f"Negotiating to a fair price saves about ₹{saving:,.0f}.")
    if worst.best_supplier:
        text += (f" {worst.best_supplier} usually sells this at about "
                 f"{worst.best_supplier_markup:.1f}% above market.")
    return text
