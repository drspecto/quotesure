"""
PRICE WATCH: re-costs every open customer quotation at TODAY's material price
and raises an alert when one has turned loss-making or its margin got too thin.

Plain Python, no AI.
"""
from sqlalchemy.orm import Session

from app import models
from app.services import cost_engine, price_service
from app.services.settings_service import get_factory_settings, to_cost_settings


def recost_quotation(db: Session, q: models.Quotation,
                     settings: cost_engine.CostSettings) -> tuple[float, float] | None:
    """Returns (today's total cost, today's profit) for an open quotation."""
    latest = price_service.get_latest_price(db, q.material_id)
    if latest is None:
        return None
    today = cost_engine.calculate(
        cost_engine.OrderInput(
            quantity=q.quantity,
            weight_per_piece_kg=q.weight_per_piece_kg,
            material_price_per_kg=latest.price_per_unit,
            machine_hours_per_piece=q.machine_hours_per_piece,
            labour_hours_per_piece=q.labour_hours_per_piece,
        ),
        settings,
    )
    return today.total_cost, round(q.quoted_price - today.total_cost, 2)


def _already_alerted(db: Session, quotation_id: int, alert_type: str) -> bool:
    """Don't repeat an alert the owner hasn't read yet."""
    return db.query(models.Alert).filter(
        models.Alert.quotation_id == quotation_id,
        models.Alert.type == alert_type,
        models.Alert.is_read.is_(False),
    ).first() is not None


def check_open_quotations(db: Session) -> list[models.Alert]:
    """Check every open quotation and create new alerts. Returns the new ones."""
    fs = get_factory_settings(db)
    settings = to_cost_settings(fs)
    new_alerts = []

    for q in db.query(models.Quotation).filter(models.Quotation.status == "open").all():
        result = recost_quotation(db, q, settings)
        if result is None:
            continue
        today_cost, today_profit = result
        margin = today_profit / today_cost * 100 if today_cost else 0
        material = f"{q.material.name} {q.material.grade}"
        price_now = price_service.get_latest_price(db, q.material_id).price_per_unit
        move = price_service.percent_change(q.material_price_used, price_now)

        if today_profit < 0:
            alert_type = "loss_risk"
            message = (f"Quote Q-{q.id:04d} for {q.customer_name} ({q.part_name}) now LOSES "
                       f"₹{-today_profit:,.0f}. {material} is ₹{price_now:.2f}/kg, "
                       f"{move:+.1f}% since you quoted at ₹{q.material_price_used:.2f}. "
                       f"Revise the price before confirming the order.")
        elif margin < fs.target_margin_percent / 2:
            alert_type = "thin_margin"
            message = (f"Quote Q-{q.id:04d} for {q.customer_name} ({q.part_name}) now makes only "
                       f"{margin:.1f}% profit (₹{today_profit:,.0f}), below half your "
                       f"{fs.target_margin_percent:.0f}% target. {material} is {move:+.1f}% "
                       f"since you quoted.")
        else:
            continue

        if _already_alerted(db, q.id, alert_type):
            continue
        if alert_type == "loss_risk":
            # A loss replaces an older "thin margin" warning for the same quote
            db.query(models.Alert).filter(
                models.Alert.quotation_id == q.id, models.Alert.type == "thin_margin",
                models.Alert.is_read.is_(False)).update({"is_read": True})
        alert = models.Alert(type=alert_type, message=message, quotation_id=q.id)
        db.add(alert)
        new_alerts.append(alert)

    db.commit()
    for a in new_alerts:
        db.refresh(a)
    return new_alerts


def simulate_price_spike(db: Session, material_id: int, percent: float) -> models.MarketPrice:
    """DEMO ONLY: raise today's market price of one material by `percent`."""
    latest = price_service.get_latest_price(db, material_id)
    if latest is None:
        raise ValueError("No price for this material")
    latest.price_per_unit = round(latest.price_per_unit * (1 + percent / 100), 2)
    db.commit()
    db.refresh(latest)
    return latest
