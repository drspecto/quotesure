"""Endpoints for materials and their market prices."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import price_service

router = APIRouter(prefix="/materials", tags=["Materials & Prices"])


@router.get("", response_model=list[schemas.MaterialOut])
def list_materials(db: Session = Depends(get_db)):
    """All materials with today's price and the 30-day change."""
    result = []
    for m in db.query(models.Material).order_by(models.Material.id).all():
        latest = price_service.get_latest_price(db, m.id)
        change = None
        if latest:
            month_ago = price_service.get_price_on(db, m.id, latest.date - timedelta(days=30))
            if month_ago:
                change = price_service.percent_change(month_ago, latest.price_per_unit)
        result.append(schemas.MaterialOut(
            id=m.id, name=m.name, grade=m.grade, unit=m.unit,
            latest_price=latest.price_per_unit if latest else None,
            change_30d_percent=change,
        ))
    return result


@router.get("/{material_id}/prices", response_model=schemas.PriceHistoryOut)
def price_history(material_id: int, days: int = 90, db: Session = Depends(get_db)):
    """Daily price history for one material (for charts). Use ?days=30 for less."""
    material = db.get(models.Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    rows = price_service.get_price_history(db, material_id, days)
    return schemas.PriceHistoryOut(
        material_id=material.id,
        material_name=f"{material.name} {material.grade}",
        prices=[schemas.PricePoint.model_validate(r) for r in rows],
    )
