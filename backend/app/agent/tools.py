"""
The TOOLS the AI agent is allowed to use.

Each tool is a normal Python function that uses our existing services, plus a
description (a JSON schema) that tells Gemini what the tool does and what
arguments it takes. Gemini decides WHICH tool to call; our code runs it and
hands back the result. Gemini never calculates a number itself.
"""
from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app import models
from app.services import alerts, cost_engine, negotiation, price_service, quote_checker
from app.services.settings_service import get_factory_settings, to_cost_settings


def _material_label(m: models.Material) -> str:
    return f"{m.name} {m.grade}"


def _find_supplier(db: Session, name: str) -> models.Supplier | None:
    name = (name or "").lower().strip()
    for s in db.query(models.Supplier).all():
        if name and (name in s.name.lower() or s.name.lower().startswith(name.split()[0])):
            return s
    return None


# ---------- The tools ----------

def get_market_prices(db: Session) -> dict:
    out = []
    for m in db.query(models.Material).order_by(models.Material.id).all():
        latest = price_service.get_latest_price(db, m.id)
        month_ago = price_service.get_price_on(db, m.id, latest.date - timedelta(days=30)) if latest else None
        out.append({
            "material_id": m.id,
            "material": _material_label(m),
            "price_today_per_kg": latest.price_per_unit if latest else None,
            "change_30_days_percent": price_service.percent_change(month_ago, latest.price_per_unit) if month_ago else None,
        })
    return {"date": date.today().isoformat(), "materials": out}


def get_suppliers(db: Session) -> dict:
    out = []
    for s in db.query(models.Supplier).order_by(models.Supplier.id).all():
        markups = [m for m in (price_service.purchase_markup(db, p) for p in s.purchases) if m is not None]
        out.append({
            "supplier": s.name, "city": s.city, "purchases": len(s.purchases),
            "average_percent_above_market": round(sum(markups) / len(markups), 2) if markups else None,
        })
    return {"suppliers": out}


def get_supplier_history(db: Session, supplier_name: str) -> dict:
    s = _find_supplier(db, supplier_name)
    if s is None:
        return {"error": f"No supplier called '{supplier_name}'. Known: "
                         + ", ".join(x.name for x in db.query(models.Supplier).all())}
    by_material: dict[str, list[models.Purchase]] = {}
    for p in s.purchases:
        by_material.setdefault(_material_label(p.material), []).append(p)
    rows = []
    for label, ps in by_material.items():
        ps.sort(key=lambda p: p.date)
        markups = [m for m in (price_service.purchase_markup(db, p) for p in ps) if m is not None]
        rows.append({
            "material": label, "purchases": len(ps),
            "total_kg": sum(p.quantity for p in ps),
            "last_price_per_kg": ps[-1].price_per_unit, "last_date": ps[-1].date.isoformat(),
            "average_percent_above_market": round(sum(markups) / len(markups), 2) if markups else None,
        })
    return {"supplier": s.name, "materials": rows}


def check_supplier_quote(db: Session, supplier_name: str, items: list[dict]) -> dict:
    """items: [{material_id, quantity_kg, price_per_kg}]"""
    clean = [dict(description=f"material {i.get('material_id')}", material_id=int(i["material_id"]),
                  quantity_kg=float(i["quantity_kg"]), price_per_kg=float(i["price_per_kg"]))
             for i in items]
    check = quote_checker.check_quote(db, clean)
    s = _find_supplier(db, supplier_name)
    name = s.name if s else supplier_name
    return {
        "verdict": check.verdict,
        "summary": check.summary,
        "potential_saving_rupees": check.potential_saving,
        "items": [{k: v for k, v in asdict(c).items() if k != "description"} for c in check.items],
        "negotiation_message": negotiation.template_message(name, check),
    }


def estimate_order(db: Session, material_id: int, quantity: int, weight_per_piece_kg: float,
                   machine_hours_per_piece: float = 0, labour_hours_per_piece: float = 0,
                   owner_price_per_piece: float | None = None) -> dict:
    m = db.get(models.Material, int(material_id))
    if m is None:
        return {"error": "Unknown material_id. Call get_market_prices to see the ids."}
    latest = price_service.get_latest_price(db, m.id)
    b = cost_engine.calculate(
        cost_engine.OrderInput(int(quantity), float(weight_per_piece_kg), latest.price_per_unit,
                               float(machine_hours_per_piece), float(labour_hours_per_piece),
                               float(owner_price_per_piece) if owner_price_per_piece else None),
        to_cost_settings(get_factory_settings(db)),
    )
    return {"material": _material_label(m), "material_price_used_per_kg": latest.price_per_unit, **asdict(b)}


def get_open_quotes(db: Session) -> dict:
    settings = to_cost_settings(get_factory_settings(db))
    out = []
    for q in db.query(models.Quotation).filter(models.Quotation.status == "open").all():
        today = alerts.recost_quotation(db, q, settings)
        out.append({
            "quote": f"Q-{q.id:04d}", "customer": q.customer_name, "part": q.part_name,
            "material": _material_label(q.material), "quantity": q.quantity,
            "quoted_total": q.quoted_price, "profit_when_quoted": round(q.quoted_price - q.total_cost, 2),
            "profit_at_todays_prices": today[1] if today else None,
            "valid_until": q.valid_until.isoformat() if q.valid_until else None,
        })
    return {"open_quotes": out}


