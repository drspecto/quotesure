"""Endpoints for suppliers and what we've bought from them."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import price_service

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


def _purchase_out(db: Session, p: models.Purchase) -> schemas.PurchaseOut:
    """Turn one Purchase row into the API shape, adding market price + markup."""
    return schemas.PurchaseOut(
        id=p.id,
        date=p.date,
        material_name=f"{p.material.name} {p.material.grade}",
        quantity=p.quantity,
        price_per_unit=p.price_per_unit,
        market_price=price_service.get_price_on(db, p.material_id, p.date),
        markup_percent=price_service.purchase_markup(db, p),
    )


def _supplier_summary(db: Session, s: models.Supplier) -> dict:
    """Fields shared by the list view and the detail view."""
    markups = [m for m in (price_service.purchase_markup(db, p) for p in s.purchases) if m is not None]
    return dict(
        id=s.id, name=s.name, city=s.city, phone=s.phone, rating=s.rating,
        purchase_count=len(s.purchases),
        avg_markup_percent=round(sum(markups) / len(markups), 2) if markups else None,
    )


@router.get("", response_model=list[schemas.SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    """All suppliers, with how much above market we pay them on average."""
    suppliers = db.query(models.Supplier).order_by(models.Supplier.id).all()
    return [schemas.SupplierOut(**_supplier_summary(db, s)) for s in suppliers]


@router.get("/{supplier_id}", response_model=schemas.SupplierDetailOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    """One supplier with every purchase, newest first."""
    s = db.get(models.Supplier, supplier_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    purchases = sorted(s.purchases, key=lambda p: p.date, reverse=True)
    return schemas.SupplierDetailOut(
        **_supplier_summary(db, s),
        purchases=[_purchase_out(db, p) for p in purchases],
    )
