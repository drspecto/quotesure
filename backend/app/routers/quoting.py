"""Endpoints for quoting customer orders: estimate, save, list, PDF."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import cost_engine, pdf_service, price_service
from app.services.settings_service import get_factory_settings, to_cost_settings

router = APIRouter(prefix="/quotes", tags=["Customer Quotes"])


def _material_and_price(db: Session, req: schemas.QuoteRequest) -> tuple[models.Material, float]:
    """Find the material and decide which ₹/kg to use (owner's price or today's market)."""
    material = db.get(models.Material, req.material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    if req.material_price_per_kg is not None:
        return material, req.material_price_per_kg
    latest = price_service.get_latest_price(db, material.id)
    if latest is None:
        raise HTTPException(status_code=400, detail="No market price for this material; send material_price_per_kg")
    return material, latest.price_per_unit


def _run_engine(db: Session, req: schemas.QuoteRequest, price_per_kg: float,
                owner_price: float | None) -> cost_engine.CostBreakdown:
    order = cost_engine.OrderInput(
        quantity=req.quantity,
        weight_per_piece_kg=req.weight_per_piece_kg,
        material_price_per_kg=price_per_kg,
        machine_hours_per_piece=req.machine_hours_per_piece,
        labour_hours_per_piece=req.labour_hours_per_piece,
        owner_price_per_piece=owner_price,
    )
    return cost_engine.calculate(order, to_cost_settings(get_factory_settings(db)))


def _quotation_out(db: Session, q: models.Quotation) -> schemas.QuotationOut:
    """Quotation + profit, and the same order re-costed at today's material price."""
    profit = q.quoted_price - q.total_cost
    today_price = today_cost = today_profit = None
    latest = price_service.get_latest_price(db, q.material_id)
    if latest:
        today_price = latest.price_per_unit
        today = cost_engine.calculate(
            cost_engine.OrderInput(
                quantity=q.quantity,
                weight_per_piece_kg=q.weight_per_piece_kg,
                material_price_per_kg=today_price,
                machine_hours_per_piece=q.machine_hours_per_piece,
                labour_hours_per_piece=q.labour_hours_per_piece,
            ),
            to_cost_settings(get_factory_settings(db)),
        )
        today_cost = today.total_cost
        today_profit = round(q.quoted_price - today_cost, 2)
    return schemas.QuotationOut(
        id=q.id,
        customer_name=q.customer_name,
        part_name=q.part_name,
        material_name=f"{q.material.name} {q.material.grade}",
        quantity=q.quantity,
        price_per_piece=round(q.quoted_price / q.quantity, 2),
        quoted_price=q.quoted_price,
        total_cost=q.total_cost,
        profit=round(profit, 2),
        margin_percent=round(profit / q.total_cost * 100, 2),
        material_price_used=q.material_price_used,
        status=q.status,
        created_at=q.created_at,
        valid_until=q.valid_until,
        today_material_price=today_price,
        today_total_cost=today_cost,
        today_profit=today_profit,
    )


@router.post("/estimate", response_model=schemas.CostBreakdownOut)
def estimate(req: schemas.QuoteRequest, db: Session = Depends(get_db)):
    """Work out the true cost and a safe price. Nothing is saved.
    Add owner_price_per_piece to check whether your own price makes a loss."""
    material, price = _material_and_price(db, req)
    b = _run_engine(db, req, price, req.owner_price_per_piece)
    return schemas.CostBreakdownOut(
        material_name=f"{material.name} {material.grade}",
        material_price_used=price,
        **b.__dict__,
    )


@router.post("", response_model=schemas.QuotationOut, status_code=201)
def create_quote(req: schemas.QuoteCreate, db: Session = Depends(get_db)):
    """Save a quotation for a customer (uses the recommended price unless you give one)."""
    material, price = _material_and_price(db, req)
    b = _run_engine(db, req, price, None)
    per_piece = req.final_price_per_piece or b.recommended_price_per_piece
    q = models.Quotation(
        customer_name=req.customer_name,
        part_name=req.part_name,
        material_id=material.id,
        quantity=req.quantity,
        weight_per_piece_kg=req.weight_per_piece_kg,
        machine_hours_per_piece=req.machine_hours_per_piece,
        labour_hours_per_piece=req.labour_hours_per_piece,
        material_price_used=price,
        total_cost=b.total_cost,
        quoted_price=round(per_piece * req.quantity, 2),
        valid_until=date.today() + timedelta(days=req.valid_days),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _quotation_out(db, q)


@router.get("", response_model=list[schemas.QuotationOut])
def list_quotes(status: str | None = None, db: Session = Depends(get_db)):
    """All quotations, newest first. Filter with ?status=open"""
    query = db.query(models.Quotation)
    if status:
        query = query.filter(models.Quotation.status == status)
    return [_quotation_out(db, q) for q in query.order_by(models.Quotation.id.desc()).all()]


@router.get("/{quote_id}", response_model=schemas.QuotationOut)
def get_quote(quote_id: int, db: Session = Depends(get_db)):
    q = db.get(models.Quotation, quote_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _quotation_out(db, q)


@router.get("/{quote_id}/pdf", response_class=Response)
def quote_pdf(quote_id: int, db: Session = Depends(get_db)):
    """Download the quotation as a PDF to send to the customer."""
    q = db.get(models.Quotation, quote_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    pdf = pdf_service.quotation_pdf(q, get_factory_settings(db).factory_name)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="quotation-Q{q.id:04d}.pdf"'},
    )
