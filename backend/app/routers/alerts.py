"""Endpoints for price-watch alerts (Flow 3: stay safe)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import alerts

router = APIRouter(tags=["Price Watch"])


class SpikeRequest(BaseModel):
    percent: float = Field(default=15, gt=-50, lt=100, examples=[15])


@router.get("/alerts", response_model=list[schemas.AlertOut])
def list_alerts(unread_only: bool = False, db: Session = Depends(get_db)):
    """Alerts, newest first."""
    q = db.query(models.Alert)
    if unread_only:
        q = q.filter(models.Alert.is_read.is_(False))
    return q.order_by(models.Alert.id.desc()).all()


@router.post("/alerts/check", response_model=list[schemas.AlertOut])
def run_price_watch(db: Session = Depends(get_db)):
    """Re-cost every open quotation at today's prices. Returns only NEW alerts."""
    return alerts.check_open_quotations(db)


@router.post("/alerts/{alert_id}/read", response_model=schemas.AlertOut)
def mark_read(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(models.Alert, alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    a.is_read = True
    db.commit()
    db.refresh(a)
    return a


@router.post("/materials/{material_id}/simulate-spike", response_model=list[schemas.AlertOut])
def simulate_spike(material_id: int, req: SpikeRequest, db: Session = Depends(get_db)):
    """DEMO: push today's price of a material up (or down), then run the price watch.
    Run `python -m data.seed` to reset prices afterwards."""
    if db.get(models.Material, material_id) is None:
        raise HTTPException(status_code=404, detail="Material not found")
    alerts.simulate_price_spike(db, material_id, req.percent)
    return alerts.check_open_quotations(db)