def run_price_watch(db: Session) -> dict:
    alerts.check_open_quotations(db)
    unread = db.query(models.Alert).filter(models.Alert.is_read.is_(False)).order_by(models.Alert.id.desc()).all()
    return {"unread_alerts": [{"type": a.type, "message": a.message} for a in unread]}


def create_quotation(db: Session, customer_name: str, part_name: str, material_id: int, quantity: int,
                     weight_per_piece_kg: float, machine_hours_per_piece: float = 0,
                     labour_hours_per_piece: float = 0, price_per_piece: float | None = None,
                     valid_days: int = 15) -> dict:
    est = estimate_order(db, material_id, quantity, weight_per_piece_kg,
                         machine_hours_per_piece, labour_hours_per_piece)
    if "error" in est:
        return est
    per_piece = float(price_per_piece) if price_per_piece else est["recommended_price_per_piece"]
    q = models.Quotation(
        customer_name=customer_name, part_name=part_name, material_id=int(material_id),
        quantity=int(quantity), weight_per_piece_kg=float(weight_per_piece_kg),
        machine_hours_per_piece=float(machine_hours_per_piece),
        labour_hours_per_piece=float(labour_hours_per_piece),
        material_price_used=est["material_price_used_per_kg"], total_cost=est["total_cost"],
        quoted_price=round(per_piece * int(quantity), 2),
        valid_until=date.today() + timedelta(days=int(valid_days)),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return {"saved": True, "quote": f"Q-{q.id:04d}", "price_per_piece": per_piece,
            "total": q.quoted_price, "profit": round(q.quoted_price - q.total_cost, 2),
            "pdf_url": f"/quotes/{q.id}/pdf"}


# ---------- What Gemini is told about each tool ----------

ORDER_PROPS = {
    "material_id": {"type": "integer", "description": "From get_market_prices"},
    "quantity": {"type": "integer", "description": "Number of pieces"},
    "weight_per_piece_kg": {"type": "number", "description": "Finished weight of one piece in kg"},
    "machine_hours_per_piece": {"type": "number", "description": "Machine time per piece in hours (0 if unknown)"},
    "labour_hours_per_piece": {"type": "number", "description": "Labour time per piece in hours (0 if unknown)"},
}

TOOLS = {
    "get_market_prices": (get_market_prices, {
        "description": "Today's market price per kg of every raw material, with material ids and 30-day change.",
        "parameters": {"type": "object", "properties": {}},
    }),
    "get_suppliers": (get_suppliers, {
        "description": "All suppliers with how much above market (in %) the factory pays each on average.",
        "parameters": {"type": "object", "properties": {}},
    }),
    "get_supplier_history": (get_supplier_history, {
        "description": "One supplier's purchase history per material: last price, total kg, average % above market.",
        "parameters": {"type": "object", "properties": {
            "supplier_name": {"type": "string"}}, "required": ["supplier_name"]},
    }),
    "check_supplier_quote": (check_supplier_quote, {
        "description": "Check a supplier's quoted prices against market and history. Returns a verdict, "
                       "possible saving, cheapest supplier per item and a negotiation message.",
        "parameters": {"type": "object", "properties": {
            "supplier_name": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "material_id": {"type": "integer"},
                "quantity_kg": {"type": "number"},
                "price_per_kg": {"type": "number", "description": "Rupees per kg before GST"}},
                "required": ["material_id", "quantity_kg", "price_per_kg"]}}},
            "required": ["supplier_name", "items"]},
    }),
    "estimate_order": (estimate_order, {
        "description": "True cost of a customer order at today's material price, the safe recommended price, "
                       "and whether the owner's own price makes a loss.",
        "parameters": {"type": "object", "properties": {
            **ORDER_PROPS,
            "owner_price_per_piece": {"type": "number", "description": "Price the owner plans to quote, if any"}},
            "required": ["material_id", "quantity", "weight_per_piece_kg"]},
    }),
    "get_open_quotes": (get_open_quotes, {
        "description": "Open customer quotations with profit when quoted and profit at today's prices.",
        "parameters": {"type": "object", "properties": {}},
    }),
    "run_price_watch": (run_price_watch, {
        "description": "Re-check all open quotations at today's prices and return unread alerts "
                       "about quotes that now lose money or have thin margins.",
        "parameters": {"type": "object", "properties": {}},
    }),
    "create_quotation": (create_quotation, {
        "description": "SAVE a customer quotation and get its PDF link. Only call this when the owner "
                       "clearly asks to create or save a quote.",
        "parameters": {"type": "object", "properties": {
            "customer_name": {"type": "string"}, "part_name": {"type": "string"},
            **ORDER_PROPS,
            "price_per_piece": {"type": "number", "description": "Leave out to use the recommended price"},
            "valid_days": {"type": "integer"}},
            "required": ["customer_name", "part_name", "material_id", "quantity", "weight_per_piece_kg"]},
    }),
}


def run_tool(db: Session, name: str, args: dict) -> dict:
    """Run one tool by name. Errors are returned to the agent instead of crashing."""
    if name not in TOOLS:
        return {"error": f"Unknown tool {name}"}
    fn, _ = TOOLS[name]
    try:
        return fn(db, **(args or {}))
    except Exception as e:   # bad arguments from the model, etc.
        return {"error": f"{type(e).__name__}: {e}"}
