"""Price lookups. Plain Python + database queries, no AI.
Used by the API now, and later by the quote checker, cost engine and agent."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app import models


def get_latest_price(db: Session, material_id: int) -> models.MarketPrice | None:
    """Most recent market price row for a material."""
    return (
        db.query(models.MarketPrice)
        .filter(models.MarketPrice.material_id == material_id)
        .order_by(models.MarketPrice.date.desc())
        .first()
    )


def get_price_on(db: Session, material_id: int, on_date: date) -> float | None:
    """Market price on a given date (or the closest earlier date we have)."""
    row = (
        db.query(models.MarketPrice)
        .filter(models.MarketPrice.material_id == material_id,
                models.MarketPrice.date <= on_date)
        .order_by(models.MarketPrice.date.desc())
        .first()
    )
    return row.price_per_unit if row else None


def get_price_history(db: Session, material_id: int, days: int = 90) -> list[models.MarketPrice]:
    """All price rows for the last `days` days, oldest first (ready for a chart)."""
    since = date.today() - timedelta(days=days)
    return (
        db.query(models.MarketPrice)
        .filter(models.MarketPrice.material_id == material_id,
                models.MarketPrice.date >= since)
        .order_by(models.MarketPrice.date.asc())
        .all()
    )


def percent_change(old: float, new: float) -> float:
    """+10.0 means 'new' is 10% higher than 'old'."""
    if not old:
        return 0.0
    return round((new - old) / old * 100, 2)


def purchase_markup(db: Session, purchase: models.Purchase) -> float | None:
    """How much above (+) or below (-) market this purchase was, in %."""
    market = get_price_on(db, purchase.material_id, purchase.date)
    if market is None:
        return None
    return percent_change(market, purchase.price_per_unit)