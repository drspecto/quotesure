"""Endpoints for checking supplier quotes (Flow 1: buy raw material right)."""
from dataclasses import asdict
from difflib import get_close_matches

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import extractor, negotiation, quote_checker

router = APIRouter(prefix="/buying", tags=["Supplier Quotes"])

MAX_FILE_MB = 10


def _match_supplier(db: Session, name: str) -> models.Supplier | None:
    """Find a known supplier whose name is close to the name on the quote."""
    if not name:
        return None
    suppliers = db.query(models.Supplier).all()
    by_lower = {s.name.lower(): s for s in suppliers}
    match = get_close_matches(name.lower(), list(by_lower), n=1, cutoff=0.6)
    return by_lower[match[0]] if match else None


def _save_and_respond(db: Session, supplier: models.Supplier | None, supplier_name: str,
                      file_name: str, items: list[dict], ai_notes: str = "") -> schemas.QuoteCheckOut:
    """Run the checks, draft the message, save everything, return the result."""
    check = quote_checker.check_quote(db, items)
    name = supplier.name if supplier else supplier_name
    message = negotiation.draft_message(name, check)

    quote = models.SupplierQuote(
        supplier_id=supplier.id if supplier else None,
        supplier_name=name,
        file_name=file_name,
        verdict=check.verdict,
        summary=check.summary,
        potential_saving=check.potential_saving,
        negotiation_message=message,
    )
    for c in check.items:
        quote.items.append(models.SupplierQuoteItem(
            material_id=c.material_id,
            raw_description=c.description,
            quantity=c.quantity_kg,
            price_per_unit=c.price_per_kg,
            market_price=c.market_price,
            difference_percent=c.difference_percent,
        ))
    db.add(quote)
    db.commit()
    db.refresh(quote)

    return schemas.QuoteCheckOut(
        id=quote.id, supplier_id=quote.supplier_id, supplier_name=name, file_name=file_name,
        created_at=quote.created_at, verdict=check.verdict, summary=check.summary,
        potential_saving=check.potential_saving, negotiation_message=message, ai_notes=ai_notes,
        items=[schemas.QuoteItemResult(**asdict(c)) for c in check.items],
    )


@router.post("/check-quote", response_model=schemas.QuoteCheckOut)
async def check_quote_file(
    file: UploadFile = File(..., description="Photo or PDF of the supplier's quote"),
    supplier_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Upload a quote. The AI reads it, then every line is checked against market prices."""
    data = await file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is bigger than {MAX_FILE_MB} MB")

    materials = [(m.id, f"{m.name} {m.grade}") for m in db.query(models.Material).all()]
    try:
        # Gemini calls are slow and "blocking", so run them on a separate thread.
        # Otherwise the whole server freezes while it waits.
        extracted = await run_in_threadpool(
            extractor.extract_quote, data, file.content_type or "", materials)
    except extractor.ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if not extracted.items:
        raise HTTPException(status_code=422,
                            detail=f"No items found on this quote. {extracted.notes}".strip())

    supplier = db.get(models.Supplier, supplier_id) if supplier_id else _match_supplier(db, extracted.supplier_name)
    items = [i.model_dump() for i in extracted.items]
    return await run_in_threadpool(_save_and_respond, db, supplier, extracted.supplier_name,
                                   file.filename or "", items, extracted.notes)


@router.post("/check-items", response_model=schemas.QuoteCheckOut)
def check_items(req: schemas.CheckItemsRequest, db: Session = Depends(get_db)):
    """Same check, but you type the items yourself (no AI reading needed)."""
    supplier = db.get(models.Supplier, req.supplier_id) if req.supplier_id else None
    if req.supplier_id and supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    items = [i.model_dump() for i in req.items]
    return _save_and_respond(db, supplier, "", "manual entry", items)


def _stored_out(db: Session, q: models.SupplierQuote) -> schemas.QuoteCheckOut:
    """Rebuild the response for a saved quote (re-checked against today's data)."""
    items = [dict(description=i.raw_description, material_id=i.material_id,
                  quantity_kg=i.quantity, price_per_kg=i.price_per_unit) for i in q.items]
    check = quote_checker.check_quote(db, items)
    return schemas.QuoteCheckOut(
        id=q.id, supplier_id=q.supplier_id, supplier_name=q.supplier_name, file_name=q.file_name,
        created_at=q.created_at, verdict=q.verdict, summary=q.summary,
        potential_saving=q.potential_saving, negotiation_message=q.negotiation_message,
        items=[schemas.QuoteItemResult(**asdict(c)) for c in check.items],
    )


@router.get("/quotes", response_model=list[schemas.QuoteCheckOut])
def list_checked_quotes(db: Session = Depends(get_db)):
    """Every supplier quote checked so far, newest first."""
    quotes = db.query(models.SupplierQuote).order_by(models.SupplierQuote.id.desc()).all()
    return [_stored_out(db, q) for q in quotes]


@router.get("/quotes/{quote_id}", response_model=schemas.QuoteCheckOut)
def get_checked_quote(quote_id: int, db: Session = Depends(get_db)):
    q = db.get(models.SupplierQuote, quote_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _stored_out(db, q)
