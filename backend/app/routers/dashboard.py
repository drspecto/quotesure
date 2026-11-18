"""One call that gives the dashboard's headline numbers."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services import alerts, price_service
from app.services.quote_checker import FAIR_MARKUP_PERCENT
from app.services.settings_service import get_factory_settings, to_cost_settings

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    fs = get_factory_settings(db)
    since = date.today() - timedelta(days=90)

    # Money paid above a fair price (market + 3%) in the last 90 days, per supplier
    overpaid_by_supplier: dict[str, float] = {}
    for p in db.query(models.Purchase).filter(models.Purchase.date >= since).all():
        market = price_service.get_price_on(db, p.material_id, p.date)
        if market is None:
            continue
        extra = (p.price_per_unit - market * (1 + FAIR_MARKUP_PERCENT / 100)) * p.quantity
        if extra > 0:
            overpaid_by_supplier[p.supplier.name] = overpaid_by_supplier.get(p.supplier.name, 0) + extra
    worst = max(overpaid_by_supplier.items(), key=lambda kv: kv[1], default=(None, 0))

    # Open quotations at today's prices
    settings = to_cost_settings(fs)
    at_risk = 0
    open_count = 0
    for q in db.query(models.Quotation).filter(models.Quotation.status == "open").all():
        open_count += 1
        today = alerts.recost_quotation(db, q, settings)
        if today and today[1] / today[0] * 100 < fs.target_margin_percent / 2:
            at_risk += 1

    return {
        "factory_name": fs.factory_name,
        "overpaid_90_days": round(sum(overpaid_by_supplier.values()), 2),
        "overpaid_by_supplier": {k: round(v, 2) for k, v in overpaid_by_supplier.items()},
        "worst_supplier": worst[0],
        "worst_supplier_overpaid": round(worst[1], 2),
        "open_quotes": open_count,
        "open_quotes_at_risk": at_risk,
        "unread_alerts": db.query(models.Alert).filter(models.Alert.is_read.is_(False)).count(),
        "supplier_quotes_checked": db.query(models.SupplierQuote).count(),
    }
